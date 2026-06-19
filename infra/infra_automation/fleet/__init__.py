"""The pure, stateful fleet core.

``model.py`` holds the process-wide ``default_fleet`` — a deterministic in-memory
model of services, resources, secrets, and backups. The tool modules
(monitoring, deployment, scaling, backup, secrets, logs) read and mutate it and
return plain JSON-serializable dicts, with **no MCP / HTTP / LLM imports**.
"""
