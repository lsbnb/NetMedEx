FROM python:3.11-slim-bookworm AS builder
LABEL version="v1.3.1"
WORKDIR /app

# Install build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --upgrade pip

# Install project and production deps
COPY pyproject.toml .
COPY netmedex/ netmedex/
COPY webapp/ webapp/
RUN pip install --no-cache-dir ".[api]" gunicorn

# Pre-download ChromaDB ONNX embedding model (~80 MB).
# Must CALL the function — instantiation alone does not trigger download.
RUN python -c "from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2; ef = ONNXMiniLM_L6_V2(); ef(['warmup'])" && \
    ls -la /root/.cache/chroma/onnx_models/

# ── Runtime stage ──────────────────────────────────────────────────────────────
FROM python:3.11-slim-bookworm
WORKDIR /app

# Non-root user for security
RUN useradd -m -u 1000 appuser

# Copy installed packages and app from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app

# Copy pre-downloaded ONNX model cache into appuser home
COPY --from=builder /root/.cache/chroma /home/appuser/.cache/chroma

# Create writable data directory and cache directory; set ownership
RUN mkdir -p /app/data /app/webapp/cache && \
    chown -R appuser:appuser /app /home/appuser/.cache

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER appuser

EXPOSE 8050
ENV HOST=0.0.0.0 \
    PORT=8050 \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg \
    JUPYTER_PLATFORM_DIRS=0

ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", \
     "--bind", "0.0.0.0:8050", \
     "--workers", "1", \
     "--threads", "4", \
     "--timeout", "300", \
     "--keep-alive", "5", \
     "--log-level", "info", \
     "webapp.wsgi:application"]
