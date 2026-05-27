# Multi-stage build for the KJVA Bible backend.
#
# Per ADR-0003 retrieval-first ordering:
#   - MLX is Apple Silicon only and is NOT installed in this image.
#   - The container runs in retrieval-only mode by default.
#   - For AI fallback on Apple Silicon, mount the weights volume AND run the
#     image on an arm64 host with mlx installed at runtime via a host-pip
#     overlay, OR run the backend natively (outside Docker) on macOS.
#
# Per SLICE-0001 deploy plan:
#   - Volume mount: ./KJVA/training:/app/KJVA/training:ro for weights (optional)
#   - Healthcheck via /api/health
#
# Per SPEC-KJVA-SEC-0001:
#   - Runs as non-root user
#   - No weights baked into image (.dockerignore excludes them)

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# --- deps layer ---
FROM base AS deps
COPY backend/requirements.txt /tmp/requirements.txt
# MLX (Apple Silicon only) is filtered out — retrieval path doesn't need it.
RUN grep -v '^mlx' /tmp/requirements.txt > /tmp/requirements.linux.txt && \
    pip install --no-cache-dir -r /tmp/requirements.linux.txt

# --- runtime ---
FROM base AS runtime

# Copy installed packages
COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# Non-root user
RUN useradd --create-home --shell /bin/bash --uid 1001 appuser

# App layout (matches main.py: cwd=backend, data at ../data, KJVA at ../KJVA)
WORKDIR /app
COPY --chown=appuser:appuser backend/ /app/backend/
COPY --chown=appuser:appuser data/ /app/data/
# KJVA/training/ is a mount point; weights.safetensors NOT in image (per .dockerignore)
RUN mkdir -p /app/KJVA/training && chown -R appuser:appuser /app/KJVA

USER appuser
WORKDIR /app/backend

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; \
        r=urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=2); \
        sys.exit(0 if r.status==200 else 1)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
