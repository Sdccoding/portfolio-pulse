"""
logic/critic.py — Portfolio Pulse: The Critic Loop
====================================================
The Reasoning Brain. Evaluates news against a ticker's investment thesis.
"""
from loguru import logger

import json
from logic.llm_client import client, MODEL_ID, CRITIC_CONFIG
from logic.thesis_manager import get_or_infer_thesis

_EVALUATE_NEWS_PROMPT = """\
You are a seasoned investment thesis critic for Indian equities.

Your task is to take a specific news headline and evaluate whether it structurally \
impacts the previously established investment thesis for a stock.

Ticker: {ticker}
Investment Thesis: "{thesis}"
News Headline: "{headline}"

Determine if this news is a SIGNAL or NOISE.

Definitions:
  SIGNAL — News that structurally impacts the business model, competitive position, \
earnings trajectory, or directly relates to the stated thesis. (e.g., earnings beats/misses, \
regulatory rulings, M&A, major policy changes).
  NOISE  — Temporary price moves, general market sentiment, macro commentary not \
specific to the company, clickbait, or analyst noise with no new information.

Think step by step and then return ONLY a valid JSON object (no markdown fences) with this schema:

{{
  "classification": "SIGNAL" | "NOISE",
  "reasoning": "<A 1-sentence explanation of why it hit that classification>",
  "confidence_score": <A float between 0.0 and 1.0>
}}

Rules:
- Be ruthlessly honest. Most market chatter should be NOISE.
- Base your classification strictly on whether the headline impacts the *thesis*.
- Return ONLY the JSON object. No markdown formatting.
"""

def evaluate_news(ticker: str, news_headline: str) -> dict:
    """
    Evaluates a news headline against the stored thesis for a ticker.

    Args:
        ticker: The stock ticker (e.g., 'TATASTEEL')
        news_headline: The news headline to evaluate.

    Returns:
        dict: A JSON structured object containing `classification`, `reasoning`, and `confidence_score`.
    """
    # 1. Fetch the investment thesis using ThesisManager
    thesis = get_or_infer_thesis(ticker)

    # 2. Prepare the prompt for Gemini
    prompt = _EVALUATE_NEWS_PROMPT.format(
        ticker=ticker,
        thesis=thesis,
        headline=news_headline
    )

    try:
        # 3. Call Gemini using CRITIC_CONFIG (no search grounding, just reasoning)
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt,
            config=CRITIC_CONFIG,
        )

        raw = (response.text or "").strip()
        if raw.startswith("```"):
            raw = "\n".join(
                l for l in raw.splitlines() if not l.strip().startswith("```")
            ).strip()

        data = json.loads(raw)
        return {
            "headline": news_headline,
            "classification": data.get("classification", "NOISE"),
            "reasoning": data.get("reasoning", "Failed to parse reasoning."),
            "confidence_score": float(data.get("confidence_score", 0.0))
        }

    except Exception as e:
        logger.warning(f"[Critic] ⚠️ Inference failed for {ticker}: {e}")
        return {
            "headline": news_headline,
            "classification": "NOISE",
            "reasoning": f"Fallback due to inference error: {e}",
            "confidence_score": 0.0
        }
