# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A monorepo of two Python MCP servers and one shared Next.js frontend. The
governing idea: write analysis/build logic **once in a pandas/AST engine** and
expose it across four surfaces — Web UI, in-app Gemini chat agent, MCP server
(tools + prompts), and HTTP API.

- **`backend/`** — *Quick Data*: arbitrary JSON/CSV analysis. Package `quickdata`.
- **`smart-dev/`** — *Smart Dev*: a senior-dev pair-programmer for code analysis
  (complexity, tests, deps, docs, deploy preview, rollback). Package `smart_dev`.
- **`frontend/`** — Next.js 16 / React 19 UI. Main app (`/`) drives Quick Data;
  the `/dev` route drives Smart Dev.

The root `main.py` / root `pyproject.toml` are a leftover `uv` scaffold and are
**not** part of any product — ignore them.

## Common commands

Each Python project is a separate `uv` package; run commands from its own dir.

**Quick Data backend** (`cd backend`, Python ≥3.11):
```bash
uv venv && uv pip install -e ".[dev]"
uv run quickdata-api          # FastAPI on http://127.0.0.1:8020 (docs at /docs)
uv run quickdata-mcp          # MCP server, stdio transport
uv run pytest                 # all tests
uv run pytest tests/test_engine.py::test_name   # a single test
```

**Smart Dev** (`cd smart-dev`, Python ≥3.10):
```bash
uv venv && uv pip install -e ".[dev]"
uv run smart-dev              # MCP server, stdio transport
uv run smart-dev-api          # FastAPI on http://127.0.0.1:8030
uv run pytest
```

**Frontend** (`cd frontend`, pnpm):
```bash
pnpm install
pnpm dev                      # http://localhost:3000
pnpm build
pnpm lint                     # eslint
```

**Everything at once:** `start_servers.bat` (Windows: backend + frontend) or
`GEMINI_API_KEY=... docker compose up --build` (all three services).

Both MCP servers are registered for Claude Code in `.mcp.json` at the repo root
(absolute Windows paths). After changing MCP tool/prompt signatures, the client
must reconnect to pick them up.

## Architecture

### The shared-engine pattern (both backends follow it)

A backend is structured as a pure core wrapped by thin transports:

- **`engine/`** (Quick Data) / **`tools/`** + **`languages.py`** (Smart Dev) —
  the real logic. **No MCP, HTTP, or LLM imports.** Unit-tested directly.
- **`mcp_server.py`** / **`server_fastmcp.py`** — FastMCP wrapper exposing the
  core as **tools and prompts**. Prompts are treated as the higher-leverage
  primitive: multi-step agentic workflows (e.g. `dataset_first_look`,
  `code_review`) that compose tools and tell the agent what to do next.
- **`api.py`** — FastAPI REST mirror of the tools, for the frontend.
- **`agent/`** — a Gemini analyst that calls the same core via function calling,
  exposed to the frontend over `POST /api/chat`.

When adding a capability, add it to the engine/tools core first, then surface it
through each transport. Don't put logic in `api.py` or `mcp_server.py`.

### Quick Data engine modules (`backend/quickdata/engine/`)

`store.py` (load + schema classification + the process-wide `default_store`),
`analysis.py`, `charts.py`, `query.py` (string-DSL filter/group/aggregate),
`sql.py` (read-only SQL over an **ephemeral** in-memory SQLite built per call —
no persistent mirror; all loaded datasets registered as tables so JOINs work),
`transform.py` (**non-destructive** column/row transforms → new `<name>_transformed`
dataset; `df.eval`/`df.query`, never bare `eval`),
`quality.py` (profile + **non-destructive** clean → new `<name>_clean` dataset),
`playbooks.py`, `report.py`, `pdf.py` (fpdf2, no native deps).

The MCP server and HTTP API **share `default_store`**, so within one process a
dataset loaded via one transport is visible to the other.

### The agent (swap-in point)

`agent/base.py` defines the transport-neutral `AnalysisAgent` Protocol plus
`AgentEvent` (streamed: `session`, `text`, `tool`, `chart`, `done`, `error`).
`gemini_agent.py` is the `google-genai` implementation — a **manual
function-calling loop** that streams SSE. Conversation state is held
**server-side, keyed by `session_id`**; the client sends only the new message.
A second backend (e.g. antigravity-sdk) can be added without touching `api.py`
or the frontend by implementing the Protocol.

Without `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) the agent is disabled: the rest of
the app works and `/api/chat` returns 503.

> **Gemini 3 streaming + manual function calling:** when echoing the model's
> function-call turn back into history, you must preserve the part's
> `thought_signature` or the next request 400s. See the memory note
> `gemini3-thought-signature-streaming`.

### Smart Dev internals (`smart-dev/smart_dev/`)

Smart Dev has no `engine/` dir — its core is `tools/` + `languages.py`:

- **`tools/`** — `analyze_codebase`, `run_tests`, `check_dependencies`,
  `generate_docs`, `deploy_preview`, `rollback_changes`. Each returns a JSON
  string. `analyze_codebase` does **real Python AST** complexity/structure
  analysis and falls back to **pattern-based heuristics** for other languages;
  it reads files concurrently (thread pool) and includes debug-statement and
  **secret scanning**.
- **`languages.py`** — the single source of language knowledge: `EXTENSIONS`
  (ext→language), `SKIP_DIRS` (never-analyzed dirs), `BRANCH_TOKENS` (complexity
  heuristic for non-Python), `FUNCTION_PATTERNS` (doc-gen regexes).
- **`prompts/`** — the six workflow prompts; `list_assets` lives inline in the
  server. Tools return JSON, prompts return guided **Markdown**.
- **`utils/`** — `resolve_dir`/`resolve_file` (+ `PathError`), `FileCache`
  (per-file results cached by mtime), `get_logger`, `run_command`/`which`.
- **`server_fastmcp.py`** — wraps tools/prompts. The `_guard` decorator turns
  `PathError` into a clean `{"error": ...}` JSON message instead of a stack trace.
- **`api.py`** / **`agent/`** — same shape as Quick Data, but the agent streams
  only `session | text | tool | done | error` events (**no `chart`**), and there
  is **no shared in-memory store** — tools are stateless over the path you pass.

**Safety conventions:** `deploy_preview` does no real remote deploy (build-gated
by `run_build`, simulated URL). `rollback_changes` **plans by default** and only
executes (via `git revert`, a new reversible commit) when called with
`confirm=true`. All tools take **absolute** project paths.

## Frontend — read before writing code

`frontend/CLAUDE.md` points to `frontend/AGENTS.md`, which warns: **this is
Next.js 16 + React 19 with breaking changes from older versions.** Consult
`frontend/node_modules/next/dist/docs/` before writing Next.js code rather than
relying on training data, and use `ctx7` for library docs per global rules.

- `app/lib/api.ts` — typed client for the Quick Data backend; base URL from
  `NEXT_PUBLIC_API_BASE` (default `http://127.0.0.1:8020`).
- `app/lib/chat.ts` — SSE stream parser for the chat agent.
- `app/lib/smartdev.ts` — client for the Smart Dev API (`NEXT_PUBLIC_SMARTDEV_API_BASE`,
  default port 8030), used by the `/dev` route.

## Configuration

| Variable | Used by | Purpose |
| --- | --- | --- |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | both backends | Enables the chat agent |
| `QUICKDATA_MODEL` | backend | Override model (default `gemini-3.5-flash`) |
| `QUICKDATA_DATA_DIR` | backend | Bundled sample data location (set in Docker) |
| `SMART_DEV_DEBUG=1` | smart-dev | Log to stderr (else `smart-dev-env.log`) |
| `NEXT_PUBLIC_API_BASE` | frontend (build time) | Quick Data backend URL |
| `NEXT_PUBLIC_SMARTDEV_API_BASE` | frontend (build time) | Smart Dev backend URL |

Frontend `NEXT_PUBLIC_*` vars are **baked at build time** into the JS bundle
(see Docker build args), not read at runtime.
