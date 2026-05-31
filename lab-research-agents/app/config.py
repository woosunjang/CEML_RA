"""
Lab Research Agents — Configuration

Loads environment variables from .env and provides them as module-level constants.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Load .env from project root (two levels up from this file)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _PROJECT_ROOT / ".env"

if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH)
else:
    # Try loading from cwd as fallback (e.g. running from project root)
    load_dotenv()

# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_CHAT_MODEL: str = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o")
OPENAI_EMBEDDING_MODEL: str = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

if not OPENAI_API_KEY:
    raise EnvironmentError(
        "OPENAI_API_KEY is not set. "
        "Copy .env.example to .env and fill in your API key."
    )

# ---------------------------------------------------------------------------
# Anthropic (optional)
# ---------------------------------------------------------------------------
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_CHAT_MODEL: str = os.getenv("ANTHROPIC_CHAT_MODEL", "claude-sonnet-4-20250514")

# ---------------------------------------------------------------------------
# Qdrant (local file-based mode — no Docker required)
# ---------------------------------------------------------------------------
QDRANT_URL: str = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_STORAGE_PATH: Path = _PROJECT_ROOT / "qdrant_storage"
QDRANT_COLLECTION: str = os.getenv("QDRANT_COLLECTION", "lab_research_chunks")

# Ensure qdrant storage directory exists
QDRANT_STORAGE_PATH.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_RAW_DIR: Path = _PROJECT_ROOT / "data" / "raw"
DATA_PARSED_DIR: Path = _PROJECT_ROOT / "data" / "parsed"

# Ensure data directories exist
DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)
DATA_PARSED_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# lab-paper-scout integration (read-only)
# ---------------------------------------------------------------------------
SCOUT_DB_PATH: Path = Path(os.getenv(
    "SCOUT_DB_PATH",
    str(_PROJECT_ROOT.parent / "lab-paper-scout" / "data" / "paper_scout.db"),
))
