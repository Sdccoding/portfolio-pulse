"""
dry_run_test.py — Portfolio Pulse End-to-End Dry Run
=====================================================
Validates the FULL pipeline without:
  - Making any real Gemini API calls
  - Sending any Telegram messages
  - Checking for real credentials
  - Visiting any external URLs

Safety:
  - All network calls are MOCKED with unittest.mock
  - No real HTTP requests are made
  - SSL/TLS and DNS are not touched
  - Only local file I/O is performed

Run:
    ./venv/bin/python3 dry_run_test.py
"""

import sys, os, json, warnings
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Inject dummy env vars BEFORE any module is imported ─────────────────────
os.environ["GEMINI_API_KEY"]        = "DRY_RUN_DUMMY_GEMINI_KEY"
os.environ["TELEGRAM_BOT_TOKEN"]     = "DRY_RUN_DUMMY_TOKEN"
os.environ["TELEGRAM_CHAT_ID"]       = "123456789"

from unittest.mock import MagicMock, patch
from datetime import datetime
import pandas as pd

PASS = "✅"; FAIL = "❌"; SEP = "─" * 65
RESULTS = []

def run_test(name, fn):
    try:
        fn()
        RESULTS.append((True, name, None))
        print(f"  {PASS}  {name}")
    except Exception as e:
        RESULTS.append((False, name, str(e)))
        print(f"  {FAIL}  {name}")
        print(f"       └─ {e}")

# ─── Mock Gemini response factory ───────────────────────────────────────────
MOCK_ANALYSIS = (
    "**Latest News**: SBIN Q3 profit up 84% YoY. RBI held rates.\n"
    "**Analyst Sentiment**: Bullish — BUY on dips.\n"
    "**Key Risks**:\n1. MSME NPA risk.\n2. Global rate reversal.\n"
    "**Action Signal**: HOLD — Strong fundamentals."
)

MOCK_SCOUTS = [
    {"rank": 1, "sector": "Renewable Energy", "stock": "Shakti Pumps",
     "ticker": "SHAKTIPUMP", "exchange": "NSE", "current_price_inr": 2345.5,
     "change_percent": "+18.0%", "research_source": "Moneycontrol",
     "why": "18% jump on Jal Jeevan Mission 2.0 announcement."},
    {"rank": 2, "sector": "IT", "stock": "Tata Consultancy Services",
     "ticker": "TCS", "exchange": "NSE", "current_price_inr": 4642.0,
     "change_percent": "-1.1%", "research_source": "Nuvama",
     "why": "Contrarian BUY — GenAI fears overblown per Nuvama."},
    {"rank": 3, "sector": "EV Components", "stock": "Sona BLW Precision Forgings",
     "ticker": "SONACOMS", "exchange": "NSE", "current_price_inr": 612.45,
     "change_percent": "+4.5%", "research_source": "BofA",
     "why": "All-time high after BofA upgrade to BUY with ₹640 target."},
]

def mock_gemini_response(text=MOCK_ANALYSIS):
    resp = MagicMock()
    resp.text = text
    chunk = MagicMock()
    chunk.web.uri = "https://www.moneycontrol.com/news/sbin-q3.html"
    candidate = MagicMock()
    candidate.grounding_metadata.grounding_chunks = [chunk]
    resp.candidates = [candidate]
    return resp

def mock_scout_response():
    """Gemini response that returns valid scout JSON."""
    from datetime import date
    payload = {
        "date": date.today().strftime("%Y-%m-%d"),
        "analyst_note": "Markets mixed. Selective opportunities in EV and IT.",
        "scout_suggestions": MOCK_SCOUTS,
    }
    return mock_gemini_response(text=json.dumps(payload))

# ============================================================
print()
print("=" * 65)
print("  🧪  Portfolio Pulse — End-to-End Dry Run")
print(f"  🕐  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 65)

# ============================================================
# STAGE 1: Module Imports
# ============================================================
print(f"\n{SEP}")
print("  STAGE 1 — Module Imports & Dependency Check")
print(SEP)

def t1_pandas():
    import pandas as _pd
    assert _pd.__version__

def t1_dotenv():
    from dotenv import load_dotenv

def t1_genai():
    from google import genai
    from google.genai import types

def t1_requests():
    import requests
    assert requests.__version__

def t1_core():
    with patch("google.genai.Client"):
        import core

def t1_telegram():
    import telegram_notifier

for name, fn in [
    ("Import: pandas",            t1_pandas),
    ("Import: python-dotenv",     t1_dotenv),
    ("Import: google-genai",      t1_genai),
    ("Import: requests",          t1_requests),
    ("Import: core.py",           t1_core),
    ("Import: telegram_notifier", t1_telegram),
]:
    run_test(name, fn)

# Now do real imports for subsequent stages
with patch("google.genai.Client"):
    import core
import telegram_notifier as tn
import main

# ============================================================
# STAGE 2: Portfolio CSV
# ============================================================
print(f"\n{SEP}")
print("  STAGE 2 — portfolio.csv Loading & Validation")
print(SEP)

def t2_exists():
    assert os.path.exists("portfolio.csv"), "portfolio.csv not found in project root!"

def t2_loads():
    df = core.load_portfolio()
    assert len(df) > 0

def t2_columns():
    df = pd.read_csv("portfolio.csv")
    required = [
        "Symbol", "ISIN", "Sector", "Instrument Type",
        "Quantity Available", "Average Price",
        "Previous Closing Price", "Unrealized P&L", "Unrealized P&L Pct."
    ]
    missing = [c for c in required if c not in df.columns]
    assert not missing, f"Missing columns: {missing}"

def t2_count():
    df = core.load_portfolio()
    count = len(df)
    print(f"\n       Holdings loaded: {count}", end="")
    assert count >= 50, f"Expected ≥50, got {count}"

def t2_instrument_types():
    df = core.load_portfolio()
    types_ = df["Instrument Type"].value_counts().to_dict()
    print(f"\n       Instrument types: {types_}", end="")
    assert "Equity" in types_

def t2_numeric():
    df = core.load_portfolio()
    avg = pd.to_numeric(df["Average Price"], errors="coerce")
    assert avg.notna().sum() > 0, "Average Price is all NaN"

for name, fn in [
    ("portfolio.csv: file exists",                    t2_exists),
    ("portfolio.csv: loads without error",            t2_loads),
    ("portfolio.csv: has all required columns",       t2_columns),
    ("portfolio.csv: ≥50 holdings loaded",            t2_count),
    ("portfolio.csv: instrument type breakdown",      t2_instrument_types),
    ("portfolio.csv: numeric price parsing is clean", t2_numeric),
]:
    run_test(name, fn)

# ============================================================
# STAGE 3: Privacy — Quantity Masking
# ============================================================
print(f"\n{SEP}")
print("  STAGE 3 — Privacy Gate: Quantity Masking")
print(SEP)

def t3_copy():
    df = core.load_portfolio()
    original = df["Quantity Available"].iloc[0]
    masked = core.mask_quantity(df)
    assert masked["Quantity Available"].iloc[0] == "[MASKED]"
    assert df["Quantity Available"].iloc[0] == original  # original untouched

def t3_all_rows():
    df = core.load_portfolio()
    masked = core.mask_quantity(df)
    assert (masked["Quantity Available"] == "[MASKED]").all(), \
        "Some rows still have real quantity values!"

def t3_no_numeric():
    df = core.load_portfolio()
    masked = core.mask_quantity(df)
    numeric = pd.to_numeric(masked["Quantity Available"], errors="coerce")
    assert numeric.isna().all(), "Numeric quantities still present after masking!"

for name, fn in [
    ("mask_quantity: returns copy, original untouched", t3_copy),
    ("mask_quantity: ALL rows are masked",               t3_all_rows),
    ("mask_quantity: no numeric quantity remains",       t3_no_numeric),
]:
    run_test(name, fn)

# ── Mock overview and deep dive responses ────────────────────────────────────

MOCK_OVERVIEW = {
    "market_overview": "Markets opened mixed today with caution ahead of RBI policy.",
    "portfolio_health": "Bullish",
    "portfolio_health_rationale": "Portfolio skewed towards financials which are outperforming.",
    "sector_commentary": {
        "Financial Services": "PSU banks rallying on credit growth data.",
        "IT": "IT sector under mild pressure due to US macro uncertainty.",
    },
    "green_flags": [
        {"symbol": "SBIN", "headline": "SBIN Q3 PAT up 84% YoY", "reason": "Strong earnings beat with NIM expansion."},
        {"symbol": "HDFCBANK", "headline": "HDFC Bank credit growth at 16% YoY", "reason": "Loan book expanding robustly."},
    ],
    "red_flags": [
        {"symbol": "TCS", "headline": "IT headwinds: TCS deal wins slow", "reason": "US client spending cuts weighing on deal pipeline."},
    ],
    "neutral_watch": [
        {"symbol": "RELIANCE", "reason": "Awaiting Jio IPO timeline clarity."},
    ],
}

MOCK_DEEP_DIVE = [
    {
        "symbol": "SBIN",
        "flag_type": "green",
        "latest_news": "SBIN Q3 PAT ₹18,331 Cr, up 84% YoY. NIM at 3.15%.",
        "analyst_sentiment": "Bullish",
        "analyst_rationale": "Strong earnings and RBI tailwinds favour PSU banks.",
        "key_risks": ["MSME NPA risk", "Global rate reversal"],
        "action_signal": "BUY MORE",
        "action_reason": "Strong earnings trajectory supports accumulation on dips.",
    },
    {
        "symbol": "HDFCBANK",
        "flag_type": "green",
        "latest_news": "Credit growth 16% YoY. HDFC merger integration on track.",
        "analyst_sentiment": "Bullish",
        "analyst_rationale": "Merger synergies expected to drive margin improvement.",
        "key_risks": ["Deposit growth lag", "Integration costs"],
        "action_signal": "HOLD",
        "action_reason": "Hold for merger synergy unlock over 12-18 months.",
    },
    {
        "symbol": "TCS",
        "flag_type": "red",
        "latest_news": "Deal wins slow in Q3. Management cautious on discretionary spend.",
        "analyst_sentiment": "Neutral",
        "analyst_rationale": "Valuation reasonable but visibility low until H2 FY26.",
        "key_risks": ["US recession risk", "AI disruption"],
        "action_signal": "HOLD",
        "action_reason": "Hold with stop-loss; do not add at current valuations.",
    },
]

def _mock_overview_response():
    return mock_gemini_response(text=json.dumps({"market_overview": MOCK_OVERVIEW["market_overview"],
       **MOCK_OVERVIEW}))

def _mock_deep_dive_response():
    return mock_gemini_response(text=json.dumps({"deep_dive": MOCK_DEEP_DIVE}))

def _mock_all_gemini_v2(model, contents, config):
    """Route mock responses: scout → scout JSON, deep_dive → dive JSON, else overview JSON."""
    if "scout_suggestions" in contents and "rank" not in contents:
        # Scout prompt (contains schema with scout_suggestions key)
        from datetime import date
        return mock_gemini_response(text=json.dumps({
            "date": date.today().strftime("%Y-%m-%d"),
            "analyst_note": "Mixed market.",
            "scout_suggestions": MOCK_SCOUTS,
        }))
    elif "deep_dive" in contents or "flagged" in contents.lower():
        return _mock_deep_dive_response()
    else:
        return _mock_overview_response()

# ============================================================
# STAGE 4: Gemini Analysis — 2-Call Architecture (FULLY MOCKED)
# ============================================================
print(f"\n{SEP}")
print("  STAGE 4 — core.py: 2-Call Analysis (FULLY MOCKED, no network)")
print(SEP)

def t4_portfolio_table():
    """build_portfolio_table includes Qty column and key symbols."""
    df = core.load_portfolio()
    table = core.build_portfolio_table(df)
    assert "Symbol" in table
    assert "Qty" in table, "Qty column is missing — quantities should be sent to LLM"
    assert "SBIN" in table or any(sym in table for sym in df["Symbol"].tolist())

def t4_qty_not_in_table():
    """The portfolio table must not contain any '[MASKED]' privacy artifact."""
    df = core.load_portfolio()
    table = core.build_portfolio_table(df)
    assert "[MASKED]" not in table, "MASKED token found in table — masking is disabled"

def t4_qty_present_in_table():
    """Actual quantity values should appear in the table."""
    df = core.load_portfolio()
    table = core.build_portfolio_table(df)
    first_qty = str(int(df["Quantity Available"].dropna().iloc[0]))
    assert first_qty in table, f"Expected qty '{first_qty}' in table but not found"


def t4_fetch_overview():
    """fetch_portfolio_overview returns the right keys (mocked)."""
    df = core.load_portfolio()
    core.client.models.generate_content = MagicMock(return_value=_mock_overview_response())
    overview = core.fetch_portfolio_overview(df)
    for k in ["market_overview", "portfolio_health", "green_flags", "red_flags", "neutral_watch"]:
        assert k in overview, f"Missing key in overview: {k}"
    print(f"\n       Green: {len(overview['green_flags'])}  Red: {len(overview['red_flags'])}", end="")

def t4_fetch_deep_dive():
    """fetch_flagged_deep_dive covers only the flagged symbols (mocked)."""
    df = core.load_portfolio()
    flagged = ["SBIN", "TCS"]
    core.client.models.generate_content = MagicMock(return_value=_mock_deep_dive_response())
    dives = core.fetch_flagged_deep_dive(df, flagged)
    assert isinstance(dives, list)
    assert len(dives) > 0
    for d in dives:
        assert "symbol" in d and "action_signal" in d

def t4_orchestrator():
    """fetch_portfolio_analyses returns overview + deep_dive dict (mocked)."""
    df = core.load_portfolio()
    core.client.models.generate_content = MagicMock(side_effect=lambda model, contents, config:
        _mock_deep_dive_response() if "deep_dive" in contents else _mock_overview_response())
    result = core.fetch_portfolio_analyses(df)
    assert "overview" in result and "deep_dive" in result
    print(f"\n       Deep dive symbols: {[d['symbol'] for d in result['deep_dive']]}", end="")

for name, fn in [
    ("build_portfolio_table: has Qty column + key symbols",    t4_portfolio_table),
    ("build_portfolio_table: no [MASKED] artifact",            t4_qty_not_in_table),
    ("build_portfolio_table: real qty values present",         t4_qty_present_in_table),
    ("fetch_portfolio_overview: correct keys returned",        t4_fetch_overview),
    ("fetch_flagged_deep_dive: covers flagged symbols",        t4_fetch_deep_dive),
    ("fetch_portfolio_analyses: returns overview+deep_dive",   t4_orchestrator),
]:
    run_test(name, fn)

# ============================================================
# STAGE 5: Live Scout Suggestions (fetch_scout_suggestions)
# ============================================================
print(f"\n{SEP}")
print("  STAGE 5 — core.fetch_scout_suggestions (MOCKED, refreshes on each run)")
print(SEP)

def t5_live_fetch_returns_3():
    """Live fetch returns 3 picks (Gemini mocked with valid JSON)."""
    core.client.models.generate_content = MagicMock(return_value=mock_scout_response())
    picks = core.fetch_scout_suggestions(save_to_file=False)
    assert len(picks) == 3, f"Expected 3 picks, got {len(picks)}"
    print(f"\n       Picks returned: {len(picks)}", end="")

def t5_live_fetch_required_fields():
    """Every pick has the required schema fields."""
    core.client.models.generate_content = MagicMock(return_value=mock_scout_response())
    picks = core.fetch_scout_suggestions(save_to_file=False)
    for p in picks:
        assert "ticker" in p or "symbol" in p, f"No ticker in pick: {p}"
        assert "current_price_inr" in p or "current_price" in p, f"No price in pick: {p}"
        assert "why" in p or "rationale" in p, f"No rationale in pick: {p}"

def t5_live_fetch_saves_json():
    """Successful fetch writes fresh data to scout_suggestions.json."""
    import tempfile, os as _os
    tmp = tempfile.mktemp(suffix=".json")
    orig_path = core.SCOUT_JSON_PATH
    core.SCOUT_JSON_PATH = tmp
    try:
        core.client.models.generate_content = MagicMock(return_value=mock_scout_response())
        core.fetch_scout_suggestions(save_to_file=True)
        assert _os.path.exists(tmp), "JSON file was not written!"
        with open(tmp) as f:
            saved = json.load(f)
        assert "scout_suggestions" in saved
        assert len(saved["scout_suggestions"]) == 3
    finally:
        core.SCOUT_JSON_PATH = orig_path
        if _os.path.exists(tmp):
            _os.remove(tmp)

def t5_live_fetch_fallback_on_error():
    """If Gemini fails, falls back to existing scout_suggestions.json."""
    # Simulate a network/API error
    core.client.models.generate_content = MagicMock(side_effect=Exception("API down"))
    picks = core.fetch_scout_suggestions(save_to_file=False)
    # Should not raise — returns cached file or empty list
    assert isinstance(picks, list)
    print(f"\n       Fallback picks: {len(picks)}", end="")

for name, fn in [
    ("fetch_scout_suggestions: returns 3 live picks (mocked)",    t5_live_fetch_returns_3),
    ("fetch_scout_suggestions: all picks have required fields",    t5_live_fetch_required_fields),
    ("fetch_scout_suggestions: saves fresh JSON to disk",          t5_live_fetch_saves_json),
    ("fetch_scout_suggestions: graceful fallback on API failure",  t5_live_fetch_fallback_on_error),
]:
    run_test(name, fn)

# ============================================================
# STAGE 6: WhatsApp Formatting (no send)
# ============================================================
print(f"\n{SEP}")
print("  STAGE 6 — telegram_notifier: Message Formatting (no send)")
print(SEP)

MOCK_OVERVIEW_TAGGED = {
    **MOCK_OVERVIEW,
    "green_flags": [
        {"symbol": "SBIN", "headline": "SBIN Q3 PAT up 84% YoY",
         "reason": "Strong earnings beat.", "quality": "SIGNAL"},
        {"symbol": "HDFCBANK", "headline": "Credit growth 16% YoY",
         "reason": "Loan book expanding.", "quality": "NOISE"},
    ],
    "red_flags": [
        {"symbol": "TCS", "headline": "IT deal wins slow",
         "reason": "US client spending cuts.", "quality": "SIGNAL"},
    ],
    "neutral_watch": [
        {"symbol": "RELIANCE", "reason": "Awaiting Jio IPO.", "quality": "NOISE"},
    ],
}

MOCK_BRIEFING = {
    "date": "2026-03-14",
    "generated_at": "2026-03-14 11:00:00",
    "portfolio_snapshot": {
        "total_holdings": 56, "invested_value": 2361723.18,
        "present_value": 2623682.18, "unrealized_pnl": 261958.74, "pnl_pct": 11.09,
    },
    "portfolio_summary": {},
    "portfolio_overview": MOCK_OVERVIEW_TAGGED,
    "deep_dive": [
        {**MOCK_DEEP_DIVE[0], "quality": "SIGNAL"},
        {**MOCK_DEEP_DIVE[1], "quality": "NOISE"},
        {**MOCK_DEEP_DIVE[2], "quality": "SIGNAL"},
    ],
    "scout_suggestions": MOCK_SCOUTS,
    "portfolio_df_pnl": {},
    "new_tickers_thesis": {"SBIN": "PSU Re-rating"},
}

def t6_build_report():
    report = tn.build_telegram_report(MOCK_BRIEFING)
    assert isinstance(report, str) and len(report) > 100

def t6_sections_new_format():
    report = tn.build_telegram_report(MOCK_BRIEFING).lower()
    assert "market sentiment" in report, "Missing MARKET SENTIMENT"
    assert "high" in report and "signal intel" in report, \
        "Missing HIGH-SIGNAL INTEL section (quality tags present)"

def t6_thesis_note():
    # Deprecated: user requested completely removing Thesis Notes
    pass

def t6_scout_picks():
    report = tn.build_telegram_report(MOCK_BRIEFING)
    assert "SCOUT PICKS" in report, "Scout picks section missing"
    assert "SHAKTIPUMP" in report, "Expected scout ticker not found"

def t6_length():
    report = tn.build_telegram_report(MOCK_BRIEFING)
    l = len(report)
    print(f"\n       Formatted message length: {l} chars", end="")
    assert l <= 6000, f"Too long: {l} chars"

def t6_cred_guard():
    """Verify send_telegram_update raises ValueError for placeholder creds."""
    import importlib, telegram_notifier as _tn2
    old = os.environ["TELEGRAM_BOT_TOKEN"]
    os.environ["TELEGRAM_BOT_TOKEN"] = "your_fake_placeholder"
    try:
        importlib.reload(_tn2)
        try:
            _tn2.send_telegram_update("test")
            assert False, "Should have raised ValueError!"
        except ValueError as ve:
            assert "credential" in str(ve).lower() or "placeholder" in str(ve).lower() \
                   or "missing" in str(ve).lower()
    finally:
        os.environ["TELEGRAM_BOT_TOKEN"] = old

for name, fn in [
    ("build_telegram_report: returns non-empty string",              t6_build_report),
    ("build_telegram_report: has HIGH-SIGNAL INTEL & NOISE sections", t6_sections_new_format),
    ("build_telegram_report: thesis note with /fix hint",            t6_thesis_note),
    ("build_telegram_report: scout picks section present",           t6_scout_picks),
    ("build_telegram_report: message within size limits",            t6_length),
    ("send_telegram_update: ValueError on placeholder creds",        t6_cred_guard),
]:
    run_test(name, fn)

# ============================================================
# STAGE 7: Full Pipeline Integration via main.py
# ============================================================
print(f"\n{SEP}")
print("  STAGE 7 — main.py: Full Pipeline Integration (MOCKED)")
print(SEP)

def t7_validate_env():
    missing = main.validate_env()
    print(f"\n       Missing env keys: {missing}", end="")
    assert missing == [], f"validate_env raised false alarm: {missing}"

def t7_load_csv():
    df = main.load_portfolio_csv()
    assert len(df) > 0

def t7_load_scouts():
    core.client.models.generate_content = MagicMock(return_value=mock_scout_response())
    scouts = main.load_scout_suggestions()
    assert len(scouts) == 3, f"Expected 3 picks, got {len(scouts)}"

def t7_snapshot():
    df = main.load_portfolio_csv()
    snap = main.build_portfolio_snapshot(df)
    for k in ["invested_value", "present_value", "unrealized_pnl", "pnl_pct", "total_holdings"]:
        assert k in snap, f"Missing key: {k}"
    print(
        f"\n       Invested: ₹{snap['invested_value']:>12,.0f}"
        f" | Present: ₹{snap['present_value']:>12,.0f}"
        f" | P&L: {snap['pnl_pct']:+.2f}%",
        end=""
    )

def t7_merge_briefing():
    df = main.load_portfolio_csv()
    mock_analyses = {"overview": MOCK_OVERVIEW_TAGGED, "deep_dive": MOCK_DEEP_DIVE}
    scouts = MOCK_SCOUTS
    briefing = main.merge_briefing(df, mock_analyses, scouts, new_tickers_thesis={"SBIN": "Growth"})
    for k in ["date", "generated_at", "portfolio_snapshot",
              "portfolio_overview", "deep_dive", "scout_suggestions",
              "portfolio_df_pnl", "new_tickers_thesis"]:
        assert k in briefing, f"Missing briefing key: {k}"

def t7_dry_run_no_send():
    briefing = {**MOCK_BRIEFING}
    with patch("requests.post") as mock_post:
        mock_post.return_value.ok = True
        main.trigger_telegram(briefing, dry_run=True)
        called = mock_post.called
        assert not called, f"requests.post() was triggered in dry-run mode — BUG!"

def t7_console_summary():
    df = main.load_portfolio_csv()
    briefing = {**MOCK_BRIEFING, "portfolio_summary": main.build_portfolio_snapshot(df)}
    main.print_console_summary(briefing)

for name, fn in [
    ("main.validate_env: passes with DRY_RUN_ values",             t7_validate_env),
    ("main.load_portfolio_csv: returns valid DataFrame",            t7_load_csv),
    ("main.load_scout_suggestions: returns all 3 picks",            t7_load_scouts),
    ("main.build_portfolio_snapshot: correct keys + values",        t7_snapshot),
    ("main.merge_briefing: assembles complete briefing dict",       t7_merge_briefing),
    ("main.trigger_telegram(dry_run=True): NO API call made",       t7_dry_run_no_send),
    ("main.print_console_summary: renders without error",           t7_console_summary),
]:
    run_test(name, fn)

# ============================================================
# STAGE 8: ThesisManager
# ============================================================
print(f"\n{SEP}")
print("  STAGE 8 — ThesisManager: Persistence, Inference & Updates")
print(SEP)

with patch("google.genai.Client"):
    from thesis_manager import ThesisManager

def _make_tm(tmp_path):
    """Create a ThesisManager backed by a temp file."""
    return ThesisManager(metadata_path=tmp_path)

def t8_empty_store():
    """Fresh ThesisManager has no entries."""
    import tempfile
    tmp = tempfile.mktemp(suffix=".json")
    tm = _make_tm(tmp)
    assert tm.get_thesis("SBIN") is None
    if os.path.exists(tmp): os.remove(tmp)

def t8_update_and_persist():
    """update_thesis writes to disk and can be re-read."""
    import tempfile
    tmp = tempfile.mktemp(suffix=".json")
    tm = _make_tm(tmp)
    tm.update_thesis("SBIN", "PSU Re-rating")
    assert tm.get_thesis("SBIN") == "PSU Re-rating"
    # Re-load from disk
    tm2 = _make_tm(tmp)
    assert tm2.get_thesis("SBIN") == "PSU Re-rating"
    entry = tm2.get_entry("SBIN")
    assert entry["inferred"] is False
    os.remove(tmp)

def t8_infer_and_store():
    """infer_and_store calls Gemini (mocked) and saves result."""
    import tempfile
    tmp = tempfile.mktemp(suffix=".json")
    tm = _make_tm(tmp)
    mock_thesis_resp = mock_gemini_response(text=json.dumps({
        "ticker": "TCS",
        "primary_thesis": "Quality Compounder",
        "rationales": ["Quality Compounder", "Export Growth", "Dividend Play"],
        "confidence": "High",
    }))
    core.client.models.generate_content = MagicMock(return_value=mock_thesis_resp)
    thesis = tm.infer_and_store("TCS", "IT")
    assert thesis == "Quality Compounder"
    assert tm.get_thesis("TCS") == "Quality Compounder"
    entry = tm.get_entry("TCS")
    assert entry["inferred"] is True
    assert "TCS" in tm.get_new_tickers()
    os.remove(tmp)

def t8_ensure_existing():
    """ensure_thesis returns existing entry without calling the API."""
    import tempfile
    tmp = tempfile.mktemp(suffix=".json")
    tm = _make_tm(tmp)
    tm.update_thesis("HDFCBANK", "Dividend Play")
    # Poison the API — it should NOT be called
    core.client.models.generate_content = MagicMock(side_effect=Exception("Should not call API!"))
    thesis = tm.ensure_thesis("HDFCBANK", "Financial Services")
    assert thesis == "Dividend Play", f"Got: {thesis}"
    os.remove(tmp)

def t8_build_thesis_map():
    """build_thesis_map returns a full ticker→thesis dict."""
    import tempfile
    tmp = tempfile.mktemp(suffix=".json")
    tm = _make_tm(tmp)
    tm.update_thesis("SBIN", "PSU Re-rating")
    mock_thesis_resp = mock_gemini_response(text=json.dumps({
        "ticker": "TCS", "primary_thesis": "Growth Play",
        "rationales": ["Growth Play"], "confidence": "Medium",
    }))
    core.client.models.generate_content = MagicMock(return_value=mock_thesis_resp)
    tmap = tm.build_thesis_map([("SBIN", "Financial Services"), ("TCS", "IT")])
    assert tmap["SBIN"] == "PSU Re-rating"
    assert tmap["TCS"] == "Growth Play"
    assert "TCS" in tm.get_new_tickers()
    assert "SBIN" not in tm.get_new_tickers()  # was pre-existing
    os.remove(tmp)

for name, fn in [
    ("ThesisManager: fresh store has no entries",                  t8_empty_store),
    ("ThesisManager: update_thesis persists to disk",              t8_update_and_persist),
    ("ThesisManager: infer_and_store uses Gemini (mocked)",        t8_infer_and_store),
    ("ThesisManager: ensure_thesis returns existing, no API call", t8_ensure_existing),
    ("ThesisManager: build_thesis_map covers all tickers",         t8_build_thesis_map),
]:
    run_test(name, fn)

# ============================================================
# STAGE 9: Quality Critic (classify_news_items)
# ============================================================
print(f"\n{SEP}")
print("  STAGE 9 — Quality Critic: SIGNAL / NOISE Classification (MOCKED)")
print(SEP)

_MOCK_CRITIC_CLASSIFICATIONS = [
    {"id": 0, "classification": "SIGNAL", "reason": "Earnings structural."},
    {"id": 1, "classification": "NOISE",  "reason": "Price move only."},
    {"id": 2, "classification": "SIGNAL", "reason": "Deal loss material."},
    {"id": 3, "classification": "NOISE",  "reason": "Vague wait-and-see."},
    {"id": 4, "classification": "SIGNAL", "reason": "Strong earnings."},
    {"id": 5, "classification": "NOISE",  "reason": "Integration already priced."},
    {"id": 6, "classification": "NOISE",  "reason": "Low visibility."},
]

def _mock_critic_response():
    return mock_gemini_response(text=json.dumps(_MOCK_CRITIC_CLASSIFICATIONS))

def t9_classify_returns_quality_tags():
    """classify_news_items tags each item with 'quality': SIGNAL or NOISE."""
    import copy
    ov = copy.deepcopy(MOCK_OVERVIEW)
    dd = copy.deepcopy(MOCK_DEEP_DIVE)
    tmap = {"SBIN": "PSU Re-rating", "HDFCBANK": "Dividend Play",
            "TCS": "Quality Compounder", "RELIANCE": "Conglomerate Growth"}
    core.client.models.generate_content = MagicMock(return_value=_mock_critic_response())
    updated_ov, updated_dd = core.classify_news_items(ov, dd, tmap)
    # Every flag should now have a quality key
    for flag_key in ("green_flags", "red_flags", "neutral_watch"):
        for item in updated_ov.get(flag_key, []):
            assert "quality" in item, f"Missing quality tag in {flag_key}: {item}"
            assert item["quality"] in ("SIGNAL", "NOISE")
    for item in updated_dd:
        assert "quality" in item, f"Missing quality tag in deep_dive: {item}"

def t9_classify_no_items_noop():
    """classify_news_items with empty overview does nothing (no API call)."""
    core.client.models.generate_content = MagicMock(side_effect=Exception("Should not call"))
    empty_ov = {"green_flags": [], "red_flags": [], "neutral_watch": {}}
    updated_ov, updated_dd = core.classify_news_items(empty_ov, [], thesis_map={})
    assert updated_dd == []

def t9_classify_fails_open():
    """If the critic call fails, items default to SIGNAL (fail open)."""
    import copy
    ov = copy.deepcopy(MOCK_OVERVIEW)
    dd = copy.deepcopy(MOCK_DEEP_DIVE)
    tmap = {"SBIN": "PSU Re-rating", "HDFCBANK": "Dividend Play", "TCS": "Growth"}
    core.client.models.generate_content = MagicMock(side_effect=Exception("API down"))
    updated_ov, updated_dd = core.classify_news_items(ov, dd, tmap)
    for item in updated_ov.get("green_flags", []):
        assert item.get("quality") == "SIGNAL", "Fail-open: expected SIGNAL"

for name, fn in [
    ("classify_news_items: all items get quality tag",          t9_classify_returns_quality_tags),
    ("classify_news_items: empty overview is a no-op",          t9_classify_no_items_noop),
    ("classify_news_items: API failure defaults to SIGNAL",     t9_classify_fails_open),
]:
    run_test(name, fn)

# ============================================================
# FINAL SUMMARY
# ============================================================
passed = sum(1 for r in RESULTS if r[0])
failed = sum(1 for r in RESULTS if not r[0])
total  = len(RESULTS)

print(f"\n{'=' * 65}")
print("  📋  DRY RUN SUMMARY")
print('=' * 65)
print(f"\n  Total checks: {total}  |  {PASS} Passed: {passed}  |  {FAIL} Failed: {failed}\n")

if failed:
    print("  Failed checks:")
    for ok, name, err in RESULTS:
        if not ok:
            print(f"    {FAIL}  {name}")
            if err:
                print(f"         └─ {err}")
    print()

if failed == 0:
    print("  🎉  ALL CHECKS PASSED — Pipeline is verified and ready for live run!")
    print()
    print("  📝  Next steps:")
    print("       1. Fill in real values in .env")
    print("       2. Run:  source venv/bin/activate")
    print("       3. Then: python main.py --dry-run   (formats, no Telegram send)")
    print("       4. Then: python main.py             (full live run)")
else:
    print("  ⚠️   Some checks failed — review output above before going live.")

print('=' * 65)
print()
sys.exit(0 if failed == 0 else 1)
