# 🟢 Portfolio Pulse

**Portfolio Pulse** is an AI-powered portfolio briefing engine that delivers qualitative and quantitative insights directly to your Telegram. It leverages **Google Gemini 2.5 Flash** with native Google News RSS scraping to analyze your stock investments, identify red/green flags, and extract actionable market advice.

---

## 🚀 Key Features

- **Flexible LLM Execution**: Supports **Google Gemini 2.5 Flash** (default cloud), **Local Ollama** (with client-side DuckDuckGo tool-calling grounding), and **GCP Cloud Run vLLM** (high-performance NVIDIA L4 GPU serverless serving).
- **Sentiment Tracking**: Automatically categorizes news into **Green Flags** (positive), **Red Flags** (negative), and **Watch List** items.
- **Actionable Deep Dives**: Provides specific "BUY MORE", "HOLD", or "CONSIDER EXIT" signals for flagged holdings based on strict market indicators.
- **Zero-Cost Scaling**: Runs entirely serverless within the free tiers of **Google Cloud Run** and **GCP Cloud Scheduler**.
- **Financial Snapshot**: Aggregates Invested Value, Present Value, and Unrealized P&L natively from broker exports.

---

## 🛠️ Setup Instructions

### 1. Prerequisites
- Python 3.11+
- A Google Cloud Platform (GCP) Project with **Cloud Run** and **Cloud Storage** enabled.
- A Gemini API Key (Generate one for free at Google AI Studio)
- A Telegram Bot (created via [@BotFather](https://t.me/botfather))

### 2. Google Cloud Storage (GCS)
Your portfolio state and investment memories are natively secured inside Google Cloud Storage.
1. Create a GCS bucket (e.g., `gs://portfolio-pulse-memory/`).
2. Upload your broker's `portfolio.csv` to this bucket.

### 3. Serverless Deployment
The infrastructure is 100% Serverless and runs reliably without manual interactions.
It consists of exactly three pillars:
1. **Interactive Webhook**: Deployed as a web service (`gcloud run deploy ...`).
2. **Daily Briefing**: Deployed as a Cloud Run Job mapped to `main.py`.
3. **Passive Guardian**: Deployed as a Cloud Run Job mapped to `guardian_check.py`.

---

## 📈 The Three Engine Pillars (Usage)

This system is fully automated and designed to cover you comprehensively:

### 1. Telegram Chat (Interactive)
Send `/check TICKER` (e.g., `/check HDFCBANK`) to your Telegram bot. 
The Webhook instance securely queries Google News RSS, evaluates it against your formally inferred investment thesis, and instantly responds with an analysis.

### 2. Passive Monitoring (The Guardian)
Triggered securely via GCP Cloud Scheduler periodically (every 4 hours). 
The job spins up `guardian_check.py`, silently iterating over your portfolio and ONLY sending a proactive Telegram push if a High-Signal (e.g., an alarming drop or huge breakout event) is detected organically in the news layer.

### 3. Daily Briefings (The Orchestrator)
Triggered securely via GCP Cloud Scheduler strictly at 8:00 AM IST daily.
The job spins up `main.py`, securely downloading your `portfolio.csv` out of your GCS bucket, and structuring the ultimate morning summary push containing:
- **Financial Snapshot**: Wealth and P&L.
- **Portfolio Health**: AI-generated health score.
- **Strategy Deep Dive**: Specific calls (Buy/Sell/Hold).
- **Scout Suggestions**: 🔭 3 trending stock ideas for the day.

---

## 📂 Project Structure

```text
.
├── ingestion/                 # Abstracted Data Input Layer
│   ├── csv_source.py          # State engine loading configs from GCS natively
│   └── news_source.py         # Google News RSS scraper natively bypassing subnets
├── logic/                     # The Core Machine Learning architectures
│   ├── thesis_manager.py      # Automated Thesis inference & memory persistence
│   ├── critic.py              # Evaluates NOISE vs SIGNAL metrics natively
│   └── llm_client.py          # Gemini 2.5 flash injection binding
├── main.py                    # The Daily Orchestrator (Pillar 3)
├── guardian_check.py          # The Passive Monitor (Pillar 2)
├── interactive_bot.py         # The Interactive Chat Engine (Webhook / Pillar 1)
├── telegram_notifier.py       # Core telemetry logic for routing notifications
├── requirements.txt           # Python dependencies
└── .gitignore                 # Actively blocks local sensitive CSVs from Git leaks
```

---

## ⚡ Inference Engines & Benchmarking

The briefing engine supports running inference across three primary backends:
1. **Google Gemini 2.5 Flash** (Production Cloud API - Default)
2. **Local Ollama** (Fully offline CPU/M-series Mac, uses `qwen2.5:0.5b` or `llama3.1`)
3. **GCP Cloud Run vLLM** (Serverless NVIDIA L4 GPU deployment running `Qwen2.5-0.5B-Instruct` mounted via GCS FUSE)

To inspect setup guides, load-testing scripts, or performance results comparing these engines under concurrency:
* **Local Ollama Setup Guide**: See [LOCAL_VLLM_TESTING.md](infra/LOCAL_VLLM_TESTING.md)
* **GCP Cloud Run vLLM GPU Serverless Deployment Guide**: See [GCP_VLLM_DEPLOYMENT.md](infra/GCP_VLLM_DEPLOYMENT.md)
* **Concurrent Load Testing Script**: See [benchmark_load.py](infra/benchmark_load.py)
* **Performance Benchmark Results**: See [BENCHMARK_RESULTS.md](infra/BENCHMARK_RESULTS.md) for TTFT, ITL, and KV Cache metrics under load.

