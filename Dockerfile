FROM python:3.11-slim-bookworm
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir . gunicorn

EXPOSE 8050
ENV HOST=0.0.0.0
CMD ["gunicorn", "--bind", "0.0.0.0:8050", "--workers", "2", "--threads", "4", "webapp.wsgi:application"]
