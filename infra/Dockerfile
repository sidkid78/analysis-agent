# Infrastructure Automation API — FastAPI + MCP over a simulated fleet.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PORT=8040

# The fleet is an in-memory simulation — no native deps, no external services.
COPY pyproject.toml README.md ./
COPY infra_automation ./infra_automation
RUN uv pip install --system .

EXPOSE 8040

# Bind 0.0.0.0 for external reachability (the console script binds localhost).
CMD ["uvicorn", "infra_automation.api:app", "--host", "0.0.0.0", "--port", "8040"]
