"""architecture-analysis: guided assessment with maintainability focus."""

from __future__ import annotations

from pathlib import Path

from ..tools import analyze_codebase
from ..utils import PathError, resolve_dir


def architecture_analysis(project_path: str) -> str:
    """Assess structure, modularity, and maintainability of a codebase."""
    try:
        root = resolve_dir(project_path)
    except PathError as exc:
        return f"Cannot analyze: {exc}"

    a = analyze_codebase(str(root))
    top_dirs = _top_level(root)
    hot = a["metrics"]["complexity_hotspots"]
    langs = ", ".join(a["languages"]) or "none"

    return f"""# Architecture analysis — `{root.name}`

**Languages:** {langs} · **Files:** {a['files_analyzed']} · **Avg complexity:** {a['metrics']['avg_function_complexity']}

## Module map (top level)
{chr(10).join(f'- `{d}`' for d in top_dirs) or '_flat layout_'}

## Maintainability signals
- **Complexity hotspots** (candidates for decomposition):
{chr(10).join(f'  - `{_rel(h["path"], root)}` (max {h["max_complexity"]})' for h in hot) or '  - none'}
- **Quality score:** {a['metrics']['quality_score']}/100

## Assessment guide
Walk these dimensions and note findings for each:
1. **Separation of concerns** — are layers (UI / logic / data / IO) distinct?
2. **Coupling** — do modules depend on internals of others, or on interfaces?
3. **Cohesion** — does each module do one thing?
4. **Testability** — can core logic be tested without IO/network?
5. **Consistency** — naming, structure, and patterns uniform across the tree?

## Next steps
- Decompose the hotspots above (`refactor-planning`).
- Confirm behavior is covered before changes (`run_tests`).
- Generate an API surface to review boundaries (`generate_docs`).
"""


def _top_level(root: Path) -> list[str]:
    out = []
    for p in sorted(root.iterdir()):
        if p.is_dir() and not p.name.startswith(".") and p.name not in {"node_modules", "__pycache__"}:
            out.append(p.name + "/")
    return out[:20]


def _rel(path: str, root: Path) -> str:
    try:
        return Path(path).relative_to(root).as_posix()
    except ValueError:
        return path
