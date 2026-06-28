"""
logic/thesis_manager.py — Portfolio Pulse: Modular Thesis Manager
==================================================================
Manages per-ticker investment thesis persistence and inference.

This is the formalized, MCP-architecture version of the root-level
thesis_manager.py. Key differences:
  - Imports Gemini client from logic.llm_client (not core.py)
  - Adds a top-level get_or_infer_thesis() function (the main public API)
  - Uses a Chain-of-Thought (CoT) inference prompt that resolves opaque
    tickers (e.g. TMPV → Tata Motors Passenger Vehicles) before reasoning

The root-level thesis_manager.py and thesis_metadata.json are shared —
both this module and the legacy module operate on the same JSON file.
"""
from loguru import logger

import os
import json
from datetime import date as _date

import config

# ── Paths ─────────────────────────────────────────────────────────────────────

DEFAULT_METADATA_PATH = config.THESIS_METADATA_PATH

# ── Chain-of-Thought Inference Prompt ─────────────────────────────────────────

_COT_THESIS_PROMPT = """\
You are a senior Indian equity research analyst with access to live market data \
via Google Search.

Your task is to determine the primary investment thesis for the stock ticker \
"{ticker}" listed on NSE/BSE in the "{sector}" sector.

Think step by step:

Step 1 — Identify the company:
  First, search for "{ticker}" on Google to confirm what company this ticker \
refers to. Many tickers are abbreviations (e.g. TMPV = Tata Motors Passenger \
Vehicles, JIOFIN = Jio Financial Services, ITCHOTELS = ITC Hotels). State the \
full company name before proceeding.

Step 2 — Research the investment rationale:
  Search for analyst commentary, investor forums, and recent news for this company. \
Identify the 3 most common reasons retail investors in India hold this stock.

Step 3 — Synthesise the primary thesis:
  From the 3 rationales, select the single most dominant one as the primary_thesis.

Return ONLY a valid JSON object (no markdown fences) with this schema:

{{
  "ticker": "{ticker}",
  "company_name": "<full company name identified in Step 1>",
  "primary_thesis": "<single most dominant rationale — concise phrase ≤6 words>",
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

# ── Batch CoT Prompt ──────────────────────────────────────────────────────────

_BATCH_COT_PROMPT = """\
You are a senior Indian equity research analyst with access to live market data \
via Google Search.

For each stock in the list below, determine the primary investment thesis \
retail investors hold for that stock. Follow these steps for EACH ticker:

Step 1 — Identify the company: Confirm the full company name behind the ticker. \
Many tickers are abbreviations (TMPV = Tata Motors Passenger Vehicles, \
JIOFIN = Jio Financial Services, ITCHOTELS = ITC Hotels, etc.).

Step 2 — Research rationales: Find the 3 most common retail investor rationales \
for holding this stock (analyst commentary, forums, recent news).

Step 3 — Synthesise: Pick the single most dominant rationale as primary_thesis.

Stocks to analyse (JSON array):
{stocks_json}

Return ONLY a valid JSON array (no markdown fences) where each element is:
{{
  "ticker": "<same ticker as input>",
  "company_name": "<full company name>",
  "primary_thesis": "<single most dominant rationale — concise phrase ≤6 words>",
  "rationales": ["<thesis 1>", "<thesis 2>", "<thesis 3>"]
}}

Rules:
- Cover EVERY ticker. Do not skip any.
- Return ONLY the JSON array. No preamble, no markdown fences.
"""


# ── ThesisManager (modular version) ───────────────────────────────────────────

class ThesisManager:
    """
    Manages the investment thesis for each portfolio ticker.

    Persistence:
        thesis_metadata.json — local file (path from config.py).
        Schema per entry:
        {
          "SBIN": {
            "thesis":       "PSU banking leader, asset quality turnaround",
            "company_name": "State Bank of India",
            "rationales":   ["...", "...", "..."],
            "inferred":     true,
            "updated_at":   "2026-04-18"
          }
        }

    Usage:
        tm = ThesisManager()
        thesis = tm.get_or_infer_thesis("TMPV", sector="Automobile")
    """

    def __init__(self, metadata_path: str = DEFAULT_METADATA_PATH) -> None:
        self.metadata_path = metadata_path
        self._store: dict = self._load()
        self._new_tickers: set[str] = set()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _get_gcs_blob(self):
        bucket_name = os.getenv("GCS_BUCKET_NAME", "").strip()
        if not bucket_name:
            return None
        try:
            from google.cloud import storage
            client = storage.Client()
            bucket = client.bucket(bucket_name)
            return bucket.blob("thesis_metadata.json")
        except Exception as e:
            logger.warning(f"[ThesisManager] ⚠️ GCS Init Failed: {e}")
            return None

    def _load(self) -> dict:
        blob = self._get_gcs_blob()
        if blob and blob.exists():
            try:
                logger.info(f"[ThesisManager] 📥 Loaded thesis metadata from GCS.")
                return json.loads(blob.download_as_string())
            except Exception as e:
                logger.warning(f"[ThesisManager] ⚠️ GCS load failed: {e}. Falling back locally.")

        if os.path.exists(self.metadata_path):
            try:
                with open(self.metadata_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"[ThesisManager] ⚠️  Could not read metadata: {e}. Starting fresh.")
        return {}

    def _save(self) -> None:
        blob = self._get_gcs_blob()
        if blob:
            try:
                blob.upload_from_string(json.dumps(self._store, indent=2, ensure_ascii=False), content_type="application/json")
                return
            except Exception as e:
                logger.warning(f"[ThesisManager] ⚠️ GCS save failed: {e}. Falling back locally.")

        try:
            with open(self.metadata_path, "w", encoding="utf-8") as f:
                json.dump(self._store, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"[ThesisManager] ⚠️  Could not save metadata: {e}")

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_thesis(self, ticker: str) -> str | None:
        """Return the stored thesis string for a ticker, or None if missing."""
        entry = self._store.get(ticker)
        return entry["thesis"] if entry else None

    def get_entry(self, ticker: str) -> dict | None:
        """Return the full metadata entry for a ticker."""
        return self._store.get(ticker)

    # ── Write (manual) ────────────────────────────────────────────────────────

    def update_thesis(self, ticker: str, new_thesis: str) -> None:
        """Manually override the thesis. Sets inferred=False so it's never auto-overwritten."""
        today = _date.today().strftime("%Y-%m-%d")
        self._store[ticker] = {
            "thesis":     new_thesis,
            "rationales": [new_thesis],
            "inferred":   False,
            "updated_at": today,
        }
        self._save()
        logger.info(f"[ThesisManager] ✓ Thesis for {ticker} updated to: '{new_thesis}'")

    # ── Inference (single ticker, CoT) ────────────────────────────────────────

    def infer_and_store(self, ticker: str, sector: str = "Unknown") -> str:
        """
        Infer thesis via Gemini CoT prompt, persist, and return primary_thesis.
        Falls back to 'Growth Play' on error.
        """
        from logic import llm_client

        prompt = _COT_THESIS_PROMPT.format(ticker=ticker, sector=sector)
        today  = _date.today().strftime("%Y-%m-%d")

        try:
            response = llm_client.generate(prompt, use_grounding=True)
            # Extract outer JSON braces
            raw = response.text.strip()
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                raw = raw[start:end + 1]
            data       = json.loads(raw)
            thesis     = data.get("primary_thesis", "Growth Play")
            rationales = data.get("rationales", [thesis])
            company    = data.get("company_name", ticker)

        except Exception as e:
            logger.warning(f"[ThesisManager] ⚠️  CoT inference failed for {ticker}: {e}")
            thesis     = "Growth Play"
            rationales = ["Growth Play"]
            company    = ticker

        self._store[ticker] = {
            "thesis":       thesis,
            "company_name": company,
            "rationales":   rationales,
            "inferred":     True,
            "updated_at":   today,
        }
        self._save()
        self._new_tickers.add(ticker)
        logger.info(f"[ThesisManager] 🔍 Inferred thesis for {ticker} ({company}): '{thesis}'")
        return thesis

    # ── Inference (batch, single API call) ───────────────────────────────────

    def _batch_infer(self, missing: list[tuple[str, str]]) -> dict[str, str]:
        """
        Single Gemini+Search call to infer theses for ALL missing tickers.
        Returns ticker → thesis dict. Falls back to 'Growth Play' for failures.
        """
        from logic import llm_client

        stocks_json = json.dumps(
            [{"ticker": t, "sector": s} for t, s in missing],
            ensure_ascii=False,
        )
        prompt = _BATCH_COT_PROMPT.format(stocks_json=stocks_json)
        today  = _date.today().strftime("%Y-%m-%d")
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
                ticker     = item.get("ticker", "")
                thesis     = item.get("primary_thesis", "Growth Play")
                rationales = item.get("rationales", [thesis])
                company    = item.get("company_name", ticker)
                if not ticker:
                    continue
                self._store[ticker] = {
                    "thesis":       thesis,
                    "company_name": company,
                    "rationales":   rationales,
                    "inferred":     True,
                    "updated_at":   today,
                }
                self._new_tickers.add(ticker)
                results[ticker] = thesis

            self._save()
            logger.info(
                f"[ThesisManager] ✓ Batch-CoT inferred {len(results)}/{len(missing)} "
                f"theses in 1 API call"
            )

        except Exception as e:
            logger.warning(f"[ThesisManager] ⚠️  Batch CoT inference failed: {e}. Using fallback.")

        # Fill any missed tickers with fallback
        for ticker, _ in missing:
            if ticker not in results:
                fallback = "Growth Play"
                self._store[ticker] = {
                    "thesis":     fallback,
                    "rationales": [fallback],
                    "inferred":   True,
                    "updated_at": today,
                }
                self._new_tickers.add(ticker)
                results[ticker] = fallback

        if results:
            self._save()

        return results

    # ── Public: main entry point ──────────────────────────────────────────────

    def get_or_infer_thesis(self, ticker: str, sector: str = "Unknown") -> str:
        """
        Return existing thesis if cached; otherwise trigger a CoT Gemini call
        to infer one, persist with inferred=True, and return it.

        This is the primary public API for the MCP-centric architecture.

        Args:
            ticker: NSE/BSE ticker symbol (e.g. 'TMPV', 'SBIN').
            sector: Sector name for context (e.g. 'Automobile'). Helps Gemini
                    pick the right rationale for ambiguous tickers.

        Returns:
            Investment thesis string.
        """
        existing = self.get_thesis(ticker)
        if existing:
            return existing
        return self.infer_and_store(ticker, sector)

    def build_thesis_map(self, tickers_sectors: list[tuple[str, str]]) -> dict[str, str]:
        """
        Return a ticker→thesis mapping for every (ticker, sector) pair.
        Batches ALL missing tickers into a single Gemini API call.
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
                f"[ThesisManager] 🔍 Batch-CoT inferring theses for {len(missing)} "
                f"new ticker(s) in 1 call…"
            )
            inferred = self._batch_infer(missing)
            thesis_map.update(inferred)

        return thesis_map

    def get_new_tickers(self) -> frozenset[str]:
        """Return tickers whose theses were inferred (not pre-existing) this run."""
        return frozenset(self._new_tickers)


# ── Module-level convenience function (the primary MCP-facing API) ────────────

def get_or_infer_thesis(ticker: str, sector: str = "Unknown") -> str:
    """
    Convenience wrapper around ThesisManager.get_or_infer_thesis().

    Creates a fresh ThesisManager instance pointing to the canonical
    thesis_metadata.json and returns the thesis for the given ticker,
    inferring via CoT if not already stored.

    Args:
        ticker: NSE/BSE ticker symbol.
        sector: Optional sector context (improves inference accuracy).

    Returns:
        Investment thesis string.
    """
    tm = ThesisManager()
    return tm.get_or_infer_thesis(ticker, sector=sector)
