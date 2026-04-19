from loguru import logger
import sys
import config
from mcp_server import evaluate_ticker
from telegram_notifier import send_telegram_update, escape_markdown_v2
from logic.thesis_manager import get_or_infer_thesis

def test_push():
    ticker = "TATASTEEL"
    logger.info(f"Fetching news and evaluating {ticker}...")
    
    results = evaluate_ticker(ticker)
    if not results:
        logger.info("No news found.")
        return
        
    for res in results:
        logger.info(f"Headline: {res['headline']}")
        logger.info(f"Classification: {res['classification']} (Conf: {res['confidence_score']})")
        logger.info(f"Reasoning: {res['reasoning']}\n")
        
    # Pick the first one to send a test alert
    res = results[0]
    thesis = get_or_infer_thesis(ticker)
    
    msg = (
        f"🔔 *TEST PUSH ALERT: {escape_markdown_v2(ticker)}*\n"
        f"📝 *Headline:* {escape_markdown_v2(res['headline'])}\n"
        f"🎯 *Classification:* {res['classification']} \\(Conf: {res['confidence_score']}\\)\n"
        f"💡 *Your Thesis:* {escape_markdown_v2(thesis)}"
    )
    
    logger.info("Sending Telegram message...")
    success = send_telegram_update(msg)
    if success:
        logger.info("✅ Telegram Bot API returned success response.")
    else:
        logger.error("❌ Telegram Bot API failed to send.")

if __name__ == "__main__":
    test_push()
