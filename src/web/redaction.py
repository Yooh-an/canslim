"""Privacy redaction helpers for dashboard diagnostics."""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def redact_local_paths(value: str, *, project_root: Path | None = None, home_root: Path | None = None) -> str:
    """Replace absolute local paths with stable, non-identifying labels."""
    text = str(value or "")
    roots = [
        (_resolved_path(project_root or PROJECT_ROOT), "."),
        (_resolved_path(home_root or Path.home()), "~"),
    ]
    for root, replacement in sorted(
        ((root, replacement) for root, replacement in roots if root),
        key=lambda item: len(str(item[0])),
        reverse=True,
    ):
        text = text.replace(str(root), replacement)
    return text


def _resolved_path(path: Path | None) -> Path | None:
    if path is None:
        return None
    try:
        return path.resolve()
    except OSError:
        return None
