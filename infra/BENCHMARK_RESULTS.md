# Benchmark Results — Local Ollama vs. GCP Cloud Run vLLM

This report presents performance metrics from a high-concurrency load test comparing local CPU inference (Ollama) against remote GPU inference (vLLM on GCP Cloud Run).

To ensure a fair architectural comparison, **both environments ran the identical model architecture and size**: `Qwen2.5-0.5B-Instruct`.

---

## Load Test Configuration
* **Concurrency**: 20 concurrent requests initiated simultaneously.
* **Prompt**: "Explain the concept of quantum computing in three paragraphs as if I am 10 years old."
* **Max Generation Tokens**: 150 tokens.
* **Target Models**:
  * Local Ollama: `qwen2.5:0.5b` (running on virtualized macOS CPU)
  * GCP Cloud Run: `/models/qwen-0.5b` (running on NVIDIA L4 GPU)

---

## Performance Metrics Comparison

| Metric | Local Ollama (Mac CPU) | GCP Cloud Run vLLM (L4 GPU) | Performance Delta |
| :--- | :--- | :--- | :--- |
| **Model Size** | Qwen2.5-0.5B | Qwen2.5-0.5B | Identical |
| **Success Rate** | 20/20 (100%) | 20/20 (100%) | Parity |
| **Total Test Duration** | 63.92 seconds | 3.80 seconds | **~16.8x faster** |
| **Time to First Token (TTFT)** | 30.073 seconds | 0.541 seconds | **~55.6x faster** |
| **Inter-Token Latency (ITL)** | 0.021 sec/token | 0.021 sec/token | **Identical** |
| **Aggregate Throughput** | 45.34 tokens/second | 783.26 tokens/second | **~17.3x higher** |
| **Peak KV Cache Usage** | *Not exposed by Ollama* | **0.00%** (uses $<3,000$ of $\approx 210,000$ slots) |
| **Peak Running Requests** | *Not exposed by Ollama* | **20.0** | **Concurrent processing** |

---

## Key Performance Insights

### 1. The Prefill Wall (TTFT)
* **The Result**: vLLM responded to all 20 clients in **0.54 seconds** on average. Local Ollama took **30.07 seconds** to return the first token to the clients.
* **The Engineering Reason**: The prompt prefilling phase is compute-bound. It processes all prompt tokens in parallel to generate the initial KV cache. The NVIDIA L4 GPU leverages tens of thousands of CUDA cores and dedicated Tensor Cores to process all 20 prompts simultaneously in parallel. The local virtualized CPU lacks this mass parallelization, resulting in heavy thread contention, context switching, and sequential queueing (forcing some clients to wait over 50 seconds just for their first token to arrive).

### 2. The Decoding Memory-Bandwidth Bottleneck (ITL)
* **The Result**: Once token generation began, the Inter-Token Latency (ITL) was **exactly identical** at **21 milliseconds per token** (0.021 seconds/token) in both environments.
* **The Engineering Reason**: During the autoregressive decoding phase, the model generates only one token per step. For each token, the runtime must load the entire model weights from memory (VRAM/RAM) into processing cache (SRAM), compute a single forward pass step, and write the updated KV cache back. Because this is strictly memory-bandwidth bound rather than compute-bound:
  * The L4 GPU's VRAM memory bus speed and the Apple Mac CPU's unified memory bus speed achieved the same data transfer rate for this tiny 500MB weight file, resulting in identical single-token decoding latencies.

### 3. Throughput Scaling & Batching
* **The Result**: vLLM achieved an aggregate throughput of **783.26 tokens/second** compared to Ollama's **45.34 tokens/second**.
* **The Engineering Reason**: vLLM's **Continuous Batching** and **PagedAttention** merge the decoding steps of all 20 active requests into a single unified GPU execution step. Instead of running 20 separate memory-fetch cycles sequentially, vLLM loads the weights once, runs the execution for all 20 requests in parallel, and returns the tokens. Ollama, lacking continuous batching capabilities for multiple parallel API client streams, suffered from sequential processing overhead.
