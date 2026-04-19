"""
telegram_notifier.py — Portfolio Pulse: Telegram Delivery Layer
================================================================
Integration Specialist — The Telegram Expert

Responsibilities:
  - Load Telegram Bot credentials from .env
  - Format the portfolio analysis report in Telegram-friendly MarkdownV2
  - Lead with 🔥 High-Signal Intel (SIGNAL items) / 📉 Market Noise / FYI (NOISE items)
  - Append thesis inference notes for new tickers
  - Send the formatted report via Telegram Bot API
  - Support message splitting for Telegram's character limits
"""
from loguru import logger

import os
import re
import requests
from datetime import datetime
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# 1. Load Environment
# ---------------------------------------------------------------------------

load_dotenv()

_REQUIRED_ENV_VARS = [
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
]

def _load_credentials() -> dict:
    """Read Telegram credentials from .env."""
    creds = {}
    missing = []
    for key in _REQUIRED_ENV_VARS:
        value = os.getenv(key, "").strip()
        if not value or value.startswith("your_"):
            missing.append(key)
        else:
            creds[key] = value

    if missing:
        raise ValueError(
            f"Missing or placeholder credentials in .env:\n"
            + "\n".join(f"  • {k}" for k in missing)
            + "\n\nPlease update your .env file with real Telegram credentials."
        )
    return creds

# ---------------------------------------------------------------------------
# 2. Telegram Markdown Formatter
# ---------------------------------------------------------------------------

def escape_markdown_v2(text: str) -> str:
    """
    Escape special characters for Telegram MarkdownV2.
    Characters: _ * [ ] ( ) ~ ` > # + - = | { } . !
    """
    if not text:
        return ""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', str(text))


def _flag_line(item: dict, flag_type: str) -> str:
    """
    Format a single flag/watch item as a Telegram MarkdownV2 bullet.

    flag_type: "green" | "red" | "neutral" | "deep_dive"
    """
    sym = item.get("symbol", "")
    reason = item.get("reason") or item.get("action_reason") or item.get("analyst_rationale", "")
    headline = item.get("headline", "")

    if flag_type == "deep_dive":
        sig = item.get("action_signal", "HOLD")
        sig_emoji = {"BUY MORE": "🟢", "TRIM": "🟠", "HOLD": "🟡", "CONSIDER EXIT": "🔴"}.get(sig, "⚪")
        return (
            f"\n*{escape_markdown_v2(sym)}*: {sig_emoji} *{escape_markdown_v2(sig)}*\n"
            f"_{escape_markdown_v2(reason)}_"
        )
    else:
        flag_emoji = {"green": "🟢", "red": "🔴", "neutral": "👁"}.get(flag_type, "•")
        display = headline or reason
        return f"\n{flag_emoji} *{escape_markdown_v2(sym)}*: {escape_markdown_v2(display)}"


def _collect_signal_noise(
    overview: dict,
    deep_dive: list[dict],
) -> tuple[list[tuple[str, dict]], list[tuple[str, dict]]]:
    """
    Split all items into (SIGNAL, NOISE) buckets.

    Returns:
        signals: list of (flag_type_str, item_dict)
        noise:   list of (flag_type_str, item_dict)
    """
    signals: list[tuple[str, dict]] = []
    noise:   list[tuple[str, dict]] = []

    for item in overview.get("green_flags", []):
        bucket = signals if item.get("quality", "SIGNAL") == "SIGNAL" else noise
        bucket.append(("green", item))

    for item in overview.get("red_flags", []):
        bucket = signals if item.get("quality", "SIGNAL") == "SIGNAL" else noise
        bucket.append(("red", item))

    for item in overview.get("neutral_watch", []):
        bucket = signals if item.get("quality", "SIGNAL") == "SIGNAL" else noise
        bucket.append(("neutral", item))

    for item in deep_dive:
        bucket = signals if item.get("quality", "SIGNAL") == "SIGNAL" else noise
        bucket.append(("deep_dive", item))

    return signals, noise


def build_telegram_report(briefing: dict) -> str:
    """Build a structured Telegram report from the briefing dict."""
    overview   = briefing.get("portfolio_overview", {})
    deep_dive  = briefing.get("deep_dive", [])
    scouts     = briefing.get("scout_suggestions", [])
    snap       = briefing.get("portfolio_snapshot", {})
    new_tickers: dict[str, str] = briefing.get("new_tickers_thesis", {})

    today_display = datetime.now().strftime("%d %b %Y")

    lines = []
    lines.append(f"🤖 *PORTFOLIO PULSE REPORT*")
    lines.append(f"_Generated on {escape_markdown_v2(today_display)}_")
    lines.append(escape_markdown_v2("─" * 20))

    # ── Portfolio snapshot ────────────────────────────────────────────────────
    if snap:
        pnl_pct = snap.get("pnl_pct", 0.0)
        pnl_emoji = "🟢" if pnl_pct >= 0 else "🔴"
        val = f"₹{snap.get('present_value', 0):,.0f}"
        pnl_str = escape_markdown_v2(f"{pnl_pct:+.2f}%")
        val_str = escape_markdown_v2(val)
        lines.append(
            f"\n{pnl_emoji} *Portfolio:* {escape_markdown_v2(snap.get('total_holdings', '?'))} holdings\n"
            f"P&L: *{pnl_str}* {escape_markdown_v2('|')} Val: {val_str}"
        )

    # ── Market Sentiment ──────────────────────────────────────────────────────
    lines.append(f"\n\n📊 *MARKET SENTIMENT*")
    health = overview.get("portfolio_health", "Neutral")
    emoji = {"Bullish": "🟢", "Bearish": "🔴", "Neutral": "🟡"}.get(health, "🟡")
    lines.append(f"*{emoji} {escape_markdown_v2(health)}*")
    if overview.get("market_overview"):
        lines.append(escape_markdown_v2(overview["market_overview"]))

    # ── Classify items ────────────────────────────────────────────────────────
    signals, noise_items = _collect_signal_noise(overview, deep_dive)

    # Check if quality tags exist at all (critic may have been skipped)
    has_quality_tags = any(
        "quality" in item
        for bucket in (
            overview.get("green_flags", []),
            overview.get("red_flags", []),
            overview.get("neutral_watch", []),
            deep_dive,
        )
        for item in bucket
    )

    if has_quality_tags:
        # ── 🔥 High-Signal Intel ─────────────────────────────────────────────
        if signals:
            lines.append(f"\n\n🔥 *HIGH\\-SIGNAL INTEL*")
            for flag_type, item in signals:
                lines.append(_flag_line(item, flag_type))

    else:
        # ── Fallback: old format (no quality tags) ────────────────────────────
        if overview.get("green_flags"):
            lines.append(f"\n\n🟢 *GREEN FLAGS*")
            for f in overview["green_flags"]:
                lines.append(f"\n• *{escape_markdown_v2(f.get('symbol',''))}*: {escape_markdown_v2(f.get('reason',''))}")

        if overview.get("red_flags"):
            lines.append(f"\n\n🔴 *RED FLAGS*")
            for f in overview["red_flags"]:
                lines.append(f"\n• *{escape_markdown_v2(f.get('symbol',''))}*: {escape_markdown_v2(f.get('reason',''))}")

        if deep_dive:
            lines.append(f"\n\n🔍 *ACTION SIGNALS*")
            for d in deep_dive:
                sig = d.get("action_signal", "HOLD")
                sig_emoji = {"BUY MORE": "🟢", "TRIM": "🟠", "HOLD": "🟡", "CONSIDER EXIT": "🔴"}.get(sig, "⚪")
                lines.append(f"\n*{escape_markdown_v2(d.get('symbol',''))}*: {sig_emoji} *{escape_markdown_v2(sig)}*")
                lines.append(f"_{escape_markdown_v2(d.get('action_reason',''))}_")

    # ── 🆕 Thesis Notes (Removed per user request) ───────────────────────────

    # ── 🔭 Scout Picks ────────────────────────────────────────────────────────
    if scouts:
        lines.append(f"\n\n🔭 *SCOUT PICKS*")
        for s in scouts:
            sym = s.get("ticker") or s.get("symbol", "N/A")
            price = s.get("current_price_inr") or s.get("current_price", "N/A")
            lines.append(f"\n• *{escape_markdown_v2(sym)}* @ ₹{escape_markdown_v2(str(price))}")
            lines.append(f"  _{escape_markdown_v2(s.get('why', ''))}_")

    lines.append(f"\n{escape_markdown_v2('─' * 20)}")
    lines.append(f"_{escape_markdown_v2('⚡ AI-generated. Not financial advice.')}_")

    return "\n".join(lines)

# ---------------------------------------------------------------------------
# 3. Send Telegram Message
# ---------------------------------------------------------------------------

def send_telegram_update(report_text: str) -> bool:
    """Send formatted report via Telegram Bot API."""
    creds = _load_credentials()
    token = creds["TELEGRAM_BOT_TOKEN"]
    chat_id = creds["TELEGRAM_CHAT_ID"]
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    # Telegram limit is 4096 chars. Split safely by lines to avoid breaking Markdown entities.
    MAX_LEN = 4000 
    chunks = []
    current_chunk = []
    current_length = 0
    
    for line in report_text.split('\n'):
        line_len = len(line) + 1 
        
        if line_len > MAX_LEN:
            if current_chunk:
                chunks.append('\n'.join(current_chunk))
                current_chunk = []
                current_length = 0
            for i in range(0, len(line), MAX_LEN):
                chunks.append(line[i:i+MAX_LEN])
            continue

        if current_length + line_len > MAX_LEN:
            chunks.append('\n'.join(current_chunk))
            current_chunk = [line]
            current_length = line_len
        else:
            current_chunk.append(line)
            current_length += line_len
            
    if current_chunk:
        chunks.append('\n'.join(current_chunk))
    
    success = True
    for chunk in chunks:
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "MarkdownV2"
        }
        resp = requests.post(url, json=payload)
        if not resp.ok:
            logger.error(f"  [Telegram] Error: {resp.text}")
            success = False
            
    return success

if __name__ == "__main__":
    logger.info("Telegram Notifier Dry Run")
    test_briefing = {
        "portfolio_overview": {
            "portfolio_health": "Bullish",
            "market_overview": "Market is strong.",
            "green_flags": [
                {"symbol": "SBIN", "headline": "SBIN Q3 up 84%", "reason": "Strong earnings.", "quality": "SIGNAL"},
            ],
            "red_flags": [
                {"symbol": "TCS", "headline": "Deal slowdown", "reason": "US spending cuts.", "quality": "NOISE"},
            ],
            "neutral_watch": [],
        },
        "deep_dive": [],
        "portfolio_snapshot": {"total_holdings": 5, "pnl_pct": 12.5, "present_value": 150000},
        "scout_suggestions": [],
        "new_tickers_thesis": {"SBIN": "PSU Re-rating"},
    }
    report = build_telegram_report(test_briefing)
    logger.info("-" * 30)
    logger.info(report)
    logger.info("-" * 30)
    logger.info("Check .env for credentials before live run.")
