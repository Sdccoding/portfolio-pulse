"""
mcp_server.py — Portfolio Pulse: MCP Server
============================================
Exposes Portfolio Pulse data and tools via the Model Context Protocol (MCP)
using FastMCP.

Start the server:
    python mcp_server.py

Resources:
    portfolio://thesis-metadata  → Full JSON content of thesis_metadata.json

Tools:
    get_portfolio_summary()      → Returns list of current tickers from CSV
"""
from loguru import logger

import json
import os

from fastmcp import FastMCP

import config
from ingestion.csv_source import CSVPortfolioSource

# ── Server ─────────────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="portfolio-pulse",
    instructions=(
        "Portfolio Pulse MCP Server. "
        "Provides access to investment thesis metadata and portfolio summary tools. "
        "Use the thesis-metadata resource to inspect per-ticker investment rationales, "
        "and call get_portfolio_summary() to list current holdings."
    ),
)

# ── Resource: thesis metadata ──────────────────────────────────────────────────

@mcp.resource("portfolio://thesis-metadata")
def thesis_metadata_resource() -> str:
    """
    Returns the full contents of thesis_metadata.json as a JSON string.

    Each key is a ticker symbol. Each value contains:
      - thesis:       primary investment rationale
      - rationales:   list of contributing rationales
      - inferred:     whether the thesis was AI-inferred or manually set
      - updated_at:   date of last update
    """
    path = config.THESIS_METADATA_PATH
    if not os.path.exists(path):
        return json.dumps({})
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return json.dumps(data, indent=2, ensure_ascii=False)


# ── Tool: portfolio summary ───────────────────────────────────────────────────

@mcp.tool()
def get_portfolio_summary() -> dict:
    """
    Returns a summary of the current portfolio holdings.

    Reads the CSV portfolio file and returns:
      - tickers: list of all ticker symbols
      - count:   total number of holdings
    """
    source  = CSVPortfolioSource(csv_path=config.PORTFOLIO_CSV_PATH)
    tickers = source.get_tickers()
    return {
        "count":   len(tickers),
        "tickers": tickers,
    }


# ── Tool: Evaluate Ticker ───────────────────────────────────────────────────

@mcp.tool()
def evaluate_ticker(ticker: str) -> list[dict]:
    """
    Evaluates recent news for a ticker against its established investment thesis.

    1. Fetches top 3-5 news headlines using YFinance.
    2. Runs each headline through the Critic engine to classify as SIGNAL or NOISE.
    3. Returns the list of structured results.
    """
    from ingestion.news_source import GoogleNewsSource
    from logic.critic import evaluate_news

    source = GoogleNewsSource()
    headlines = source.get_top_news(ticker, limit=5)
    
    results = []
    for headline in headlines:
        decision = evaluate_news(ticker, headline)
        results.append(decision)
        
    return results

# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("[MCP] Starting Portfolio Pulse MCP Server…")
    mcp.run()
