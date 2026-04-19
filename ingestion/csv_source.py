"""
ingestion/csv_source.py — Portfolio Pulse: CSV Portfolio Source
===============================================================
Concrete PortfolioSource that reads from a local portfolio.csv file.

This is the default ingestion path used today.
Tomorrow, swap in ZerodhaPortfolioSource with zero changes to core logic.
"""

import os
import pandas as pd
from ingestion.base import PortfolioSource

# Resolve relative to project root (one level up from ingestion/)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_CSV  = os.path.join(_PROJECT_ROOT, "portfolio.csv")

# Numeric columns to coerce on load
_NUMERIC_COLS = [
    "Quantity Available",
    "Average Price",
    "Previous Closing Price",
    "Unrealized P&L",
    "Unrealized P&L Pct.",
]


class CSVPortfolioSource(PortfolioSource):
    """
    Reads portfolio data from a local CSV file exported from Zerodha / Kite.

    Args:
        csv_path: Absolute or relative path to the CSV file.
                  Defaults to `portfolio.csv` in the project root.
    """

    def __init__(self, csv_path: str = _DEFAULT_CSV) -> None:
        self._csv_path = csv_path
        self._df: pd.DataFrame | None = None  # lazy-loaded
        
        # ── State Cloud Fallback ───────────────────────────────────────────────────
        if not os.path.exists(self._csv_path):
            import config
            bucket_name = os.getenv("GCS_BUCKET_NAME", "")
            if bucket_name:
                from loguru import logger
                logger.info(f"[CSVPortfolioSource] Local file missing. Fetching from GCS: {bucket_name}")
                try:
                    from google.cloud import storage
                    client = storage.Client()
                    bucket = client.bucket(bucket_name)
                    blob = bucket.blob("portfolio.csv")
                    if blob.exists():
                        blob.download_to_filename(self._csv_path)
                        logger.info(f"[CSVPortfolioSource] ✓ Downloaded portfolio.csv from GCS.")
                    else:
                        raise FileNotFoundError("GCS Blob portfolio.csv not found.")
                except Exception as e:
                    logger.error(f"[CSVPortfolioSource] ⚠️ Failed fetching portfolio.csv from GCS: {e}")

        if not os.path.exists(self._csv_path):
            raise FileNotFoundError(
                f"[CSVPortfolioSource] portfolio.csv not found locally and fallback failed.\n"
                "Place your Zerodha holdings export at that path and retry."
            )

    # ── Internal ──────────────────────────────────────────────────────────────

    def _load(self) -> pd.DataFrame:
        """Load, clean, and return the portfolio DataFrame (cached after first call)."""
        if self._df is not None:
            return self._df

        df = pd.read_csv(self._csv_path)
        df.dropna(how="all", inplace=True)
        df.reset_index(drop=True, inplace=True)

        for col in _NUMERIC_COLS:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        self._df = df
        return self._df

    # ── PortfolioSource interface ─────────────────────────────────────────────

    def get_tickers(self) -> list[str]:
        """
        Return the list of ticker symbols from the CSV.

        Returns:
            List of NSE/BSE ticker strings.
        """
        df = self._load()
        return df["Symbol"].dropna().tolist()

    # ── Extended helpers ──────────────────────────────────────────────────────

    def get_dataframe(self) -> pd.DataFrame:
        """
        Return the full cleaned portfolio DataFrame.
        Callers that need more than just tickers (e.g. P&L, sectors) use this.
        """
        return self._load()

    def get_tickers_with_sectors(self) -> list[tuple[str, str]]:
        """
        Return a list of (ticker, sector) tuples — used by ThesisManager for
        batch thesis inference.
        """
        df = self._load()
        return list(zip(df["Symbol"].tolist(), df["Sector"].fillna("Unknown").tolist()))
