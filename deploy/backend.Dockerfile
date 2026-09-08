# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:0.12.5 AS uv

FROM python:3.13-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY vendor/contexture_mcp-*.whl /tmp/contexture/
# The dependency remains commit-locked in pyproject.toml/uv.lock. Releases ship
# the wheel built from that exact checkout so Beijing does not need GitHub access.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --no-install-package contexture-mcp \
    && uv pip install --python .venv/bin/python --no-deps /tmp/contexture/contexture_mcp-*.whl
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-package contexture-mcp \
    && rm -rf /tmp/contexture

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
ENTRYPOINT ["cointent"]
