# syntax=docker/dockerfile:1.7

# Builder stage: use uv image to resolve and install dependencies + project
FROM ghcr.io/astral-sh/uv:python3.11-bookworm AS builder

WORKDIR /app

# Copy project metadata and lock first to maximize cache
COPY pyproject.toml uv.lock ./

# Copy sources
COPY src ./src
COPY README.md ./

# Install into a local virtualenv in /app/.venv (default for uv sync)
# --frozen ensures we respect the pinned versions in uv.lock
RUN uv sync --frozen --no-dev

# Runtime stage: slim base with only the venv and sources
FROM debian:bookworm-slim AS runtime

ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only what is needed to run
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/README.md /app/README.md
COPY pyproject.toml ./pyproject.toml

# The MCP server communicates over stdio; no port exposure needed

# Required at runtime:
# - FRESHRELEASE_API_KEY
# - FRESHRELEASE_DOMAIN

ENTRYPOINT ["freshrelease-mcp"]
