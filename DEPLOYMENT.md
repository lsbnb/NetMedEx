# Deploying NetMedEx

NetMedEx is container-ready and can be easily deployed using Docker.

## Prerequisites
- Docker installed on your host machine.
- OpenAI API Key (for RAG/Semantic features).

## 1. Building the Docker Image
Run the following command in the project root directory:

```bash
docker build -t netmedex:V0.9.7 .
```

2.  **Tag for Docker Hub or Registry (Optional)**

```bash
docker tag netmedex:V0.9.7 [USERNAME]/netmedex:V0.9.7
```

3.  **Run with Local LLM (Ollama)**

Using `docker-compose.yml`:

```bash
docker compose up -d
```

Or standalone:

```bash
docker run -d \
  -p 8050:8050 \
  --name netmedex-app \
  -v $(pwd)/.env:/app/.env \
  netmedex:V0.9.7
```

> [!IMPORTANT]
> **Access the Application**: Once the container is running, open your browser and go to:
> **[http://localhost:8050](http://localhost:8050)**

## Configuration
You can customize the deployment using environment variables:

- `PORT`: Internal port (default: 8050)
- `workers`: Number of Gunicorn workers (default: 2, modify in Dockerfile CMD)
- `threads`: Threads per worker (default: 4, modify in Dockerfile CMD)

## Production Notes
- The Docker image uses **Gunicorn** as a production-grade WSGI server.
- The base image is `python:3.11-slim-bookworm` for a small footprint.
