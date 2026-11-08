"""Chooses which HTML file in a directory to display."""

from __future__ import annotations

from pathlib import Path

HTML_SUFFIXES = (".html", ".htm")
INDEX_NAME = "index.html"


def select_html(directory: Path) -> Path | None:
    """Return index.html if present, else the alphabetically first HTML file.

    Only the given directory is inspected (no recursion). Hidden files and
    macOS resource forks (``._*``) are ignored. Returns None when nothing fits.
    """
    candidates = _list_html_files(directory)
    if not candidates:
        return None
    for candidate in candidates:
        if candidate.name.lower() == INDEX_NAME:
            return candidate
    return min(candidates, key=lambda path: (path.name.lower(), path.name))


def _list_html_files(directory: Path) -> tuple[Path, ...]:
    try:
        entries = tuple(directory.iterdir())
    except OSError:
        return ()
    return tuple(entry for entry in entries if _is_visible_html_file(entry))


def _is_visible_html_file(path: Path) -> bool:
    if path.name.startswith("."):
        return False
    if path.suffix.lower() not in HTML_SUFFIXES:
        return False
    try:
        return path.is_file()
    except OSError:
        return False
