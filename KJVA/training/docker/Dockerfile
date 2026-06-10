# Portable training image for TokenlessLM (PyTorch, CPU↔CUDA).
# Runs locally on Docker Desktop (CPU) now; the SAME image runs on a remote/cloud
# Linux+GPU host later with `--gpus all` (build with TORCH_VARIANT=cu121).
#
# Build (CPU, default):   docker build -t tokenless-train -f training/docker/Dockerfile .
# Build (CUDA):           docker build --build-arg TORCH_VARIANT=cu121 -t tokenless-train:cu121 -f training/docker/Dockerfile .
#
# Training code is mounted at runtime (see docker-compose.yml / run_train.sh) so the
# image stays small and the host owns the run/checkpoint artifacts.
FROM python:3.11-slim

# cpu (default) | cu121 | cu124 — selects the PyTorch wheel index.
ARG TORCH_VARIANT=cpu

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TOKENLESS_HOME=/workspace/models_v7/training

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git && \
    rm -rf /var/lib/apt/lists/*

# Torch first (variant-specific index), then framework-neutral training deps.
RUN pip install --upgrade pip && \
    pip install torch --index-url "https://download.pytorch.org/whl/${TORCH_VARIANT}" && \
    pip install numpy safetensors sentencepiece pyyaml pytest

WORKDIR /workspace
# Default to an interactive shell; training is invoked via run_train.sh / compose.
CMD ["bash"]
