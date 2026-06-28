import os
import sys
import time
import asyncio
import subprocess
import urllib.request
import re
from openai import AsyncOpenAI

# Configuration
CONCURRENT_REQUESTS = 20
PROMPT = "Explain the concept of quantum computing in three paragraphs as if I am 10 years old."
MAX_TOKENS = 150

def get_gcloud_token(service_url):
    try:
        result = subprocess.run(
            ["gcloud", "auth", "print-identity-token"],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except Exception as e:
        print(f"Warning: Could not fetch identity token: {e}")
        return None

def poll_metrics_sync(url, token=None):
    try:
        req = urllib.request.Request(url)
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req, timeout=2) as response:
            content = response.read().decode('utf-8')
            
        metrics = {}
        for line in content.splitlines():
            if line.startswith("#") or not line.strip():
                continue
            match = re.match(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{[^}]*\})?\s+([eE0-9.-]+)', line.strip())
            if match:
                name, val = match.groups()
                metrics[name] = float(val)
        return metrics
    except Exception:
        return None

async def poll_metrics_loop(metrics_url, token, stop_event, stats):
    while not stop_event.is_set():
        res = await asyncio.to_thread(poll_metrics_sync, metrics_url, token)
        if res:
            for k in ["vllm:kv_cache_usage_perc", "vllm:num_requests_running", "vllm:num_requests_waiting"]:
                if k in res:
                    stats[k] = max(stats.get(k, 0.0), res[k])
        await asyncio.sleep(0.1)

async def send_request(client, model, request_id):
    start_time = time.perf_counter()
    ttft = None
    total_tokens = 0
    
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": PROMPT}],
            max_tokens=MAX_TOKENS,
            temperature=0.7,
            stream=True
        )
        
        async for chunk in response:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            content = delta.content if hasattr(delta, "content") else None
            
            if content:
                if ttft is None:
                    # Time to first token
                    ttft = time.perf_counter() - start_time
                total_tokens += len(content.split())
                
        end_time = time.perf_counter()
        total_duration = end_time - start_time
        
        if ttft is None:
            ttft = total_duration
            
        itl = (total_duration - ttft) / max(total_tokens - 1, 1)
        
        return {
            "success": True,
            "request_id": request_id,
            "total_duration": total_duration,
            "ttft": ttft,
            "itl": itl,
            "total_tokens": total_tokens
        }
    except Exception as e:
        print(f"Request {request_id} failed: {e}")
        return {
            "success": False,
            "request_id": request_id,
            "error": str(e)
        }

async def run_benchmark(name, base_url, model, token=None, metrics_url=None):
    print(f"\n==================================================")
    print(f"Starting Benchmark: {name}")
    print(f"Target URL: {base_url}")
    print(f"Model: {model}")
    print(f"Concurrency: {CONCURRENT_REQUESTS} concurrent requests")
    print(f"==================================================")
    
    client = AsyncOpenAI(
        base_url=base_url,
        api_key=token or "not-needed"
    )
    
    stats = {}
    stop_event = asyncio.Event()
    polling_task = None
    
    if metrics_url:
        polling_task = asyncio.create_task(
            poll_metrics_loop(metrics_url, token, stop_event, stats)
        )
        
    start_time = time.perf_counter()
    tasks = [send_request(client, model, i) for i in range(CONCURRENT_REQUESTS)]
    results = await asyncio.gather(*tasks)
    end_time = time.perf_counter()
    
    if polling_task:
        stop_event.set()
        await polling_task
        
    total_run_duration = end_time - start_time
    
    successful_runs = [r for r in results if r["success"]]
    
    if not successful_runs:
        print("All requests failed. Benchmark incomplete.")
        return
        
    avg_ttft = sum(r["ttft"] for r in successful_runs) / len(successful_runs)
    avg_itl = sum(r["itl"] for r in successful_runs) / len(successful_runs)
    total_tokens = sum(r["total_tokens"] for r in successful_runs)
    throughput = total_tokens / total_run_duration
    
    print("\nResults:")
    print(f"- Success rate: {len(successful_runs)}/{CONCURRENT_REQUESTS}")
    print(f"- Total Run Duration: {total_run_duration:.2f} seconds")
    print(f"- Average Time to First Token (TTFT): {avg_ttft:.3f} seconds")
    print(f"- Average Inter-Token Latency (ITL): {avg_itl:.3f} seconds/token")
    print(f"- Total Estimated Tokens Generated: {total_tokens}")
    print(f"- Throughput: {throughput:.2f} tokens/second")
    
    if metrics_url:
        print(f"- Peak KV Cache Usage: {stats.get('vllm:kv_cache_usage_perc', 0.0) * 100:.2f}%")
        print(f"- Peak Running Requests: {stats.get('vllm:num_requests_running', 0.0)}")
        print(f"- Peak Waiting Requests: {stats.get('vllm:num_requests_waiting', 0.0)}")
        
    print(f"==================================================\n")

async def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "both"
    
    if target in ("local", "both"):
        await run_benchmark(
            name="Local Ollama",
            base_url="http://localhost:11434/v1",
            model="qwen2.5:0.5b"
        )
        
    if target in ("gcp", "both"):
        service_url = "https://vllm-server-111880092623.us-central1.run.app"
        token = get_gcloud_token(service_url)
        if not token:
            print("Could not obtain OIDC token for GCP. Skipping GCP benchmark.")
            return
            
        await run_benchmark(
            name="GCP Cloud Run vLLM (L4 GPU)",
            base_url=f"{service_url}/v1",
            model="/models/qwen-0.5b",
            token=token,
            metrics_url=f"{service_url}/metrics"
        )

if __name__ == "__main__":
    asyncio.run(main())
