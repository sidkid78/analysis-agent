"""performance-audit: end-to-end performance analysis pipeline."""

from __future__ import annotations

from pathlib import Path

from ..tools import analyze_codebase
from ..utils import PathError, resolve_dir


def performance_audit(project_path: str) -> str:
    """Guide a performance audit, grounded in complexity hotspots."""
    try:
        root = resolve_dir(project_path)
    except PathError as exc:
        return f"Cannot audit: {exc}"

    a = analyze_codebase(str(root))
    hot = a["metrics"]["complexity_hotspots"]

    return f"""# Performance audit — `{root.name}`

**Avg function complexity:** {a['metrics']['avg_function_complexity']} ·
**Files:** {a['files_analyzed']}

## Static hotspots (start here)
{chr(10).join(f'- `{_rel(h["path"], root)}` — max complexity {h["max_complexity"]}' for h in hot) or '- none flagged'}

High complexity ≠ slow, but branchy/looping code is where to look first.

## Audit pipeline
1. **Measure before optimizing.** Pick representative workloads and capture a
   baseline (wall-clock, CPU, memory). Never optimize on a hunch.
2. **Profile** to find the real hot path:
   - Python: `cProfile` / `py-spy`. JS: Chrome DevTools / `node --prof`.
3. **Classify the bottleneck:** CPU-bound, IO/network-bound, memory/GC, or
   algorithmic (wrong complexity class)?
4. **Fix the dominant cost first** (Amdahl): better algorithm/data structure,
   caching, batching, removing N+1 queries, reducing allocations.
5. **Re-measure** against the baseline; keep changes that move the metric.
6. **Guard** against regressions with a benchmark or perf test.

## Common wins
- N+1 queries → batch/join. Repeated work → memoize.
- Unbounded loops over large data → stream/paginate.
- Sync IO on hot paths → async/concurrent.

## Next steps
- `run_tests` to confirm optimizations preserve behavior.
- `deploy_preview` to validate the build before/after.
"""


def _rel(path: str, root: Path) -> str:
    try:
        return Path(path).relative_to(root).as_posix()
    except ValueError:
        return path
