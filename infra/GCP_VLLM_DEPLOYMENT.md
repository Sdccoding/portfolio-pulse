# GCP vLLM Deployment Guide

This guide details the production architecture and step-by-step instructions to deploy a highly optimized, open-source **vLLM** inference server on Google Cloud Platform (GCP).

---

## 1. Production Architecture Overview

To run open-source models (like `Llama-3.1-8B-Instruct` or `Qwen2.5-7B-Instruct`) efficiently in production, we use the following GCP services:

1. **Google Cloud Run (Serverless GPU)**: Serves the vLLM container. Cloud Run supports **Nvidia L4 GPUs (24GB VRAM)** in specific regions (e.g. `us-central1`). It provides automatic scaling, HTTPS endpoints out of the box, and security via IAM.
2. **Google Cloud Storage (GCS) FUSE Mount**: Rather than downloading gigabytes of model weights from Hugging Face every time a container scales up (causing heavy cold start delays), we pre-store model weights in a GCS bucket and mount it directly into the Cloud Run container at `/models` using Cloud Run's native GCS FUSE integration.

```
┌────────────────────────────────────────────────────────┐
│                   Google Cloud Run                     │
│                                                        │
│   ┌───────────────────┐        ┌───────────────────┐   │
│   │  Portfolio Pulse  │        │       vLLM        │   │
│   │    App Engine     │───────>│  Inference Server │   │
│   └───────────────────┘        └───────────────────┘   │
└──────────────────────────────────┬─────────────────────┘
                                   │ (GCS FUSE Mount)
                                   ▼
                        ┌─────────────────────┐
                        │   GCS Model Bucket  │
                        │ (Pre-cached weights)│
                        └─────────────────────┘
```

---

## 2. Step 1: Cache Model Weights in a GCS Bucket

First, we create a bucket and download the Hugging Face model weights into it.

1. **Create the GCS Bucket**:
   ```bash
   gcloud storage buckets create gs://portfolio-pulse-models --region=us-central1
   ```

2. **Download Model Weights (Run locally or on a VM)**:
   Use `huggingface-cli` to download the specific model weights directly:
   ```bash
   # Install HF Hub CLI
   pip install huggingface_hub

   # Download model weights to a local directory
   huggingface-cli download Qwen/Qwen2.5-7B-Instruct --local-dir ./qwen-7b
   ```

3. **Upload to GCS**:
   ```bash
   gcloud storage cp -r ./qwen-7b gs://portfolio-pulse-models/qwen-7b
   ```

---

## 3. Step 2: Deploy vLLM to Cloud Run (with GPU)

Deploy the official `vllm/vllm-openai:latest` image to Cloud Run, specifying GPU execution and mounting the GCS bucket.

```bash
gcloud beta run deploy vllm-server \
  --image=vllm/vllm-openai:latest \
  --region=us-central1 \
  --cpu=8 \
  --memory=32Gi \
  --gpu=1 \
  --gpu-type=nvidia-l4 \
  --no-allow-unauthenticated \
  --port=8080 \
  --add-volume=name=model-volume,type=cloud-storage,bucket=portfolio-pulse-models \
  --add-volume-mount=volume=model-volume,mount-path=/models \
  --set-env-vars=HF_HUB_OFFLINE=1,HF_HOME=/models/cache \
  --command="python3" \
  --args="-m","vllm.entrypoints.openai.api_server","--model","/models/qwen-7b","--port","8080","--max-model-len","4096","--enforce-eager"
```

### Explaining the deployment flags:
* `--gpu=1 --gpu-type=nvidia-l4`: Requests a single Nvidia L4 GPU (24GB VRAM).
* `--add-volume`: Integrates the GCS bucket (`portfolio-pulse-models`) as a file volume.
* `--add-volume-mount`: Mounts that bucket inside the container at `/models`.
* `HF_HUB_OFFLINE=1`: Forces vLLM to load the model from the local `/models/qwen-7b` mount instead of querying Hugging Face.
* `--enforce-eager`: Disables CUDA graph compilation, which saves GPU memory and speeds up cold startup.

---

## 4. Step 3: Configure the Portfolio Pulse Client

Once the vLLM server is deployed, copy its Service URL (e.g. `https://vllm-server-xxxx.run.app`). 

Update the Portfolio Pulse environment variables in your main application's deployment configuration (or `.env` file):

```env
LLM_PROVIDER="vllm"
VLLM_BASE_URL="https://vllm-server-xxxx.run.app/v1"
VLLM_MODEL="/models/qwen-7b"
```

Because vLLM is protected behind Google IAM, ensure the service account running your main Portfolio Pulse Cloud Run container has the **Cloud Run Invoker** (`roles/run.invoker`) role for the `vllm-server` service.
