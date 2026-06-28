# Local vLLM Testing Guide

This guide details how to spin up a lightweight, CPU-compatible **vLLM** container locally on macOS via Docker Desktop for testing the `vllm` execution path before deploying to GCP.

---

## 1. Run vLLM Locally via Docker Desktop

To run vLLM on macOS (with CPU support or Rosetta emulation), use the official `vllm-openai` image serving an ultra-small instruction-following model like **Qwen 2.5 (0.5B)** or **TinyLlama (1.1B)**:

### Option A: Qwen 2.5 (0.5B) - Recommended (Super Lightweight)
```bash
docker run -d -p 8000:8000 \
  --name local-vllm \
  --ipc=host \
  vllm/vllm-openai:latest \
  --model Qwen/Qwen2.5-0.5B-Instruct \
  --device cpu
```

### Option B: TinyLlama (1.1B)
```bash
docker run -d -p 8000:8000 \
  --name local-vllm \
  --ipc=host \
  vllm/vllm-openai:latest \
  --model TinyLlama/TinyLlama-1.1B-Chat-v1.0 \
  --device cpu
```

### Check Container Status
Wait a few seconds for the model to download and load into memory. You can inspect the logs or query the active models endpoint to confirm vLLM is ready:

```bash
# View startup logs
docker logs -f local-vllm

# Query models list
curl http://localhost:8000/v1/models
```

---

## 2. Local `.env` Verification Toggle

To route all LLM requests from Portfolio Pulse to your local vLLM container, open `.env` and configure the following variables:

```env
# LLM Provider Configuration
LLM_PROVIDER="vllm"
VLLM_BASE_URL="http://localhost:8000/v1"
VLLM_MODEL="Qwen/Qwen2.5-0.5B-Instruct"  # Match the model specified in the docker run command
```

---

## 3. Verify the Integration

Once `.env` is configured to use `vllm`, run the dry-run test suite to ensure the client connects to vLLM and handles mock responses cleanly:

```bash
python dry_run_test.py
```

To run a safe end-to-end simulation of the daily briefing pipeline without sending a Telegram update:

```bash
python main.py --dry-run
```
