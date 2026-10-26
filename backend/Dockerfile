# AURA-3 API image. Local development runs the API directly with `uv run`; this image is for
# packaging the service. Code execution needs a reachable Docker daemon (DOCKER_HOST).
FROM python:3.13-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /usr/local/bin/uv

# libgomp: onnxruntime (TitanOCR, fastembed); libglib: opencv-python-headless.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 aura

ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app
COPY --chown=aura:aura pyproject.toml uv.lock ./
COPY --chown=aura:aura vendor ./vendor
RUN uv sync --frozen --no-dev --extra viz

COPY --chown=aura:aura . .
RUN mkdir -p /app/data && chown aura:aura /app/data
USER aura

# OCR models are fetched once at build time so the service never downloads at boot.
RUN uv run --no-sync titanocr models
ENV TITANOCR_OFFLINE=1

EXPOSE 8010
CMD ["uvicorn", "aura.api.app:app", "--host", "0.0.0.0", "--port", "8010"]
