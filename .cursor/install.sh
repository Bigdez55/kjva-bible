#!/usr/bin/env bash
#
# Cloud Agent install phase for the KJVA Bible app.
#
# Idempotent repository bootstrap: prepares the Python backend venv and the
# React/Vite frontend dependencies. Safe to run repeatedly against cached state.
#
# The AI-generation path (MLX / XMIND C engine + model weights) is Apple-Silicon
# only and is intentionally not provisioned here; the backend serves the
# documented retrieval-first path (ADR-0003) on linux/amd64.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# --- System dependency -------------------------------------------------------
# The default image ships Python 3.12 without the stdlib venv/ensurepip module.
if ! python3 -c 'import ensurepip' >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq "python3-venv"
fi

# --- Backend (FastAPI) -------------------------------------------------------
python3 -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
python -m pip install --upgrade pip

# MLX is Apple-Silicon-only; strip it for the linux retrieval-only runtime,
# mirroring the Dockerfile and CI.
grep -v '^mlx' backend/requirements.txt > /tmp/kjva-backend-reqs.txt

# `cryptography` supplies the AES-GCM backend the KJVA soul-manager runtime uses
# to bootstrap (without it the cognitive runtime stays un-bootstrapped).
# pytest/httpx/ruff are the test + lint toolchain used by CI.
pip install -r /tmp/kjva-backend-reqs.txt cryptography pytest httpx ruff

# --- Frontend (React + Vite) -------------------------------------------------
cd frontend
npm ci

echo "KJVA Bible install complete."
