"""
main.py - Portfolio Pulse
=========================
The Final Orchestrator.

Ties together:
  - portfolio.csv          → raw cleaned portfolio data
  - thesis_manager.py      → per-ticker investment thesis persistence & inference
  - core.py                → Gemini 2.5 Flash 3-call analysis (overview, deep-dive, critic)
  - scout_suggestions.json → new stock picks from market research
  - telegram_notifier.py   → formats and sends the Telegram briefing

Usage:
  python main.py               # Full run (live Gemini + Telegram)
  python main.py --dry-run     # Preview report, no Telegram send
  python main.py --equity-only # Only analyse equity holdings
  python main.py --fix TICKER "New Thesis"  # Manually correct a thesis
"""
from loguru import logger

import argparse
import os
import sys
import json
import time
from datetime import datetime
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# 0. Load environment FIRST so all downstream imports see it
# ---------------------------------------------------------------------------
load_dotenv()

# ---------------------------------------------------------------------------
# 1. Environment Validation
# ---------------------------------------------------------------------------

REQUIRED_KEYS = {
    "TELEGRAM_BOT_TOKEN"  : "Telegram Bot Token — via @BotFather",
    "TELEGRAM_CHAT_ID"    : "Your Telegram Chat ID — via @userinfobot",
}

# GEMINI_API_KEY is only required when using the Gemini provider
if os.getenv("LLM_PROVIDER", "gemini").strip().lower() == "gemini":
    REQUIRED_KEYS["GEMINI_API_KEY"] = "Gemini API key — https://aistudio.google.com/app/apikey"

_PLACEHOLDER_PREFIXES = ("your_", "replace_", "<")


def validate_env() -> list[tuple[str, str]]:
    """
    Return a list of (key, description) tuples for every missing or
    placeholder-valued environment variable.
    """
    missing = []
    for key, desc in REQUIRED_KEYS.items():
        value = os.getenv(key, "").strip()
        if not value or any(value.startswith(p) for p in _PLACEHOLDER_PREFIXES):
            missing.append((key, desc))
    return missing


def abort_with_missing_keys(missing: list[tuple[str, str]]) -> None:
    """Print a clear, actionable error and exit."""
    logger.info("\n" + "=" * 65)
    logger.error("  ❌  Portfolio Pulse — Configuration Error")
    logger.info("=" * 65)
    logger.info(
        "\n  The following required environment variables are missing\n"
        "  or still contain placeholder values in your .env file:\n"
    )
    for key, desc in missing:
        logger.error(f"    ✗  {key}")
        logger.info(f"         └─ {desc}\n")
    logger.info("  ─" * 33)
    logger.info(
        "\n  How to fix:\n"
        "    1. Open  .env  (same directory as main.py)\n"
        "    2. Replace each placeholder with a real value.\n"
        "    3. Re-run:  python main.py\n"
    )
    logger.info("=" * 65 + "\n")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 2. Local module imports (after env is loaded)
# ---------------------------------------------------------------------------

import pandas as pd
import core
import telegram_notifier
from thesis_manager import ThesisManager

# ---------------------------------------------------------------------------
# 3. Paths
# ---------------------------------------------------------------------------

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
PORTFOLIO_CSV = os.path.join(BASE_DIR, "portfolio.csv")
SCOUT_JSON    = os.path.join(BASE_DIR, "scout_suggestions.json")

# ---------------------------------------------------------------------------
# 4. Helper functions
# ---------------------------------------------------------------------------

def load_portfolio_csv(path: str = PORTFOLIO_CSV) -> pd.DataFrame:
    """Load and return the cleaned portfolio DataFrame using the robust ingestion engine."""
    from ingestion.csv_source import CSVPortfolioSource
    try:
        source = CSVPortfolioSource(csv_path=path)
        return source.get_dataframe()
    except Exception as e:
        logger.error(f"[ERROR] Loading portfolio failed: {e}")
        sys.exit(1)


def load_scout_suggestions() -> list[dict]:
    """
    Fetch LIVE scout suggestions via Gemini + Google Search.

    On every run, this calls core.fetch_scout_suggestions() which:
      1. Asks Gemini (with Google Search grounding) for today's top 3 picks.
      2. Saves the fresh picks to scout_suggestions.json as a cache.
      3. Falls back to the cached JSON if the live call fails.
    """
    # logger.info("[2/5] Fetching live scout suggestions (Gemini + Google Search)...")
    suggestions = core.fetch_scout_suggestions(save_to_file=True)
    # logger.info(f"      ✓ {len(suggestions)} scout picks ready.")
    return suggestions


def get_news_analyses(
    df: pd.DataFrame,
    equity_only: bool = False,
    thesis_map: dict | None = None,
) -> dict:
    """
    Run the 3-call portfolio analysis pipeline via core.py.
    Returns {"overview": dict, "deep_dive": list} — with SIGNAL/NOISE quality tags.
    Quantity masking is enforced inside core.py.
    """
    target_df = core.get_equity_holdings(df) if equity_only else df
    result = core.fetch_portfolio_analyses(target_df, thesis_map=thesis_map or {})
    n_green = len(result["overview"].get("green_flags", []))
    n_red   = len(result["overview"].get("red_flags",   []))
    n_dive  = len(result["deep_dive"])
    return result


def build_portfolio_snapshot(df: pd.DataFrame) -> dict:
    """Derive a financial snapshot from the cleaned portfolio DataFrame."""
    avg_prices   = pd.to_numeric(df["Average Price"], errors="coerce")
    quantities   = pd.to_numeric(df["Quantity Available"], errors="coerce")
    close_prices = pd.to_numeric(df["Previous Closing Price"], errors="coerce")
    pnl_values   = pd.to_numeric(df["Unrealized P&L"], errors="coerce")

    invested_value  = (avg_prices * quantities).sum()
    present_value   = (close_prices * quantities).sum()
    unrealized_pnl  = pnl_values.sum()
    pnl_pct         = (unrealized_pnl / invested_value * 100) if invested_value else 0.0

    return {
        "invested_value" : round(invested_value, 2),
        "present_value"  : round(present_value, 2),
        "unrealized_pnl" : round(unrealized_pnl, 2),
        "pnl_pct"        : round(pnl_pct, 2),
        "total_holdings" : len(df),
    }


def merge_briefing(
    df: pd.DataFrame,
    analyses: dict,
    scout_suggestions: list[dict],
    new_tickers_thesis: dict[str, str] | None = None,
) -> dict:
    """
    Merge all data sources into a single Portfolio Briefing dict.

    analyses must be the dict returned by get_news_analyses:
      {"overview": {...}, "deep_dive": [...]}

    new_tickers_thesis: ticker → thesis for tickers inferred this run.
    """
    snapshot = build_portfolio_snapshot(df)
    summary  = core.get_portfolio_summary(df)

    pnl_lookup = dict(
        zip(
            df["Symbol"].tolist(),
            pd.to_numeric(df["Unrealized P&L Pct."], errors="coerce").tolist(),
        )
    )

    briefing = {
        "date"               : datetime.now().strftime("%Y-%m-%d"),
        "generated_at"       : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "portfolio_snapshot" : snapshot,
        "portfolio_summary"  : summary,
        "portfolio_overview" : analyses.get("overview", {}),
        "deep_dive"          : analyses.get("deep_dive", []),
        "scout_suggestions"  : scout_suggestions,
        "portfolio_df_pnl"   : pnl_lookup,
        "new_tickers_thesis" : new_tickers_thesis or {},
    }
    return briefing


def print_console_summary(briefing: dict) -> None:
    """Pretty-print a human-readable briefing summary to stdout."""
    snap  = briefing["portfolio_snapshot"]
    overview = briefing.get("portfolio_overview", {})

    logger.info("\n" + "=" * 65)
    logger.info("  📊  PORTFOLIO PULSE — DAILY BRIEFING")
    logger.info("=" * 65)
    logger.info(f"\n  Date        : {briefing['date']}")
    logger.info(f"  Holdings    : {snap['total_holdings']}")
    logger.info(f"  Invested    : ₹{snap['invested_value']:>14,.2f}")
    logger.info(f"  Present Val : ₹{snap['present_value']:>14,.2f}")
    logger.info(f"  Unrealized  : ₹{snap['unrealized_pnl']:>14,.2f}")
    logger.info(f"  P&L %       :  {snap['pnl_pct']:>13.2f}%\n")

    health    = overview.get("portfolio_health", "N/A")
    rationale = overview.get("portfolio_health_rationale", "")
    logger.info(f"  📈 Portfolio Health : {health}")
    if rationale:
        logger.info(f"     {rationale}")

    green_flags = overview.get("green_flags", [])
    red_flags   = overview.get("red_flags",   [])
    neutral     = overview.get("neutral_watch", [])

    if green_flags:
        logger.info(f"\n  🟢 Green Flags ({len(green_flags)}):")
        for g in green_flags:
            logger.info(f"     {g.get('symbol',''):18s}  {g.get('headline','')[:60]}")

    if red_flags:
        logger.info(f"\n  🔴 Red Flags ({len(red_flags)}):")
        for r in red_flags:
            logger.info(f"     {r.get('symbol',''):18s}  {r.get('headline','')[:60]}")

    if neutral:
        logger.info(f"\n  👁  Watch List ({len(neutral)}):")
        for w in neutral:
            logger.info(f"     {w.get('symbol',''):18s}  {w.get('reason','')[:60]}")

    deep_dive = briefing.get("deep_dive", [])
    if deep_dive:
        logger.info(f"\n  🔍 Deep Dive ({len(deep_dive)} flagged holdings):")
        for d in deep_dive:
            signal = d.get("action_signal", "HOLD")
            emoji  = {"BUY MORE": "🟢", "HOLD": "🟡", "CONSIDER EXIT": "🔴"}.get(signal, "⚪")
            logger.info(f"     {emoji} {d.get('symbol',''):18s}  {signal:15s}  {d.get('action_reason','')[:45]}")

    scouts = briefing.get("scout_suggestions", [])
    if scouts:
        logger.info(f"\n  🔭 Scout Picks ({len(scouts)} ideas):")
        for s in scouts:
            sym    = s.get('ticker') or s.get('symbol', 'N/A')
            price  = s.get('current_price_inr') or s.get('current_price', 'N/A')
            reason = s.get('why') or s.get('rationale', '')
            logger.info(f"     {sym:12s} @ ₹{str(price):<8}  {reason[:55]}...")

    logger.info("\n" + "=" * 65)


def trigger_telegram(briefing: dict, dry_run: bool = False) -> None:
    """
    Format the Portfolio Briefing as a Telegram message and send it.
    In dry-run mode, only prints the preview without sending.
    """
    # logger.info(f"[5/5] {'[DRY-RUN] Previewing' if dry_run else 'Sending'} "
    #       f"Portfolio Briefing via Telegram...")

    formatted = telegram_notifier.build_telegram_report(briefing)

    # logger.info("\n" + "-" * 65)
    # logger.info("  Telegram Message Preview:")
    # logger.info("-" * 65)
    # logger.info(formatted)
    # logger.info("-" * 65)
    # logger.info(f"  Message length: {len(formatted)} characters")

    if dry_run:
        logger.info("\n  [DRY-RUN] No message sent. Remove --dry-run to send live.")
        return

    # Live send
    try:
        success = telegram_notifier.send_telegram_update(formatted)
        # if success:
        #     logger.info(f"\n  ✅ Telegram briefing sent!")
        if not success:
            logger.error(f"\n  ❌ Telegram send failed (check logs above)")
    except ValueError as ve:
        # Missing credentials — surface gracefully
        logger.warning(f"\n  ⚠️  Telegram send skipped:\n{ve}")
    except Exception as exc:
        logger.error(f"\n  ❌ Telegram send failed: {exc}")

# ---------------------------------------------------------------------------
# 5. CLI Argument Parsing
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Portfolio Pulse — AI-powered portfolio briefing via Telegram"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the formatted Telegram message without sending it.",
    )
    parser.add_argument(
        "--equity-only",
        action="store_true",
        help="Analyse only direct equity holdings (skip MFs and ETFs).",
    )
    parser.add_argument(
        "--fix",
        nargs=2,
        metavar=("TICKER", "THESIS"),
        help="Manually set the investment thesis for a ticker. "
             "Example: --fix SBIN 'Recovery Bet'",
    )
    return parser.parse_args()

# ---------------------------------------------------------------------------
# 6. Main Entry Point
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    # ── Step 0: Validate .env ────────────────────────────────────────────────
    missing_keys = validate_env()
    if missing_keys:
        abort_with_missing_keys(missing_keys)

    # Log active LLM provider
    from logic import llm_client
    logger.info(f"[Config] LLM Provider: {llm_client.get_provider().upper()}")

    # ── Step 1: Load portfolio.csv ───────────────────────────────────────────
    df = load_portfolio_csv()

    # ── Step 1b: Handle --fix (manual thesis correction) ────────────────────
    thesis_manager = ThesisManager()
    if args.fix:
        ticker_fix, thesis_fix = args.fix[0].upper(), args.fix[1]
        thesis_manager.update_thesis(ticker_fix, thesis_fix)
        logger.info(f"\n  ✅ Thesis for {ticker_fix} updated to: '{thesis_fix}'")
        logger.info("  Run again without --fix to regenerate the full report.\n")
        return

    # ── Step 2: Load scout_suggestions.json ─────────────────────────────────
    scouts = load_scout_suggestions()

    # Rate limit: pause after scout call before thesis inference
    time.sleep(15)

    # ── Step 3: Build thesis map for all tickers ─────────────────────────────
    target_df = core.get_equity_holdings(df) if args.equity_only else df
    tickers_sectors = list(
        zip(target_df["Symbol"].tolist(), target_df["Sector"].tolist())
    )
    thesis_map = thesis_manager.build_thesis_map(tickers_sectors)

    # ── Step 4: Get news analyses from core.py ───────────────────────────────
    analyses = get_news_analyses(df, equity_only=args.equity_only, thesis_map=thesis_map)

    # ── Step 5: Merge into one Portfolio Briefing ────────────────────────────
    new_thesis_info = {
        t: thesis_map[t]
        for t in thesis_manager.get_new_tickers()
        if t in thesis_map
    }
    briefing = merge_briefing(df, analyses, scouts, new_tickers_thesis=new_thesis_info)

    # ── Step 6: Trigger Telegram notification ────────────────────────────────
    trigger_telegram(briefing, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
