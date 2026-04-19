"""
interactive_bot.py — Portfolio Pulse: The Interactive Advisor (Pull Logic)
========================================================================
A Python Telegram Bot that listens for ticker commands and interacts with
the MCP server to return personalized, thesis-aware news evaluation.

Usage: Send a ticker symbol (e.g. "TATASTEEL" or "/check INFY") to the bot.
"""
from loguru import logger

import os
import sys
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

import config
from mcp_server import evaluate_ticker
from logic.thesis_manager import get_or_infer_thesis

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

import uuid

async def _process_ticker_check(ticker: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Core logic to check a ticker, evaluate news, and reply via Telegram."""
    ticker = ticker.upper().strip()
    
    trace_id = str(uuid.uuid4())[:8]
    with logger.contextualize(trace_id=trace_id):
        logger.info(f"Received interactive /check request for {ticker}")
        await update.message.reply_text(f"🔍 Checking latest news against your thesis for {ticker}...")
    
        # Fetch/Infer Thesis (Agentic Discovery if not present)
        thesis = get_or_infer_thesis(ticker)

        # Evaluate News via MCP tool
        try:
            results = evaluate_ticker(ticker)
        except Exception as e:
            await update.message.reply_text(f"⚠️ Error evaluating {ticker}: {e}")
            return

        if not results:
            await update.message.reply_text(f"No recent news found for {ticker}.")
            return

        # Format the response
        lines = [f"📊 *Analysis for {ticker}*"]
        lines.append(f"💡 _Thesis: {thesis}_\n")

        for idx, res in enumerate(results, 1):
            classification = res.get("classification", "NOISE")
            emoji = "🔥" if classification == "SIGNAL" else "📉"
            conf = res.get("confidence_score", 0.0)
            
            lines.append(f"{idx}. {emoji} *{classification}* (Conf: {conf:.2f})")
            lines.append(f"   📝 *Headline:* {res.get('headline')}")
            lines.append(f"   🎯 *Reasoning:* {res.get('reasoning')}\n")

        full_message = "\n".join(lines)
        
        # Telegram max length is 4096. We clip loosely if it's too long.
        if len(full_message) > 4000:
            full_message = full_message[:4000] + "\n...[Truncated]"

        await update.message.reply_text(full_message, parse_mode='Markdown')


async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for the /check command (e.g. /check INFY)"""
    if not context.args:
        await update.message.reply_text("Please provide a ticker symbol. Example: /check INFY")
        return
    
    ticker = context.args[0]
    await _process_ticker_check(ticker, update, context)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for plain text messages. Assumes the user sent a ticker symbol."""
    ticker = update.message.text
    if len(ticker.split()) == 1 and ticker.isalnum():
        await _process_ticker_check(ticker, update, context)
    else:
        await update.message.reply_text("Please send a valid ticker symbol (e.g., TATASTEEL) or use /check <TICKER>.")


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or token.startswith("your_"):
        logger.error("❌ TELEGRAM_BOT_TOKEN is missing or not configured in .env")
        sys.exit(1)

    application = ApplicationBuilder().token(token).build()

    # Handlers
    application.add_handler(CommandHandler("check", check_command))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))

    # Determine mode: Webhook vs Polling
    webhook_url = config.TELEGRAM_WEBHOOK_URL
    if webhook_url:
        logger.info(f"🟢 Starting in WEBHOOK mode. URL: {webhook_url}")
        # When deploying to Cloud Run, the port is provided by the PORT env var.
        port = int(os.environ.get("PORT", "8080"))
        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=token,
            webhook_url=f"{webhook_url}/{token}"
        )
    else:
        logger.info("🟡 Starting in POLLING mode (Local Dev).")
        application.run_polling()


if __name__ == '__main__':
    main()
