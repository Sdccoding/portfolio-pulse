# Portfolio Pulse: Product & Architecture Thought Process

This document captures the core product management decisions, architectural choices, and edge-case handling for the **Portfolio Pulse** engine. It is designed to be a reference for technical interviews and product deep-dives.

---

## 1. The Core Evaluation Workflow (How it evaluates a stock)

The system operates on a crisp, 3-step pipeline:

1. **Data Ingestion (The Pull):** The system reaches out to trusted financial feeds (Google News RSS / Yahoo Finance API) and pulls the top 5 most recent headlines for the specific stock.
2. **Context Retrieval (The Memory):** Before evaluating the news, the system checks its local "Memory Bank" (`thesis_metadata.json`) to retrieve the specific **Investment Thesis** for that stock. If none exists, the AI infers and saves one.
3. **The Critic Engine (The Evaluation):** The system packages the **Stock Ticker**, the **News Headline**, and the **Investment Thesis** into a highly constrained prompt. The LLM acts as a strict critic: deciding if the headline structurally impacts the thesis (a **SIGNAL**) or if it's general market chatter (a **NOISE**).

---

## 2. Guardrails & Quality Gating

To ensure the AI doesn't hallucinate or act on unreliable data, we built strict guardrails around data ingestion and response generation.

### The "No-Browsing" Ingestion Guardrail
* **The Problem:** Giving an LLM unrestrained web access leads to hallucinations, unpredictable latencies, and sourcing from unreliable blogs or forums.
* **The Solution:** We architecturally separated **Retrieval** from **Reasoning**. We use Python to deterministically scrape headlines from highly trusted pipes:
  * **Yahoo Finance API**
  * **Google News RSS (India Region Filtered):** Google's algorithm naturally curates top-tier publishers (Moneycontrol, Economic Times, Mint) and filters out low-authority sites.
* **Result:** The AI is strictly fed a string of verified text and is explicitly blocked from browsing the web during the evaluation phase.

### Execution Guardrails
* **JSON Enforcement & Fallbacks:** The LLM must return a strict JSON format (`classification`, `reasoning`, `confidence_score`). If it hallucinates, formats incorrectly, or if the API times out, the system catches the error and defaults to **NOISE**. You are never spammed with broken alerts.
* **Pre-Flight Testing:** We built a verification suite (`verify.py`) that feeds mock "Signal" and "Noise" headlines into the Critic Engine to guarantee the LLM behaves correctly before deploying to production.

---

## 3. The Role of the Investment Thesis

The "Thesis" is the secret weapon of the product. It transforms the system from a generic "news summarizer" into a highly personalized AI hedge fund manager.

1. **The "Ignore Filter" (Silencing Noise):** If your thesis states you hold Tata Motors purely for commercial trucking, the AI will automatically filter out negative news about their EV business. It silences bad news you explicitly don't care about.
2. **The "Weak Signal Amplifier":** If your thesis is "betting on rural demand recovery," a minor 2% increase in rural farming subsidies might be ignored by a generic AI, but our Critic Engine recognizes it as your specific catalyst and upgrades it to a HIGH SIGNAL.
3. **Emotional Anchor:** Stock markets are emotional; financial journalists write clickbait. Forcing the AI to evaluate news strictly through the mathematical lens of your thesis prevents it from giving erratic, panic-driven advice.

### Thesis Lifecycle & Evolution
* **Inference:** The AI uses a Chain-of-Thought (CoT) prompt with web-browsing enabled to research and synthesize a thesis the first time a stock is added.
* **Caching:** Once inferred, it is locked in. This saves API costs and ensures a consistent baseline for future evaluations.
* **Evolution:** If a company fundamentally pivots (e.g., an IT company becomes an AI company) and you decide to keep holding it, you must **recreate the thesis**. Updating the thesis resets the AI's "alarm system" to align with your new strategy.

---

## 4. Why Expose as an MCP (Model Context Protocol) Server?

**The Vision:** The ultimate goal is not to have 50 different fragmented apps (one for finance, one for health, one for calendar). The goal is to build a **Single-Stop Personal Orchestration Agent**.

* **Modularity:** By exposing Portfolio Pulse as an MCP server, it becomes a plug-and-play module. The financial intelligence is encapsulated.
* **Unified Assistant:** Tomorrow, when I build a "Health Tracker MCP" and a "Smart Home MCP," my master orchestration agent (like Claude Desktop or a custom unified bot) can seamlessly query all of them.
* **Context Sharing:** If I ask my master agent "Do I have enough money to buy a new car?", it can autonomously query the Portfolio Pulse MCP to check my stock P&L, then query my Bank MCP, and give me a synthesized answer. MCP is the glue that makes a unified AI ecosystem possible.
