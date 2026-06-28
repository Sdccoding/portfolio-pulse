"""
thesis_manager.py — Portfolio Pulse: Agentic Thesis Store
==========================================================
Manages per-ticker investment thesis persistence and inference.

Responsibilities:
  - Load/save thesis_metadata.json (local persistent store, gitignored)
  - Infer missing theses via Gemini 2.5 Flash + Google Search
  - Track new (inferred) tickers for Telegram notification
  - Support manual thesis correction via update_thesis()
"""
from loguru import logger

import os
import json
from datetime import date as _date

# Gemini client is shared from core.py's module-level client
# We import lazily to avoid circular imports

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_METADATA_PATH = os.path.join(BASE_DIR, "thesis_metadata.json")

# ---------------------------------------------------------------------------
# Inference prompt
# ---------------------------------------------------------------------------

_THESIS_INFER_PROMPT = """\
You are a senior Indian equity research analyst.

Given the stock ticker "{ticker}" listed on NSE/BSE in the "{sector}" sector, \
use Google Search to identify the 3 most likely investment rationales retail investors \
hold for this stock (e.g. "Sector Tailwind", "Dividend Play", "Recovery Bet", \
"Quality Compounder", "Turnaround Story", "Regulatory Moat", "Export Growth", etc.).

Return ONLY a valid JSON object (no markdown fences) with this schema:

{{
  "ticker": "{ticker}",
  "primary_thesis": "<single most dominant rationale — one short phrase>",
  "rationales": [
    "<thesis 1>",
    "<thesis 2>",
    "<thesis 3>"
  ],
  "confidence": "High" | "Medium" | "Low"
}}

Rules:
- primary_thesis must be one of the 3 rationales, the most likely one.
- Keep each rationale concise (≤6 words).
- Base your answer on real, searchable news and analyst consensus.
- Return ONLY the JSON. No preamble, no markdown fences.
"""


# ---------------------------------------------------------------------------
# ThesisManager
# ---------------------------------------------------------------------------

class ThesisManager:
    """
    Manages the investment thesis for each portfolio ticker.

    Persistence:
        thesis_metadata.json — local file, gitignored.
        Schema per entry:
        {
          "SBIN": {
            "thesis":       "Dividend Play + PSU Re-rating",
            "rationales":   ["Dividend Play", "PSU Re-rating", "Credit Growth"],
            "inferred":     true,
            "updated_at":   "2026-04-12"
          }
        }
    """

    def __init__(self, metadata_path: str = DEFAULT_METADATA_PATH):
        self.metadata_path = metadata_path
        self._store: dict = self._load()
        self._new_tickers: set[str] = set()  # tickers inferred THIS run

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load(self) -> dict:
        """Load metadata.json from disk (returns empty dict if missing)."""
        if os.path.exists(self.metadata_path):
            try:
                with open(self.metadata_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"[ThesisManager] ⚠️  Could not read metadata: {e}. Starting fresh.")
        return {}

    def _save(self) -> None:
        """Persist the in-memory store to disk."""
        try:
            with open(self.metadata_path, "w", encoding="utf-8") as f:
                json.dump(self._store, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"[ThesisManager] ⚠️  Could not save metadata: {e}")

    # ── Public API ───────────────────────────────────────────────────────────

    def get_thesis(self, ticker: str) -> str | None:
        """Return the stored thesis string for a ticker, or None if missing."""
        entry = self._store.get(ticker)
        return entry["thesis"] if entry else None

    def update_thesis(self, ticker: str, new_thesis: str) -> None:
        """
        Manually override the thesis for a ticker (used by --fix CLI flag).
        Sets inferred=False so it's never auto-overwritten.
        """
        today = _date.today().strftime("%Y-%m-%d")
        self._store[ticker] = {
            "thesis": new_thesis,
            "rationales": [new_thesis],
            "inferred": False,
            "updated_at": today,
        }
        self._save()
        logger.info(f"[ThesisManager] ✓ Thesis for {ticker} updated to: '{new_thesis}'")

    def infer_and_store(self, ticker: str, sector: str = "Unknown") -> str:
        """
        Call Gemini + Google Search to infer the 3 most likely rationales,
        pick the primary_thesis, persist it, and return it.
        Falls back to a generic thesis on any error.
        """
        from logic import llm_client

        prompt = _THESIS_INFER_PROMPT.format(ticker=ticker, sector=sector)

        try:
            response = llm_client.generate(prompt, use_grounding=True)
            raw = response.text.strip()
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                raw = raw[start:end + 1]
            data = json.loads(raw)
            thesis = data.get("primary_thesis", "Growth Play")
            rationales = data.get("rationales", [thesis])

        except Exception as e:
            logger.warning(f"[ThesisManager] ⚠️  Inference failed for {ticker}: {e}")
            thesis = "Growth Play"
            rationales = ["Growth Play"]

        today = _date.today().strftime("%Y-%m-%d")
        self._store[ticker] = {
            "thesis": thesis,
            "rationales": rationales,
            "inferred": True,
            "updated_at": today,
        }
        self._save()
        self._new_tickers.add(ticker)
        logger.info(f"[ThesisManager] 🔍 Inferred thesis for {ticker}: '{thesis}'")
        return thesis

    def ensure_thesis(self, ticker: str, sector: str = "Unknown") -> str:
        """
        Return existing thesis if present, otherwise infer and store a new one.
        This is the main entry point called for every portfolio ticker.
        """
        existing = self.get_thesis(ticker)
        if existing:
            return existing
        return self.infer_and_store(ticker, sector)

    # ── Batch inference prompt ────────────────────────────────────────────────

    _BATCH_INFER_PROMPT = """\
You are a senior Indian equity research analyst with access to live market data via Google Search.

For each of the following Indian stocks, identify the single most dominant investment thesis \
retail investors hold for that stock. Use Google Search to ground your answer in real analyst \
commentary and recent news.

Stocks (JSON array of objects with ticker and sector):
{stocks_json}

Return ONLY a valid JSON array (no markdown fences) where each element has:
{{
  "ticker": "<same ticker as input>",
  "primary_thesis": "<single most dominant rationale — concise phrase ≤6 words>",
  "rationales": ["<thesis 1>", "<thesis 2>", "<thesis 3>"]
}}

Rules:
- Cover EVERY ticker in the input list. Do not skip any.
- primary_thesis examples: "Dividend Play", "PSU Re-rating", "Quality Compounder", \
"Recovery Bet", "Sector Tailwind", "Export Growth", "Turnaround Story".
- Return ONLY the JSON array. No preamble, no markdown fences.
"""

    def _batch_infer(self, missing: list[tuple[str, str]]) -> dict[str, str]:
        """
        Single Gemini+Search call to infer theses for ALL missing tickers at once.
        Returns a ticker → thesis dict. Falls back to 'Growth Play' for any failures.
        """
        from logic import llm_client

        stocks_json = json.dumps(
            [{"ticker": t, "sector": s} for t, s in missing],
            ensure_ascii=False,
        )
        prompt = self._BATCH_INFER_PROMPT.format(stocks_json=stocks_json)

        today = _date.today().strftime("%Y-%m-%d")
        results: dict[str, str] = {}

        try:
            response = llm_client.generate(prompt, use_grounding=True)
            raw = response.text.strip()
            start_bracket = raw.find("[")
            start_brace = raw.find("{")
            if start_bracket != -1 and (start_brace == -1 or start_bracket < start_brace):
                start, end = start_bracket, raw.rfind("]")
            else:
                start, end = start_brace, raw.rfind("}")

            if start != -1 and end != -1 and end > start:
                raw = raw[start:end + 1]

            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                items = []
                for k, v in parsed.items():
                    if isinstance(v, list):
                        items = v
                        break
                if not items:
                    items = [parsed]
            else:
                items = parsed

            for item in items:
                ticker = item.get("ticker", "")
                thesis = item.get("primary_thesis", "Growth Play")
                rationales = item.get("rationales", [thesis])
                if not ticker:
                    continue
                self._store[ticker] = {
                    "thesis": thesis,
                    "rationales": rationales,
                    "inferred": True,
                    "updated_at": today,
                }
                self._new_tickers.add(ticker)
                results[ticker] = thesis

            self._save()
            logger.info(
                f"[ThesisManager] ✓ Batch inferred {len(results)}/{len(missing)} "
                f"theses in 1 API call"
            )

        except Exception as e:
            logger.warning(f"[ThesisManager] ⚠️  Batch inference failed: {e}. Using 'Growth Play' fallback.")

        # Fill in any tickers that were missed/failed
        for ticker, _ in missing:
            if ticker not in results:
                fallback = "Growth Play"
                self._store[ticker] = {
                    "thesis": fallback,
                    "rationales": [fallback],
                    "inferred": True,
                    "updated_at": today,
                }
                self._new_tickers.add(ticker)
                results[ticker] = fallback

        if results:
            self._save()

        return results

    def build_thesis_map(self, tickers_sectors: list[tuple[str, str]]) -> dict[str, str]:
        """
        Return a ticker→thesis mapping for every (ticker, sector) pair.

        - Returns cached theses immediately (zero API calls for known tickers).
        - Batches ALL missing tickers into a single Gemini+Search call (1 API call max).

        Args:
            tickers_sectors: list of (ticker_symbol, sector_name) tuples.

        Returns:
            dict mapping ticker → thesis string.
        """
        thesis_map: dict[str, str] = {}
        missing: list[tuple[str, str]] = []

        for ticker, sector in tickers_sectors:
            existing = self.get_thesis(ticker)
            if existing:
                thesis_map[ticker] = existing
            else:
                missing.append((ticker, sector))

        if missing:
            logger.info(
                f"[ThesisManager] 🔍 Inferring theses for {len(missing)} new ticker(s) "
                f"in 1 batch call…"
            )
            inferred = self._batch_infer(missing)
            thesis_map.update(inferred)

        return thesis_map

    def get_new_tickers(self) -> set[str]:
        """
        Return the set of tickers whose theses were INFERRED (not pre-existing)
        during this run. Used by the Telegram formatter to append a note.
        """
        return frozenset(self._new_tickers)

    def get_entry(self, ticker: str) -> dict | None:
        """Return the full metadata entry for a ticker."""
        return self._store.get(ticker)


# ---------------------------------------------------------------------------
# CLI helper — python thesis_manager.py --fix TICKER "New Thesis"
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ThesisManager CLI")
    sub = parser.add_subparsers(dest="command")

    fix_p = sub.add_parser("fix", help="Manually set thesis for a ticker")
    fix_p.add_argument("ticker", type=str.upper)
    fix_p.add_argument("thesis", type=str)

    show_p = sub.add_parser("show", help="Show all stored theses")

    args = parser.parse_args()
    tm = ThesisManager()

    if args.command == "fix":
        tm.update_thesis(args.ticker, args.thesis)
    elif args.command == "show":
        if not tm._store:
            logger.info("No theses stored yet.")
        else:
            logger.info(json.dumps(tm._store, indent=2, ensure_ascii=False))
    else:
        parser.print_help()
