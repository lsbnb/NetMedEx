FROM python:3.11-slim-bookworm AS builder
WORKDIR /app

# Install build deps
RUN pip install --no-cache-dir --upgrade pip

# Install project and production deps
COPY pyproject.toml .
COPY netmedex/ netmedex/
COPY webapp/ webapp/
RUN pip install --no-cache-dir ".[api]" gunicorn

# ── Runtime stage ──────────────────────────────────────────────────────────────
FROM python:3.11-slim-bookworm
WORKDIR /app

# Non-root user for security
RUN useradd -m -u 1000 appuser

# Copy installed packages and app from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app

# Create writable data directory and cache directory
RUN mkdir -p /app/data /app/webapp/cache && chown -R appuser:appuser /app

USER appuser

EXPOSE 8050
ENV HOST=0.0.0.0 \
    PORT=8050 \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg \
    JUPYTER_PLATFORM_DIRS=0

CMD ["gunicorn", \
     "--bind", "0.0.0.0:8050", \
     "--workers", "2", \
     "--threads", "4", \
     "--timeout", "120", \
     "--keep-alive", "5", \
     "--log-level", "info", \
     "webapp.wsgi:application"]
