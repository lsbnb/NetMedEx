# Deploying NetMedEx

NetMedEx is container-ready and can be easily deployed using Docker.

## Prerequisites
- Docker installed on your host machine.
- OpenAI API Key (for RAG/Semantic features).

## 1. Building the Docker Image
Run the following command in the project root directory:

```bash
docker build -t netmedex:v0.6.0 .
```

## 2. Running the Container
To run the application, you need to provide your OpenAI API key as an environment variable.

```bash
docker run -d \
  -p 8050:8050 \
  -e OPENAI_API_KEY="your-api-key-here" \
  --name netmedex-app \
  netmedex:v0.6.0
```

The application will be available at `http://localhost:8050`.

## Configuration
You can customize the deployment using environment variables:

- `PORT`: Internal port (default: 8050)
- `workers`: Number of Gunicorn workers (default: 2, modify in Dockerfile CMD)
- `threads`: Threads per worker (default: 4, modify in Dockerfile CMD)

## Production Notes
- The Docker image uses **Gunicorn** as a production-grade WSGI server.
- The base image is `python:3.11-slim-bookworm` for a small footprint.
