# Quick Data backend — FastAPI + MCP analysis engine.
# Uses the official uv image (Python 3.13). No native deps required.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    QUICKDATA_DATA_DIR=/app/data \
    PORT=8020

# Install the package (and its dependencies) into the system environment.
COPY pyproject.toml README.md ./
COPY quickdata ./quickdata
RUN uv pip install --system .

# Bundled sample datasets (path pinned via QUICKDATA_DATA_DIR above).
COPY data ./data

EXPOSE 8020

# Bind 0.0.0.0 so the API is reachable outside the container (the console
# script binds localhost + reload, which is for local dev only).
CMD ["uvicorn", "quickdata.api:app", "--host", "0.0.0.0", "--port", "8020"]
