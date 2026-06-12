# Smart Dev API — FastAPI + MCP code-analysis tools.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PORT=8030 \
    SMART_DEV_LOG=/tmp/smart-dev-env.log

# git enables the rollback_changes tool; the rest of the tools are stdlib-only.
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY smart_dev ./smart_dev
RUN uv pip install --system .

COPY test-data ./test-data

EXPOSE 8030

# Bind 0.0.0.0 for external reachability (the console script binds localhost).
CMD ["uvicorn", "smart_dev.api:app", "--host", "0.0.0.0", "--port", "8030"]
