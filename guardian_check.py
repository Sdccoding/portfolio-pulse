"""
guardian_check.py — Portfolio Pulse: The Background Guardian (Push Logic)
========================================================================
Designed to be triggered via Cron or GitHub Actions.

Iterates through all portfolio holdings, calls the Critic to evaluate news,
and sends a Telegram alert only if the news is a SIGNAL with high confidence.
"""
from loguru import logger

import sys
import config
from ingestion.csv_source import CSVPortfolioSource
from mcp_server import evaluate_ticker
from telegram_notifier import send_telegram_update

def run_guardian_check():
    logger.info("\n" + "=" * 60)
    logger.info("  🛡️  Portfolio Pulse — Guardian Check Running")
    logger.info("=" * 60)
    
    # 0. Warm up the Webhook API / Cloud Run Instance
    webhook_url = config.TELEGRAM_WEBHOOK_URL
    if webhook_url:
        logger.info(f"  [Ping] Waking up webhook server at {webhook_url}...")
        try:
            # A simple GET request to wake the instance (python-telegram-bot handles it)
            import requests
            requests.get(webhook_url, timeout=5)
        except Exception as e:
            logger.warning(f"  [⚠️] Ping warning: {e}")

    # 1. Fetch all portfolio tickers
    try:
        source = CSVPortfolioSource(csv_path=config.PORTFOLIO_CSV_PATH)
        tickers = source.get_tickers()
    except Exception as e:
        logger.error(f"✗ Failed to load portfolio: {e}")
        sys.exit(1)

    logger.info(f"  • Checking {len(tickers)} tickers for high-signal news...")

    alerts_sent = 0

    # 2. Iterate and evaluate
    for ticker in tickers:
        try:
            results = evaluate_ticker(ticker)
        except Exception as e:
            logger.warning(f"  [⚠️] Error evaluating {ticker}: {e}")
            continue

        for res in results:
            # 3. Filter for High-Signal alerts
            if res.get("classification") == "SIGNAL" and res.get("confidence_score", 0.0) > 0.8:
                
                # Fetch original thesis for context
                from logic.thesis_manager import get_or_infer_thesis
                thesis = get_or_infer_thesis(ticker)
                
                # 4. Format Message Template
                msg = (
                    f"🔔 *HIGH\\-SIGNAL ALERT: {ticker}*\n"
                    f"📝 *Headline:* {res['headline']}\n"
                    f"🎯 *Why it matters:* {res['reasoning']}\n"
                    f"💡 *Your Thesis:* {thesis}"
                )
                
                # Using our Telegram delivery layer (with markdown escaping fixes via the raw notifier or directly here)
                from telegram_notifier import escape_markdown_v2
                msg = (
                    f"🔔 *HIGH\\-SIGNAL ALERT: {escape_markdown_v2(ticker)}*\n"
                    f"📝 *Headline:* {escape_markdown_v2(res['headline'])}\n"
                    f"🎯 *Why it matters:* {escape_markdown_v2(res['reasoning'])}\n"
                    f"💡 *Your Thesis:* {escape_markdown_v2(thesis)}"
                )

                logger.info(f"  [🔥] SIGNAL detected for {ticker}. Sending alert...")
                success = send_telegram_update(msg)
                if success:
                    alerts_sent += 1
                else:
                    logger.error(f"  [❌] Failed to send Telegram alert for {ticker}.")

    logger.info("\n" + "=" * 60)
    logger.info(f"  🛡️  Guardian Check Complete. Sent {alerts_sent} alerts.")
    logger.info("=" * 60 + "\n")


if __name__ == "__main__":
    run_guardian_check()
