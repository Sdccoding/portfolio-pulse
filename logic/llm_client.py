"""
logic/llm_client.py — Portfolio Pulse: Gemini Client
======================================================
Initialises the shared Gemini 2.0 Flash (gemini-2.0-flash) client.

All other modules that need to talk to Gemini import from here:

    from logic.llm_client import client, MODEL_ID, GENERATION_CONFIG
"""

from google import genai
from google.genai import types
from config import get_api_key

# ── Model ─────────────────────────────────────────────────────────────────────

MODEL_ID = "gemini-2.5-flash"

# ── Client (singleton) ────────────────────────────────────────────────────────

client = genai.Client(api_key=get_api_key())

# ── Google Search grounding tool ──────────────────────────────────────────────

GOOGLE_SEARCH_TOOL = types.Tool(google_search=types.GoogleSearch())

# ── Default generation config (with search grounding) ────────────────────────

GENERATION_CONFIG = types.GenerateContentConfig(
    tools=[GOOGLE_SEARCH_TOOL],
    response_modalities=["TEXT"],
)

# ── Critic config (no grounding — pure reasoning, cheaper & faster) ───────────

CRITIC_CONFIG = types.GenerateContentConfig(
    response_modalities=["TEXT"],
)
