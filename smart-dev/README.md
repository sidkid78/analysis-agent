# Smart Development Environment (MCP)

A senior-dev **pair-programmer** exposed over MCP. Like the Quick Data server, it
follows the principle that **prompts are higher leverage than tools**: guided,
multi-step workflows that orchestrate individual analysis and build tools.

## Workflows (prompts)

| Prompt | What it does |
| --- | --- |
| `dev_setup` | Discover stack, surface top issues, recommend next steps (runs analysis) |
| `code_review` | Quality-gated review with security findings and a checklist |
| `architecture_analysis` | Structure, coupling, maintainability assessment |
| `debug_investigation` | Hypothesis-driven root-cause methodology |
| `refactor_planning` | Safe, reversible refactor plan with tests + rollback |
| `performance_audit` | Profiling-led optimization pipeline, grounded in hotspots |

## Tools

| Tool | What it does |
| --- | --- |
| `analyze_codebase` | Complexity (Python AST + pattern-based), quality score, issues, **secret scanning** |
| `run_tests` | Detects and runs pytest / `npm`/`pnpm test`, parses the summary |
| `check_dependencies` | Inventories manifests; optional `pip-audit` / `npm audit` |
| `generate_docs` | Markdown API docs from source (AST docstrings + signatures) |
| `deploy_preview` | Local build/health check + simulated preview URL (build gated by `run_build`) |
| `rollback_changes` | Git-based revert — **plans by default**, executes only with `confirm=true` |

`deploy_preview` and `rollback_changes` are deliberately safe: no remote deploys,
and rollback uses `git revert` (a new commit, reversible) only after confirmation.

## Setup

```bash
uv venv && uv pip install -e ".[dev]"
# or, per the classic flow:  pip install -r requirements.txt
```

## Run

```bash
uv run smart-dev          # MCP server (stdio transport)
uv run smart-dev-api      # HTTP API for the web UI (http://127.0.0.1:8030)
```

The same tools/workflows are also exposed over HTTP (FastAPI + a streaming Gemini
agent) for the **"Smart Dev"** section of the frontend (`/dev` route). Set
`GEMINI_API_KEY` to enable the agent.

Register with an MCP client (e.g. Claude Code) via `.mcp.json`:

```json
{
  "mcpServers": {
    "smart-dev": {
      "command": "uv",
      "args": ["run", "--directory", "smart-dev", "smart-dev"]
    }
  }
}
```

Then: `/smart-dev:list_assets` to prime the agent, or
`/smart-dev:dev_setup <project-path>` to start.

## Layout

```
smart_dev/
  server_fastmcp.py    # FastMCP server: tools + prompts
  languages.py         # extension -> language, complexity/doc patterns
  tools/               # analyze_codebase, run_tests, check_dependencies,
                       # generate_docs, deploy_preview, rollback_changes
  prompts/             # the six workflow prompts (+ list_assets in the server)
  utils/               # path resolution, caching, logging, subprocess
test-data/sample_app/  # sample project with intentional issues
tests/
```

## Notes

- **Language support:** Python (full AST), JavaScript/TypeScript, Java, Go, Rust,
  C/C++, C#, and more (pattern-based).
- **Caching:** per-file results are cached by modification time.
- **Logging:** operations log to `smart-dev-env.log` (set `SMART_DEV_DEBUG=1` for stderr).
- **Paths:** pass absolute project paths.

## Test

```bash
uv run pytest
```
