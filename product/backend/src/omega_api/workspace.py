from __future__ import annotations

import difflib


class WorkspaceInputError(ValueError):
    """A workspace path or diff request violates safe bounds."""


def normalize_project_path(value: str) -> str:
    """Validate a POSIX-style logical project path; it is never joined to a host path."""
    if not isinstance(value, str) or not value or len(value) > 512:
        raise WorkspaceInputError('File path must contain 1 to 512 characters.')
    if value.startswith('/') or '\\' in value or '\x00' in value:
        raise WorkspaceInputError('Absolute paths, backslashes, and NUL bytes are not allowed.')
    parts = value.split('/')
    if len(parts) > 12 or any(part in ('', '.', '..') for part in parts):
        raise WorkspaceInputError('File path contains an empty, relative, or excessively deep segment.')
    if any(len(part) > 128 or any(ord(char) < 32 or ord(char) == 127 for char in part) for part in parts):
        raise WorkspaceInputError('File path contains an invalid segment.')
    return '/'.join(parts)


def build_project_diff(previous: dict[str, str], current: dict[str, str]) -> list[dict[str, str]]:
    """Return deterministic unified diffs between a stored checkpoint and current files."""
    result: list[dict[str, str]] = []
    for path in sorted(set(previous) | set(current)):
        old = previous.get(path)
        new = current.get(path)
        if old == new:
            continue
        if old is None:
            change = 'added'
            old = ''
        elif new is None:
            change = 'deleted'
            new = ''
        else:
            change = 'modified'
        lines = difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f'a/{path}' if change != 'added' else '/dev/null',
            tofile=f'b/{path}' if change != 'deleted' else '/dev/null',
            n=3,
        )
        result.append({'path': path, 'change': change, 'diff': ''.join(lines)})
    return result
