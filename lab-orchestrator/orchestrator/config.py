"""
Lab Orchestrator — Configuration

Loads environment variables and provides module-level constants.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

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

# Scout
SCOUT_DB_PATH: Path = Path(os.getenv(
    "SCOUT_DB_PATH",
    str(_PROJECT_ROOT.parent / "lab-paper-scout" / "data" / "paper_scout.db"),
))

# Image generation
IMAGE_PROVIDER: str = os.getenv("IMAGE_PROVIDER", "google")  # google | openai
IMAGE_MODEL_GOOGLE: str = os.getenv("IMAGE_MODEL_GOOGLE", "gemini-3-pro-image-preview")
IMAGE_MODEL_OPENAI: str = os.getenv("IMAGE_MODEL_OPENAI", "gpt-image-2")

# FalkorDB (Graphiti archival memory)
FALKORDB_URI: str = os.getenv("FALKORDB_URI", "falkor://localhost:6379")

PROJECT_ROOT: Path = _PROJECT_ROOT

# ── CEML_RA 프로젝트 루트 기준 경로 ──
CEML_ROOT: Path = _PROJECT_ROOT.parent  # /path/to/CEML_RA

# 산출물 (에이전트 생성 파일)
GENERATED_DIR: Path = CEML_ROOT / "generated"
GENERATED_PROJECT_DIR: Path = GENERATED_DIR / "project"
GENERATED_WRITING_DIR: Path = GENERATED_DIR / "writing"
GENERATED_TEACHING_DIR: Path = GENERATED_DIR / "teaching"
GENERATED_PRESENTATION_DIR: Path = GENERATED_DIR / "presentation"
GENERATED_REPORTS_DIR: Path = GENERATED_DIR / "reports"

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

