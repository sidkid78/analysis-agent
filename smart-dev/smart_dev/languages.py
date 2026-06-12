"""Language detection and per-language analysis hints."""

from __future__ import annotations

EXTENSIONS: dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".go": "Go",
    ".rs": "Rust",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".cc": "C++",
    ".hpp": "C++",
    ".cs": "C#",
    ".php": "PHP",
    ".rb": "Ruby",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".scala": "Scala",
    ".clj": "Clojure",
}

# Directories never worth analyzing.
SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "env",
        "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
        "dist", "build", ".next", "out", "target", "coverage", ".turbo",
        ".idea", ".vscode", ".gradle", "vendor", ".terraform",
    }
)

# Generic branch tokens used to estimate complexity for non-Python languages.
BRANCH_TOKENS = (
    r"\bif\b", r"\belse\s+if\b", r"\belif\b", r"\bfor\b", r"\bwhile\b",
    r"\bcase\b", r"\bcatch\b", r"\bexcept\b", r"\bwhen\b", r"&&", r"\|\|", r"\?",
)

# Best-effort function/definition patterns per language family (for doc gen).
FUNCTION_PATTERNS: dict[str, list[str]] = {
    "JavaScript": [
        r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(",
        r"(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s*)?\(",
        r"(\w+)\s*\([^)]*\)\s*\{",
    ],
    "TypeScript": [
        r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(",
        r"(?:export\s+)?const\s+(\w+)\s*[:=]",
        r"(?:public|private|protected)?\s*(\w+)\s*\([^)]*\)\s*[:{]",
    ],
    "Go": [r"func\s+(?:\([^)]*\)\s*)?(\w+)\s*\("],
    "Rust": [r"(?:pub\s+)?fn\s+(\w+)\s*[(<]"],
    "Java": [r"(?:public|private|protected|static|\s)+[\w<>\[\]]+\s+(\w+)\s*\([^)]*\)\s*\{"],
}

# JavaScript/TS use TypeScript patterns as well.
FUNCTION_PATTERNS["JavaScript"] += FUNCTION_PATTERNS["TypeScript"][:1]


def detect_language(suffix: str) -> str | None:
    return EXTENSIONS.get(suffix.lower())
