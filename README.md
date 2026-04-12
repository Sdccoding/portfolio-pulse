# 🟢 Portfolio Pulse

**Portfolio Pulse** is an AI-powered portfolio briefing engine that delivers daily qualitative and quantitative insights directly to your Telegram. It leverages **Google Gemini 2.5 Flash** with Google Search grounding to analyze your stocks, identify red/green flags, and suggest fresh market opportunities.

---

## 🚀 Key Features

- **Efficient AI Analysis**: Uses a optimized 2-call Gemini architecture to analyze your entire portfolio without hitting API rate limits.
- **Sentiment Tracking**: Automatically categorizes news into **Green Flags** (positive), **Red Flags** (negative), and **Watch List** items.
- **Actionable Deep Dives**: Provides specific "BUY MORE", "HOLD", or "CONSIDER EXIT" signals for flagged holdings with detailed rationales.
- **Live Scout Picks**: Every run fetches 3 fresh "Scout Suggestions" from the Indian market using live Google Search data.
- **Telegram Integration**: Beautifully formatted reports delivered to your phone every morning.
- **Financial Snapshot**: Real-time calculation of Invested Value, Present Value, and Unrealized P&L.

---

## 🛠️ Setup Instructions

### 1. Prerequisites
- Python 3.11+
- A [Gemini API Key](https://aistudio.google.com/app/apikey)
- A Telegram Bot (created via [@BotFather](https://t.me/botfather))
- Your Telegram Chat ID (via [@userinfobot](https://t.me/userinfobot))

### 2. Manual Data Input
You must manually place your portfolio data in the project root:
1. Export your portfolio as a CSV from your broker.
2. Ensure it is named `portfolio.csv`.
3. Place it in the same directory as `main.py`.

> [!IMPORTANT]
> The script expects specific columns like `Symbol`, `Average Price`, `Quantity Available`, and `Previous Closing Price`.

### 3. Environment Variables
Create a `.env` file in the root directory:
```env
GEMINI_API_KEY=your_gemini_api_key
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
```

### 4. Installation
```bash
pip install -r requirements.txt
```

---

## 📈 Usage

### Run Manually
To generate and send a report immediately:
```bash
python main.py
```

### Dry Run (Preview)
To see the report in your terminal without sending it to Telegram:
```bash
python main.py --dry-run
```

### Equity Only Analysis
To skip Mutual Funds/ETFs and only analyze direct stocks:
```bash
python main.py --equity-only
```

---

## 🤖 Daily Automation (GitHub Actions)

This project is configured to run automatically using GitHub Actions. A cron job is set to trigger every day at **08:00 AM IST** (02:30 UTC).

### Steps to enable automation:
1. Go to your GitHub Repository **Settings** > **Secrets and variables** > **Actions**.
2. Add the following **Repository Secrets**:
   - `GEMINI_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
3. The workflow is already defined in `.github/workflows/daily_report.yml`.

Every morning, you will receive a notification with your portfolio's health, news analysis, and fresh stock picks.

---

## 📄 The Daily Report Includes:
- **Financial Snapshot**: Your total wealth and profit/loss summary.
- **Portfolio Health**: AI-generated health score and top-level rationale.
- **Sentiment Flags**: 🟢 Positive news vs 🔴 Negative impact news.
- **Strategy Deep Dive**: Specific calls (Buy/Sell/Hold) for stocks with major news.
- **Scout Suggestions**: 🔭 3 trending stock ideas for the day based on fresh market research.

---

## 📂 Project Structure

```text
.
├── .github/
│   └── workflows/
│       └── daily_report.yml    # Automation cron job configuration
├── core.py                    # Dual-call Gemini analysis pipeline
├── main.py                    # Main orchestrator (entry point)
├── telegram_notifier.py       # Telegram formatting and notification logic
├── requirements.txt           # Python dependencies
├── portfolio.csv              # USER INPUT: Your actual holdings
├── scout_suggestions.json     # Cached/recent scout stock picks
├── dry_run_test.py            # Local testing script
├── .gitignore                 # Files/folders to ignore in Git
└── .env                       # Environment variables (Local only)
```

