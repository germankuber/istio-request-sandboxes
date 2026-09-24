FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

COPY pyproject.toml .
RUN uv sync --no-dev

COPY main.py ./
COPY domain ./domain
COPY application ./application
COPY infrastructure ./infrastructure

CMD ["uv", "run", "kopf", "run", "main.py", "--standalone", "-n", "default", "--liveness=http://0.0.0.0:8080/healthz"]
