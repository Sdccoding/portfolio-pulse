"""
core.py — Portfolio Pulse: Core Engine
=========================================
Senior Python Engineer & Data Analyst — The Architect

Responsibilities:
  - Load and parse portfolio.csv
  - Initialize Gemini 2.5 Flash with Google Search Grounding
  - Fetch real-time news / analyst insight per ticker via Gemini
  - Mask Quantity fields before any LLM call (privacy)
  - Quality Critic: classify each news item as SIGNAL or NOISE
"""
from loguru import logger

import os
import json
import time
import pandas as pd
from dotenv import load_dotenv
from logic import llm_client

# ---------------------------------------------------------------------------
# 1. Environment Setup
# ---------------------------------------------------------------------------

load_dotenv()

# ---------------------------------------------------------------------------
# 3. Portfolio Loading
# ---------------------------------------------------------------------------

PORTFOLIO_CSV_PATH = os.path.join(os.path.dirname(__file__), "portfolio.csv")

# Quantity columns to mask before sending to LLM
QUANTITY_COLUMNS = ["Quantity Available"]

# Columns kept private — never sent to LLM
PRIVATE_COLUMNS = ["Quantity Available"]


def load_portfolio(csv_path: str = PORTFOLIO_CSV_PATH) -> pd.DataFrame:
    """
    Load and validate portfolio.csv.

    Returns a DataFrame with clean dtypes and no empty rows.
    """
    df = pd.read_csv(csv_path)

    # Drop fully empty rows that may exist in the raw export
    df.dropna(how="all", inplace=True)
    df.reset_index(drop=True, inplace=True)

    # Coerce numeric columns
    numeric_cols = [
        "Quantity Available",
        "Average Price",
        "Previous Closing Price",
        "Unrealized P&L",
        "Unrealized P&L Pct.",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # logger.info(f"[Portfolio] Loaded {len(df)} holdings from '{csv_path}'")
    return df


# ---------------------------------------------------------------------------
# 4. Privacy — Quantity Masking
# ---------------------------------------------------------------------------

def mask_quantity(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return a *copy* of the DataFrame with all Quantity columns replaced by
    the string '[MASKED]'.  The original DataFrame is never mutated.

    This ensures the investor's exact position sizes are never leaked to
    the LLM or any external API.
    """
    masked = df.copy()
    for col in QUANTITY_COLUMNS:
        if col in masked.columns:
            masked[col] = "[MASKED]"
    return masked


# ---------------------------------------------------------------------------
# 5. Portfolio Analysis — 2-Call Architecture (Option B)
#    Call 1: Portfolio Overview  — qualitative red/green flags across all holdings
#    Call 2: Deep Dive           — per-ticker detail only for flagged names
# ---------------------------------------------------------------------------

def build_portfolio_table(df: pd.DataFrame) -> str:
    """
    Format the portfolio as a compact text table for Gemini.
    Includes Qty so the LLM can make position-size-aware recommendations
    (e.g. 'trim half', 'reduce to 50 shares', 'scale into 20 more').
    """
    lines = [
        f"{'Symbol':<40} {'Sector':<30} {'Type':<20} "
        f"{'Qty':>8} {'Avg Price':>10} {'Curr Price':>10} {'P&L%':>8}",
        "─" * 135,
    ]
    for _, row in df.iterrows():
        lines.append(
            f"{str(row.get('Symbol','')):<40} "
            f"{str(row.get('Sector','')):<30} "
            f"{str(row.get('Instrument Type','')):<20} "
            f"{str(row.get('Quantity Available','N/A')):>8} "
            f"{str(row.get('Average Price','N/A')):>10} "
            f"{str(row.get('Previous Closing Price','N/A')):>10} "
            f"{str(row.get('Unrealized P&L Pct.','N/A')):>8}%"
        )
    return "\n".join(lines)


# ── Call 1 Prompt ────────────────────────────────────────────────────────────

_OVERVIEW_PROMPT = """\
You are a senior Indian equity research analyst with real-time market access via Google Search.
Today's date is {today}.

Below is an investor's portfolio including position quantities:

{portfolio_table}

Using Google Search (prioritize sources like Economic Times, Moneycontrol, and Livemint), analyse this portfolio holistically against today's market news.

Return ONLY a valid JSON object (no markdown fences) with this schema:

{{
  "market_overview": "<2-3 sentences on today's overall Indian market mood>",
  "portfolio_health": "Bullish" | "Neutral" | "Bearish",
  "portfolio_health_rationale": "<1-2 sentences on overall portfolio stance>",
  "sector_commentary": {{
    "<sector>": "<1-sentence on how news/macro is affecting this sector today>"
  }},
  "green_flags": [
    {{
      "symbol": "<NSE/BSE symbol>",
      "headline": "<key positive catalyst headline>",
      "reason": "<1-2 sentence explanation of the positive signal>"
    }}
  ],
  "red_flags": [
    {{
      "symbol": "<NSE/BSE symbol>",
      "headline": "<key risk or negative catalyst headline>",
      "reason": "<1-2 sentence explanation of the concern>"
    }}
  ],
  "neutral_watch": [
    {{
      "symbol": "<NSE/BSE symbol>",
      "reason": "<1 sentence why this is worth monitoring but has no clear signal>"
    }}
  ]
}}

Rules:
- green_flags: any holding with a CLEARLY POSITIVE catalyst today (earnings beat, upgrade, policy win, strong momentum). Include AS MANY as are genuinely justified — do not cap at a fixed number.
- red_flags: any holding with a CLEAR RISK signal (downgrade, bad earnings, regulatory headwind, macro sensitivity). Include AS MANY as are genuinely justified.
- neutral_watch: holdings in a wait-and-see zone — upcoming event, mixed signals, or consolidation.
- Be honest. Do not force flags. If only 2 holdings have real catalyst news, only flag 2.
- sector_commentary: only include sectors that appear in the portfolio and have relevant news today.
- Return ONLY the JSON. No preamble, no markdown fences.
"""


# ── Call 2 Prompt ────────────────────────────────────────────────────────────

_DEEP_DIVE_PROMPT = """\
You are a senior Indian equity research analyst with real-time market access via Google Search.
Today's date is {today}.

The following {n} holdings from an investor's portfolio have been flagged for deeper analysis \
(either as green flags or red flags in an earlier screening). Position quantities are included \
so you can make specific, actionable recommendations (e.g. 'sell 30 of your 114 shares', \
'add 20 more to average down'):

{flagged_table}

For EACH holding above, search for the latest news and analyst views (prioritize Economic Times, Moneycontrol, and Livemint), then return a JSON object:

{{
  "deep_dive": [
    {{
      "symbol": "<symbol>",
      "flag_type": "green" | "red" | "neutral",
      "latest_news": "<2-3 key headlines from the last 48–72 hours>",
      "analyst_sentiment": "Bullish" | "Bearish" | "Neutral",
      "analyst_rationale": "<1-2 sentences on why analysts feel this way>",
      "key_risks": ["<risk 1>", "<risk 2>"],
      "action_signal": "HOLD" | "BUY MORE" | "TRIM" | "CONSIDER EXIT",
      "action_reason": "<one clear sentence justifying the signal, reference quantity where relevant>"
    }}
  ]
}}

Rules:
- Cover every symbol in the list above — no omissions.
- action_signal must be one of: HOLD, BUY MORE, TRIM, CONSIDER EXIT.
  Use TRIM (not CONSIDER EXIT) when only a partial reduction is appropriate given the position size.
- Reference the actual quantity in action_reason where it adds clarity (e.g. 'consider selling 40 of your 114 shares to reduce concentration').
- Base everything on real, searchable news from today or the past 72 hours.
- Return ONLY the JSON. No preamble, no markdown fences.
"""


# ── Helper: extract grounding URLs ───────────────────────────────────────────

def _extract_sources(llm_response) -> list[str]:
    """Extract grounding source URLs from an LLMResponse."""
    return llm_response.grounding_sources


# ── Helper: strip JSON fences ─────────────────────────────────────────────────

def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    start = raw.find("{")
    end = raw.rfind("}")
    
    # Check for list fallback
    if start == -1 or end == -1:
        start = raw.find("[")
        end = raw.rfind("]")
        
    if start != -1 and end != -1 and end > start:
        return raw[start:end + 1]
    return raw


# ── Call 1: Portfolio Overview ────────────────────────────────────────────────

def fetch_portfolio_overview(df: pd.DataFrame) -> dict:
    """
    Call 1 of 2.

    Send the full masked portfolio to Gemini with Google Search grounding.
    Gemini qualitatively identifies green flags, red flags, and neutral-watch
    holdings across the entire portfolio — no fixed count, purely signal-driven.

    Args:
        df: Raw portfolio DataFrame (quantities will be masked inside).

    Returns:
        dict with keys: market_overview, portfolio_health, portfolio_health_rationale,
        sector_commentary, green_flags, red_flags, neutral_watch.
    """
    from datetime import date as _date
    today = _date.today().strftime("%Y-%m-%d")
    portfolio_table = build_portfolio_table(df)

    # logger.info("\n[Analysis] Call 1/2 — Portfolio Overview (all holdings, qualitative flags)...")

    prompt = _OVERVIEW_PROMPT.format(today=today, portfolio_table=portfolio_table)

    try:
        response = llm_client.generate(prompt, use_grounding=True)
        raw = _strip_fences(response.text)
        data = json.loads(raw)
        data["grounding_sources"] = _extract_sources(response)

        n_green  = len(data.get("green_flags",   []))
        n_red    = len(data.get("red_flags",     []))
        n_watch  = len(data.get("neutral_watch", []))
        # logger.info(f"[Analysis] ✓ Overview complete — "
        #       f"🟢 {n_green} green  🔴 {n_red} red  👁 {n_watch} watch")
        return data

    except Exception as e:
        logger.warning(f"[Analysis] ⚠️  Overview call failed: {e}")
        return {
            "market_overview": "Market data unavailable.",
            "portfolio_health": "Neutral",
            "portfolio_health_rationale": "Could not fetch live analysis.",
            "sector_commentary": {},
            "green_flags": [],
            "red_flags": [],
            "neutral_watch": [],
            "grounding_sources": [],
            "error": str(e),
        }


# ── Call 2: Deep Dive on Flagged Holdings ────────────────────────────────────

_DEEP_DIVE_CHUNK_SIZE = 8   # max symbols per deep-dive Gemini call


def _try_recover_deep_dive_json(raw: str) -> list[dict]:
    """
    Best-effort recovery when Gemini returns truncated JSON.
    Tries to extract the valid portion of the 'deep_dive' array before the cutoff.
    Returns an empty list if nothing can be salvaged.
    """
    import re
    # Find the start of the deep_dive array
    match = re.search(r'"deep_dive"\s*:\s*(\[)', raw)
    if not match:
        return []

    array_start = match.start(1)
    fragment = raw[array_start:]

    # Walk forward collecting complete JSON objects
    depth = 0
    in_string = False
    escaped = False
    objects: list[str] = []
    obj_start: int | None = None

    for i, ch in enumerate(fragment):
        if escaped:
            escaped = False
            continue
        if ch == "\\" and in_string:
            escaped = True
            continue
        if ch == '"' and not escaped:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            if depth == 0 and i > 0:   # top-level object start (after '[')
                obj_start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and obj_start is not None:
                try:
                    obj = json.loads(fragment[obj_start:i + 1])
                    objects.append(obj)
                except Exception:
                    pass
                obj_start = None

    if objects:
        logger.info(f"[Analysis] ↩  Recovered {len(objects)} item(s) from truncated response.")
    return objects


def fetch_flagged_deep_dive(df: pd.DataFrame, flagged_symbols: list[str]) -> list[dict]:
    """
    Call 2 of 2.

    Deep-dives on the holdings flagged in the overview (green + red + neutral).
    Splits large symbol lists into chunks of ≤ _DEEP_DIVE_CHUNK_SIZE per call
    to avoid hitting Gemini's response-length limit and JSON truncation.
    Falls back to best-effort JSON recovery on truncated responses.

    Args:
        df:              Full portfolio DataFrame (quantities included for actionable advice).
        flagged_symbols: List of ticker symbols to analyse in depth.

    Returns:
        List of deep-dive dicts, one per flagged symbol.
    """
    if not flagged_symbols:
        return []

    from datetime import date as _date
    today = _date.today().strftime("%Y-%m-%d")

    # Build the sub-dataframe for flagged holdings (with quantities — no masking)
    flagged_df = df[df["Symbol"].isin(flagged_symbols)].reset_index(drop=True)
    if flagged_df.empty:
        return []

    # ── Chunk into batches ───────────────────────────────────────────────────
    all_results: list[dict] = []
    chunks = [
        flagged_symbols[i : i + _DEEP_DIVE_CHUNK_SIZE]
        for i in range(0, len(flagged_symbols), _DEEP_DIVE_CHUNK_SIZE)
    ]
    n_chunks = len(chunks)

    for chunk_idx, chunk_syms in enumerate(chunks, start=1):
        chunk_df = flagged_df[flagged_df["Symbol"].isin(chunk_syms)].reset_index(drop=True)
        if chunk_df.empty:
            continue

        chunk_table = build_portfolio_table(chunk_df)
        n = len(chunk_df)

        if n_chunks > 1:
            logger.info(
                f"[Analysis] Deep dive chunk {chunk_idx}/{n_chunks} "
                f"— {n} holding(s)…"
            )

        prompt = _DEEP_DIVE_PROMPT.format(
            today=today,
            n=n,
            flagged_table=chunk_table,
        )

        try:
            response = llm_client.generate(prompt, use_grounding=True)
            raw = _strip_fences(response.text)

            try:
                data = json.loads(raw)
                chunk_results = data.get("deep_dive", [])
            except json.JSONDecodeError as je:
                logger.warning(f"[Analysis] ⚠️  JSON truncated in chunk {chunk_idx}: {je}. Attempting recovery…")
                chunk_results = _try_recover_deep_dive_json(raw)

            all_results.extend(chunk_results)

        except Exception as e:
            logger.warning(f"[Analysis] ⚠️  Deep dive chunk {chunk_idx} failed: {e}")

    logger.info(f"[Analysis] ✓ Deep dive complete — {len(all_results)}/{len(flagged_symbols)} holdings analysed.")
    return all_results


# ── Call 3: Quality Critic (SIGNAL vs NOISE) ─────────────────────────────────

_CRITIC_PROMPT = """\
You are a seasoned investment thesis critic for Indian equities.

Below is a list of news items from a portfolio analysis, each paired with \
the investor's thesis for that stock. Your job is to classify each item as \
SIGNAL or NOISE.

Definitions:
  SIGNAL — News that structurally impacts the business model, competitive position, \
earnings trajectory, or the specific stated thesis. Examples: earnings beats/misses, \
regulatory rulings, major contract wins/losses, leadership change, product launch, \
M&A, sector policy change.
  NOISE  — Temporary price moves, general market sentiment, macro commentary not \
specific to the company, clickbait, or analyst target tweaks with no new information.

News items (JSON array):
{items_json}

Return ONLY a valid JSON array (no markdown fences) where each element has:
{{
  "id": <same integer id as in input>,
  "classification": "SIGNAL" | "NOISE",
  "reason": "<one short sentence>"
}}

Rules:
- Cover every id. Do not skip any.
- Be ruthlessly honest. Most market noise items should be NOISE.
- Return ONLY the JSON array. No preamble, no markdown fences.
"""

# Critic uses use_grounding=False — pure reasoning, cheaper & faster


def classify_news_items(
    overview: dict,
    deep_dive: list[dict],
    thesis_map: dict[str, str],
) -> tuple[dict, list[dict]]:
    """
    Call 3 of 3 (no grounding — pure reasoning).

    Passes every flagged news item through the Critic prompt to get
    SIGNAL / NOISE classification.  Updates each item in-place with a
    ``"quality"`` key and returns (updated_overview, updated_deep_dive).

    Args:
        overview:   Result from fetch_portfolio_overview.
        deep_dive:  Result from fetch_flagged_deep_dive.
        thesis_map: ticker → thesis string mapping.

    Returns:
        Tuple of (updated_overview, updated_deep_dive).
    """
    # ── Build flat list of items with id, headline, symbol, thesis ──────────
    items = []
    idx = 0

    for flag_key in ("green_flags", "red_flags", "neutral_watch"):
        for item in overview.get(flag_key, []):
            sym = item.get("symbol", "")
            headline = item.get("headline") or item.get("reason", "")
            thesis = thesis_map.get(sym, "Growth Play")
            items.append({
                "id": idx,
                "symbol": sym,
                "headline": headline,
                "thesis": thesis,
                "_source": ("overview", flag_key, overview[flag_key].index(item)),
            })
            idx += 1

    for i, item in enumerate(deep_dive):
        sym = item.get("symbol", "")
        headline = item.get("latest_news", item.get("action_reason", ""))
        thesis = thesis_map.get(sym, "Growth Play")
        items.append({
            "id": idx,
            "symbol": sym,
            "headline": headline,
            "thesis": thesis,
            "_source": ("deep_dive", i),
        })
        idx += 1

    if not items:
        return overview, deep_dive

    # Strip internal routing keys before sending to LLM
    items_for_llm = [
        {"id": it["id"], "symbol": it["symbol"],
         "headline": it["headline"], "thesis": it["thesis"]}
        for it in items
    ]

    prompt = _CRITIC_PROMPT.format(items_json=json.dumps(items_for_llm, ensure_ascii=False))

    try:
        response = llm_client.generate(prompt, use_grounding=False)
        raw = _strip_fences(response.text)
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            classifications = []
            for k, v in parsed.items():
                if isinstance(v, list):
                    classifications = v
                    break
            if not classifications:
                classifications = [parsed]
        else:
            classifications = parsed

        # Build id → classification lookup
        quality_map = {c["id"]: c["classification"] for c in classifications}
        reason_map  = {c["id"]: c.get("reason", "") for c in classifications}

        # Apply quality tags back to the original dicts
        for meta in items:
            q = quality_map.get(meta["id"], "NOISE")
            r = reason_map.get(meta["id"], "")
            src = meta["_source"]

            if src[0] == "overview":
                _, flag_key, pos = src
                overview[flag_key][pos]["quality"] = q
                overview[flag_key][pos]["quality_reason"] = r
            else:
                _, pos = src
                deep_dive[pos]["quality"] = q
                deep_dive[pos]["quality_reason"] = r

        n_signal = sum(1 for c in classifications if c["classification"] == "SIGNAL")
        n_noise  = len(classifications) - n_signal
        logger.info(f"[Critic] ✓ Quality filter done — 🔥 {n_signal} SIGNAL  📉 {n_noise} NOISE")

    except Exception as e:
        logger.warning(f"[Critic] ⚠️  Quality classification failed: {e}. Defaulting all to SIGNAL.")
        # Fail open: mark everything SIGNAL so nothing is silently dropped
        for meta in items:
            src = meta["_source"]
            if src[0] == "overview":
                _, flag_key, pos = src
                overview[flag_key][pos]["quality"] = "SIGNAL"
            else:
                _, pos = src
                deep_dive[pos]["quality"] = "SIGNAL"

    return overview, deep_dive


# ── Orchestrator ──────────────────────────────────────────────────────────────

def fetch_portfolio_analyses(
    df: pd.DataFrame,
    thesis_map: dict[str, str] | None = None,
) -> dict:
    """
    Orchestrate the 3-call portfolio analysis pipeline.

      Call 1: Portfolio Overview  — qualitative red/green flags across all holdings
      Call 2: Deep Dive           — per-ticker detail only for flagged names
      Call 3: Quality Critic      — SIGNAL / NOISE classification (no grounding)

    Quantities are masked before either call.

    Args:
        df:         Raw portfolio DataFrame.
        thesis_map: Optional ticker → thesis mapping for the Critic.
                    If omitted the Critic still runs with a generic thesis.

    Returns:
        {
            "overview":   dict   (from fetch_portfolio_overview, items tagged with quality),
            "deep_dive":  list   (from fetch_flagged_deep_dive, items tagged with quality),
        }
    """
    thesis_map = thesis_map or {}

    # ── PRIVACY GATE ─────────────────────────────────────────────────────────
    overview = fetch_portfolio_overview(df)

    # Collect all flagged symbols (green + red) for the deep dive
    green_symbols = [f["symbol"] for f in overview.get("green_flags", [])]
    red_symbols   = [f["symbol"] for f in overview.get("red_flags",   [])]
    flagged       = list(dict.fromkeys(green_symbols + red_symbols))

    # Rate limit protection between calls 1 → 2
    if flagged:
        time.sleep(30)

    deep_dive = fetch_flagged_deep_dive(df, flagged)

    # ── Call 3: Quality Critic ────────────────────────────────────────────────
    # Short pause before the critic call (no grounding, so lighter)
    time.sleep(5)
    overview, deep_dive = classify_news_items(overview, deep_dive, thesis_map)

    return {"overview": overview, "deep_dive": deep_dive}




# ---------------------------------------------------------------------------
# 6. Live Scout Suggestions (refreshed on every run via Google Search)
# ---------------------------------------------------------------------------

SCOUT_JSON_PATH = os.path.join(os.path.dirname(__file__), "scout_suggestions.json")

_SCOUT_PROMPT = """\
You are a senior Indian equity research analyst with access to live market data \
via Google Search. Today's date is {today}.

Search for the TOP 3 most interesting Indian stock market opportunities RIGHT NOW \
(as of today, {today}). Use high-quality sources like Economic Times, Moneycontrol, and Livemint. \
Focus on stocks that have clear momentum catalysts, analyst upgrades, policy tailwinds, or earnings surprises TODAY or in the past 48 hours.

Return ONLY a valid JSON object — no explanation, no markdown fences — \
in this exact schema:

{{
  "date": "{today}",
  "analyst_note": "<1-sentence summary of today's broad market mood>",
  "scout_suggestions": [
    {{
      "rank": 1,
      "sector": "<sector name>",
      "stock": "<full company name>",
      "ticker": "<NSE ticker symbol>",
      "exchange": "NSE",
      "current_price_inr": <number>,
      "change_percent": "<e.g. +3.2% or -1.1%>",
      "research_source": "<news source or analyst house>",
      "why": "<2-3 sentence catalyst explanation grounded in today's news>"
    }},
    {{ "rank": 2, ... }},
    {{ "rank": 3, ... }}
  ]
}}

Rules:
- Tickers must be valid NSE symbols (e.g. RELIANCE, HDFCBANK, INFY).
- current_price_inr must be a real number (no quotes).
- Base every pick on real, searchable news from today or the past 48 hours.
- Do NOT invent data. If markets are closed or data is unavailable, still return \
  the 3 most relevant recent catalysts.
- Return ONLY the JSON object — no markdown, no ```json fences.
"""


def fetch_scout_suggestions(save_to_file: bool = True) -> list[dict]:
    """
    Use Gemini 2.5 Flash + Google Search to generate 3 fresh market scout
    picks for **today**, then persist the result to scout_suggestions.json.

    Called automatically by main.py on every run — replaces the old static file.

    Args:
        save_to_file: If True (default), writes the fresh picks to
                      scout_suggestions.json so there is always a recent copy
                      available as a fallback.

    Returns:
        List of suggestion dicts (same schema as the old static JSON).
        Falls back to the existing scout_suggestions.json if the API call fails.
    """
    from datetime import date as _date
    today_str = _date.today().strftime("%Y-%m-%d")

    # logger.info("\n[Scout] Fetching live scout suggestions via Gemini + Google Search...")

    prompt = _SCOUT_PROMPT.format(today=today_str)

    try:
        response = llm_client.generate(prompt, use_grounding=True)

        raw_text = _strip_fences(response.text)
        data = json.loads(raw_text)

        suggestions = data.get("scout_suggestions", [])
        if not suggestions:
            raise ValueError("Gemini returned no suggestions in the JSON.")

        # logger.info(f"[Scout] ✓ {len(suggestions)} fresh picks received for {today_str}.")

        if save_to_file:
            with open(SCOUT_JSON_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            # logger.info(f"[Scout] ✓ Saved to {os.path.basename(SCOUT_JSON_PATH)}")

        return suggestions

    except Exception as e:
        logger.warning(f"[Scout] ⚠️  Live fetch failed ({e}). Falling back to cached file.")
        # Graceful fallback — use last saved file if available
        if os.path.exists(SCOUT_JSON_PATH):
            try:
                with open(SCOUT_JSON_PATH, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                fallback = cached.get("scout_suggestions") or cached.get("suggestions", [])
                logger.info(f"[Scout] ↩  Using {len(fallback)} cached suggestions.")
                return fallback
            except Exception as fe:
                logger.error(f"[Scout] ❌ Cache read also failed: {fe}")
        return []


# ---------------------------------------------------------------------------
# 7. Convenience Helpers
# ---------------------------------------------------------------------------

def get_equity_holdings(df: pd.DataFrame) -> pd.DataFrame:
    """Filter only direct equity holdings (excludes MFs and ETFs)."""
    return df[df["Instrument Type"] == "Equity"].reset_index(drop=True)


def get_mutual_fund_holdings(df: pd.DataFrame) -> pd.DataFrame:
    """Filter only mutual fund holdings."""
    return df[df["Instrument Type"] == "Mutual Fund"].reset_index(drop=True)


def get_portfolio_summary(df: pd.DataFrame) -> dict:
    """
    Return a high-level portfolio summary dict (no Quantity data).
    """
    return {
        "total_holdings": len(df),
        "sectors": df["Sector"].value_counts().to_dict(),
        "instrument_types": df["Instrument Type"].value_counts().to_dict(),
        "top_gainers": (
            df.nlargest(5, "Unrealized P&L Pct.")[["Symbol", "Unrealized P&L Pct."]]
            .to_dict(orient="records")
        ),
        "top_losers": (
            df.nsmallest(5, "Unrealized P&L Pct.")[["Symbol", "Unrealized P&L Pct."]]
            .to_dict(orient="records")
        ),
    }


# ---------------------------------------------------------------------------
# 7. Quick Smoke Test (run directly: python core.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("  Portfolio Pulse — Core Engine Smoke Test")
    logger.info("=" * 60)

    # Load portfolio
    portfolio_df = load_portfolio()

    # Summary (no private data)
    summary = get_portfolio_summary(portfolio_df)
    logger.info("\n[Summary]")
    logger.info(json.dumps(summary, indent=2, default=str))

    # Test quantity masking
    masked_df = mask_quantity(portfolio_df)
    logger.info("\n[Privacy Check] Quantity masking sample (first 3 rows):")
    logger.info(masked_df[["Symbol", "Quantity Available"]].head(3).to_string(index=False))

    # Test single ticker analysis (only the first equity holding)
    equities = get_equity_holdings(portfolio_df)
    if not equities.empty:
        safe_equities = mask_quantity(equities)
        first_row = safe_equities.iloc[0]
        logger.info(f"\n[Test] Fetching single analysis for: {first_row['Symbol']}")
        result = fetch_analysis_for_ticker(first_row)
        logger.info("\n--- Analysis Result ---")
        logger.info(result["analysis"])
        if result["grounding_sources"]:
            logger.info("\nGrounding Sources:")
            for url in result["grounding_sources"]:
                logger.info(f"  • {url}")
    else:
        logger.info("\n[Test] No equity holdings found for analysis test.")

    logger.info("\n[Done] Smoke test complete.")
