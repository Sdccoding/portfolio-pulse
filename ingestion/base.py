"""
ingestion/base.py — Portfolio Pulse: Portfolio Source Abstraction
=================================================================
Defines the abstract interface every portfolio data source must implement.

Today:   CSVPortfolioSource  → reads portfolio.csv
Tomorrow: ZerodhaPortfolioSource → calls Zerodha Kite API

Swapping sources requires zero changes to core logic.
"""

from abc import ABC, abstractmethod


class PortfolioSource(ABC):
    """
    Abstract base class for portfolio data ingestion.

    Any concrete implementation must provide:
      - get_tickers()   → list of NSE/BSE ticker symbols
    """

    @abstractmethod
    def get_tickers(self) -> list[str]:
        """
        Return the list of ticker symbols currently in the portfolio.

        Returns:
            List of ticker strings, e.g. ['SBIN', 'INFY', 'RELIANCE', ...]
        """
        ...
