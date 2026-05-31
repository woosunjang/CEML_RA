"""
Archival Worker — Separate process for Graphiti ingestion.

Watches the archival queue directory for JSON job files,
processes them one at a time, and ingests into Graphiti.

Runs as a separate launchd service to isolate memory usage
from the main orchestrator process.

Usage:
    python3 -m integrations.archival_worker
"""

import asyncio
import gc
import json
import logging
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from orchestrator.config import ARCHIVAL_QUEUE_DIR, FALKORDB_URI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s:%(name)s:%(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("archival_worker")

# How often to poll the queue (seconds)
POLL_INTERVAL = 10
# Max memory (RSS in MB) before forced GC + skip
MAX_RSS_MB = 400

_shutdown = False


def _signal_handler(signum, frame):
    global _shutdown
    logger.info(f"Received signal {signum}, shutting down...")
    _shutdown = True


signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)


def _get_rss_mb() -> float:
    """Get current process RSS in MB."""
    try:
        import resource
        # resource.getrusage returns KB on macOS
        usage = resource.getrusage(resource.RUSAGE_SELF)
        return usage.ru_maxrss / (1024 * 1024)  # macOS: bytes → MB
    except Exception:
        return 0.0


_graphiti_instance = None


async def _get_graphiti():
    """Lazy-init Graphiti client (matching archival.py API)."""
    global _graphiti_instance
    if _graphiti_instance is not None:
        return _graphiti_instance

    try:
        from graphiti_core import Graphiti
        from graphiti_core.llm_client import LLMConfig, OpenAIClient
        from graphiti_core.embedder.openai import (
            OpenAIEmbedder, OpenAIEmbedderConfig,
        )
        from graphiti_core.driver.falkordb_driver import FalkorDriver
        from orchestrator.config import OPENAI_EMBEDDING_MODEL

        # Parse FalkorDB URI
        uri = FALKORDB_URI
        if uri.startswith("falkor://"):
            uri = uri[len("falkor://"):]
        parts = uri.split(":")
        host = parts[0]
        port = int(parts[1]) if len(parts) > 1 else 6379

        extraction_model = "gpt-5.4-nano"
        llm_config = LLMConfig(
            model=extraction_model,
            small_model=extraction_model,
            temperature=0.0,
        )
        reasoning = "low"  # gpt-5.4 series
        llm_client = OpenAIClient(config=llm_config, reasoning=reasoning)

        embedder = OpenAIEmbedder(
            config=OpenAIEmbedderConfig(
                model=OPENAI_EMBEDDING_MODEL,
            )
        )

        graph_driver = FalkorDriver(
            host=host,
            port=port,
        )

        _graphiti_instance = Graphiti(
            graph_driver=graph_driver,
            llm_client=llm_client,
            embedder=embedder,
        )
        await _graphiti_instance.build_indices_and_constraints()

        logger.info(f"Graphiti connected: {host}:{port}, model={extraction_model}")
        return _graphiti_instance

    except Exception as e:
        logger.error(f"Graphiti init failed: {e}")
        return None


async def _process_job(job_file: Path) -> bool:
    """Process a single archival job file."""
    try:
        data = json.loads(job_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Failed to read job {job_file.name}: {e}")
        job_file.unlink(missing_ok=True)
        return False

    conv_id = data.get("conversation_id", "unknown")
    user_msg = data.get("user_message", "")
    asst_msg = data.get("assistant_message", "")
    agent_name = data.get("agent_name", "orchestrator")

    graphiti = await _get_graphiti()
    if not graphiti:
        logger.warning("Graphiti not available, skipping job")
        return False

    try:
        from graphiti_core.nodes import EpisodeType

        ts = datetime.now(timezone.utc)
        safe_id = conv_id.replace("-", "")
        episode_name = f"{safe_id[:12]}_{ts.strftime('%H%M%S')}"

        episode_body = (
            f"[User]: {user_msg}\n"
            f"[Assistant/{agent_name}]: {asst_msg}"
        )

        await graphiti.add_episode(
            name=episode_name,
            episode_body=episode_body,
            source=EpisodeType.text,
            source_description="lab_orchestrator_chat",
            reference_time=ts,
            group_id=f"session{safe_id[:12]}",
        )

        logger.info(
            f"Ingested: {episode_name} ({len(episode_body)} chars)"
        )

        # Remove processed job
        job_file.unlink(missing_ok=True)

        # Force GC after each ingestion
        del episode_body, data
        gc.collect()

        return True

    except Exception as e:
        logger.error(f"Ingestion failed for {job_file.name}: {e}")
        # Move to failed dir instead of deleting
        failed_dir = ARCHIVAL_QUEUE_DIR / "failed"
        failed_dir.mkdir(exist_ok=True)
        try:
            job_file.rename(failed_dir / job_file.name)
        except OSError:
            pass
        return False


async def _worker_loop():
    """Main worker loop: poll queue, process jobs."""
    ARCHIVAL_QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"Archival worker started. Queue: {ARCHIVAL_QUEUE_DIR}")
    logger.info(f"Poll interval: {POLL_INTERVAL}s, Max RSS: {MAX_RSS_MB}MB")

    while not _shutdown:
        try:
            # Find pending jobs (sorted by filename = timestamp order)
            jobs = sorted(ARCHIVAL_QUEUE_DIR.glob("*.json"))

            if jobs:
                logger.info(f"Found {len(jobs)} pending job(s)")

            for job_file in jobs:
                if _shutdown:
                    break

                # Memory check
                rss = _get_rss_mb()
                if rss > MAX_RSS_MB:
                    logger.warning(
                        f"RSS={rss:.0f}MB > {MAX_RSS_MB}MB, "
                        "forcing GC and pausing..."
                    )
                    gc.collect()
                    await asyncio.sleep(5)

                await _process_job(job_file)

                # Brief pause between jobs
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Worker loop error: {e}")

        # Poll interval
        for _ in range(POLL_INTERVAL):
            if _shutdown:
                break
            await asyncio.sleep(1)

    logger.info("Archival worker stopped.")


def main():
    """Entry point."""
    # Load .env
    try:
        from dotenv import load_dotenv
        load_dotenv(_PROJECT_ROOT / ".env")
    except ImportError:
        pass

    asyncio.run(_worker_loop())


if __name__ == "__main__":
    main()
