"""
config.py — Portfolio Pulse: Configuration
==========================================
Single source of truth for loading environment variables.
All other modules import from here rather than reading os.getenv directly.
"""

import os
from dotenv import load_dotenv
import sys
from loguru import logger

# ── Logging Setup ─────────────────────────────────────────────────────────────
# We configure loguru here so any module importing config globally inherits this format.
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | [Trace: <cyan>{extra[trace_id]}</cyan>] | {name}:{function}:{line} - <level>{message}</level>"
)
import uuid
logger.configure(extra={"trace_id": f"BOOT-{str(uuid.uuid4())[:8]}"})

# Load .env from the project root (same directory as this file)
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_BASE_DIR, ".env"))

# ── API Keys ─────────────────────────────────────────────────────────────────
# Loaded securely during build via gcloud run deploy --set-env-vars
_GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

def get_api_key() -> str:
    """Return the Gemini API key."""
    if not _GEMINI_API_KEY:
        raise EnvironmentError("GEMINI_API_KEY is missing. Check .env or Cloud Run Env Vars.")
    return _GEMINI_API_KEY

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()


# ── Paths ─────────────────────────────────────────────────────────────────────

BASE_DIR = _BASE_DIR
PORTFOLIO_CSV_PATH    = os.path.join(BASE_DIR, "portfolio.csv")
THESIS_METADATA_PATH  = os.path.join(BASE_DIR, "thesis_metadata.json")
SCOUT_JSON_PATH       = os.path.join(BASE_DIR, "scout_suggestions.json")

# ── Telegram Webhook ──────────────────────────────────────────────────────────

TELEGRAM_WEBHOOK_URL = os.getenv("TELEGRAM_WEBHOOK_URL", "https://portfolio-pulse-111880092623.us-central1.run.app").strip()
