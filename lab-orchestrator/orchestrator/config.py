"""
Lab Orchestrator — Configuration

Loads environment variables and provides module-level constants.
"""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


def _optional_env_path(name: str) -> Optional[Path]:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return None
    return Path(raw).expanduser().resolve()

# OpenAI
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_CHAT_MODEL: str = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o")
OPENAI_EMBEDDING_MODEL: str = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

# Anthropic
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_CHAT_MODEL: str = os.getenv("ANTHROPIC_CHAT_MODEL", "claude-sonnet-4-6")

# Google
GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")

# Qdrant
QDRANT_URL: str = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION: str = os.getenv("QDRANT_COLLECTION", "lab_research_chunks")

# Neo4j (Graphiti archival memory)
NEO4J_URI: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER: str = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DATABASE: str = os.getenv("NEO4J_DATABASE", "neo4j")

# Scout
SCOUT_DB_PATH: Path = Path(os.getenv(
    "SCOUT_DB_PATH",
    str(_PROJECT_ROOT.parent / "lab-paper-scout" / "data" / "paper_scout.db"),
))

# Image generation
IMAGE_PROVIDER: str = os.getenv("IMAGE_PROVIDER", "google")  # google | openai
IMAGE_MODEL_GOOGLE: str = os.getenv("IMAGE_MODEL_GOOGLE", "gemini-3-pro-image-preview")
IMAGE_MODEL_OPENAI: str = os.getenv("IMAGE_MODEL_OPENAI", "gpt-image-2")

PROJECT_ROOT: Path = _PROJECT_ROOT

# ── CEML_RA 프로젝트 루트 기준 경로 ──
CEML_ROOT: Path = _PROJECT_ROOT.parent  # /path/to/CEML_RA

# Durable artifacts. Set CEML_RA_ARTIFACTS_DIR to move generated research
# outputs outside the source tree; otherwise fall back to in-repo generated/.
ARTIFACTS_DIR: Path = _optional_env_path("CEML_RA_ARTIFACTS_DIR") or (CEML_ROOT / "generated")

# Backward-compatible generated aliases used by existing agents.
GENERATED_DIR: Path = ARTIFACTS_DIR
GENERATED_PROJECT_DIR: Path = ARTIFACTS_DIR / "project"
GENERATED_WRITING_DIR: Path = ARTIFACTS_DIR / "writing"
GENERATED_TEACHING_DIR: Path = ARTIFACTS_DIR / "teaching"
GENERATED_PRESENTATION_DIR: Path = ARTIFACTS_DIR / "presentation"
GENERATED_REPORTS_DIR: Path = ARTIFACTS_DIR / "reports"

# 데이터 (DB, 세션, 프로젝트)
DATA_DIR: Path = CEML_ROOT / "data"
SESSIONS_DIR: Path = DATA_DIR / "sessions"
PROJECTS_JSON: Path = DATA_DIR / "projects.json"
USAGE_DB: Path = DATA_DIR / "usage.db"

# 로그
LOG_DIR: Path = CEML_ROOT / "logs"
CHAT_LOG_DIR: Path = LOG_DIR / "chat"

# 파일 명령
COMMANDS_DIR: Path = _PROJECT_ROOT / "commands"

# Archival 큐 (별도 Worker 프로세스용)
ARCHIVAL_QUEUE_DIR: Path = COMMANDS_DIR / "archival_queue"
