"""
ingestion/news_source.py — Portfolio Pulse: News Source Abstraction
===================================================================
Defines the abstract interface for filtering and retrieving news headlines.

Today:   YFinanceNewsSource  → fetches news directly from Yahoo Finance
Tomorrow: SearchNewsSource   → fetches from Bing/Google APIs
"""
from loguru import logger

import abc
import yfinance as yf


class NewsSource(abc.ABC):
    """
    Abstract base class for news data ingestion.
    """

    @abc.abstractmethod
    def get_top_news(self, ticker: str, limit: int = 5) -> list[str]:
        """
        Return the top news headlines for the given ticker.

        Args:
            ticker: NSE/BSE ticker symbol (e.g. 'SBIN', 'TATASTEEL')
            limit: Maximum number of headlines to return (default 5)

        Returns:
            List of news headline strings.
        """
        ...


import requests

class YFinanceNewsSource(NewsSource):
    """
    Retrieves the latest news headlines using the yfinance library.
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        })

    def get_top_news(self, ticker: str, limit: int = 5) -> list[str]:
        yf_ticker = ticker
        if not yf_ticker.endswith(".NS") and not yf_ticker.endswith(".BO"):
            yf_ticker = f"{ticker}.NS"

        try:
            ticker_obj = yf.Ticker(yf_ticker, session=self.session)
            news = ticker_obj.news
            logger.info(f"[YFinanceNewsSource] Fetched {len(news) if news else 0} raw news items for {yf_ticker}")

            if not news:
                return []

            headlines = []
            for item in news[:limit]:
                title = item.get("title")
                if title:
                    headlines.append(title)
            return headlines
        except Exception as e:
            logger.warning(f"[YFinanceNewsSource] ⚠️ Failed fetching news for {ticker}: {e}")
            return []


import xml.etree.ElementTree as ET
import urllib.parse

class GoogleNewsSource(NewsSource):
    """
    Retrieves the latest news headlines using Google News RSS, dynamically
    pulling results from top Indian providers (Moneycontrol, Economic Times, etc.)
    """
    def get_top_news(self, ticker: str, limit: int = 5) -> list[str]:
        # Clean ticker if it has NSE extensions natively
        clean_ticker = ticker.split('.')[0]
        query = urllib.parse.quote(f"{clean_ticker} NSE stock news")
        url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
        
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                logger.warning(f"[GoogleNewsSource] ⚠️ Non-200 response: {resp.status_code}")
                return []
                
            root = ET.fromstring(resp.content)
            headlines = []
            for item in root.findall('.//item')[:limit]:
                title = item.find('title')
                if title is not None and title.text:
                    headlines.append(title.text)
                    
            logger.info(f"[GoogleNewsSource] Fetched {len(headlines)} headlines for {ticker}")
            return headlines
        except Exception as e:
            logger.error(f"[GoogleNewsSource] ⚠️ Failed fetching news for {ticker}: {e}")
            return []
