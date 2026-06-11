# Quick Data — backend

Arbitrary JSON/CSV data analysis, exposed two ways from **one shared engine**:

- **MCP server** (`quickdata.mcp_server`) — tools **and** prompts, for MCP clients
  like Claude Code. Prompts are the high-leverage primitive: reusable agentic
  workflows that compose tools and guide the next step.
- **HTTP API** (`quickdata.api`) — FastAPI REST endpoints powering the Next.js
  frontend in `../frontend`.
- **In-app agent** (`quickdata.agent`) — a Gemini-powered analyst that turns
  natural language into analysis via function calling over the same engine.
  Exposed to the frontend through `POST /api/chat`.

```
quickdata/
  engine/          # pandas core — no MCP/HTTP/LLM deps, unit-testable
    store.py       # load JSON/CSV, schema classification, in-memory store
    analysis.py    # breakdown, segment, correlations, suggestions
    charts.py      # chart spec builders (bar/pie/histogram/scatter/line)
    query.py       # flexible filter/group-by/aggregate/top-N (string DSL)
    quality.py     # data-quality profile + non-destructive cleaning ops
    playbooks.py   # reusable recipes (first_look, data_quality_audit, ...)
    report.py      # compile playbooks into a Markdown/HTML report
    pdf.py         # render a report to PDF (fpdf2, no native deps)
  agent/
    base.py        # AnalysisAgent protocol + result types (swap-in point)
    tools.py       # engine ops as LLM function-calling tools
    gemini_agent.py# google-genai impl (gemini-3.5-flash), manual FC loop
  mcp_server.py    # FastMCP: tools + prompts
  api.py           # FastAPI HTTP API (+ /api/chat, /api/agent)
data/              # bundled sample datasets (+ generator)
tests/             # engine tests
```

## Chat agent

`POST /api/chat` runs a Gemini agent that calls the engine tools. It **streams**
results as Server-Sent Events — `session`, `text` (token deltas), `tool`,
`chart`, `done`, `error` — so the UI shows the reply, tool-call trace, and charts
as they happen.

Conversation state is held **server-side**, keyed by `session_id` (returned in
the first `session` event). The client sends only the new `message`; the agent
retains the full prior context — including earlier tool calls and their results —
so follow-ups like "now chart that" work without recomputing. `DELETE
/api/chat/{session_id}` forgets a session (the UI's "New chat" button).

It needs an API key:

```bash
export GEMINI_API_KEY=...   # or GOOGLE_API_KEY
# optional: override the model (default gemini-3-flash-preview)
export QUICKDATA_MODEL=gemini-3.1-pro-preview
```

Without a key the rest of the app works; `/api/chat` returns 503 and the UI
shows the agent as disabled. The agent is hidden behind the `AnalysisAgent`
protocol in `agent/base.py`, so an `antigravity-sdk` backend can be added as a
second implementation without changing the API or frontend.

## Setup

```bash
uv venv
uv pip install -e ".[dev]"
python data/generate_samples.py   # regenerate sample data (optional)
```

## Run the HTTP API (for the frontend)

```bash
uv run quickdata-api          # http://127.0.0.1:8000  (docs at /docs)
```

## Run the MCP server (for Claude Code / Cursor)

```bash
uv run quickdata-mcp          # stdio transport
```

Register it with Claude Code by adding to `.mcp.json` (repo root):

```json
{
  "mcpServers": {
    "quick-data": {
      "command": "uv",
      "args": ["run", "--directory", "backend", "quickdata-mcp"]
    }
  }
}
```

Then in Claude Code: `/quick-data:list_mcp_assets` to prime the agent, or
`/quick-data:find_data_sources .` to discover loadable files.

## Tools

`load_dataset`, `list_datasets`, `dataset_breakdown`, `suggest_analysis`,
`segment_by_column`, `find_correlations`, `create_chart`, `run_query`,
`profile_dataset`, `clean_dataset`, `run_playbook`.

## Prompts (slash commands)

`list_mcp_assets`, `find_data_sources`, `dataset_first_look`,
`correlation_investigation`, `first_look_report`, `data_quality_audit`.

## Workflows

Beyond one-shot tools, the engine exposes higher-level workflows, all reachable
via the in-app agent, the MCP server, and REST:

- **Flexible query** — `POST /api/datasets/{name}/query` with `filters`,
  `group_by`, `metrics` (e.g. `["value:sum","count"]`), `sort_by`, `limit`.
- **Data quality** — `GET .../profile` (issues + fixes), `POST .../clean`
  (writes a new `<name>_clean` dataset; non-destructive).
- **Playbooks** — `GET .../playbook/{first_look|data_quality_audit|correlation_deep_dive}`
  returns report sections + charts.
- **Report** — `GET .../report` returns a Markdown/HTML report with charts;
  `GET .../report.pdf` returns a print-ready PDF (fpdf2: HTML tables + hand-drawn
  charts, no native deps).

## Test

```bash
uv run pytest
```
