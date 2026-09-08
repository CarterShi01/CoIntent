# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:0.12.5 AS uv

FROM python:3.13-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
ENTRYPOINT ["cointent"]
