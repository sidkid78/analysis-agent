# Infrastructure Automation

A senior-SRE pair-programmer MCP server over a **deterministic simulated fleet**:
monitoring, deployment, scaling, backup, secret rotation, and log analysis,
exposed across an MCP server (tools + prompts), an HTTP API, and a chat agent.

Built to the same shared-core pattern as the rest of this repo: a pure stateful
core in `infra_automation/fleet/` (no MCP / HTTP / LLM imports) wrapped by thin
transports. The fleet is an honest simulation — **deterministic and stateful**,
not random — so the same state always yields the same readings, and mutating
tools (deploy, scale, backup, rotate) change inspectable state.

## Commands

```bash
cd infra
uv venv && uv pip install -e ".[dev]"
uv run infra-mcp        # MCP server, stdio transport
uv run infra-api        # FastAPI on http://127.0.0.1:8040
uv run pytest
```

## Safety

Mutating operations (`deploy_application`, `scale_resources`, `backup_data`,
`rotate_secrets`) **plan by default** and only apply when called with
`confirm=true`, mirroring Smart Dev's `rollback_changes`.
