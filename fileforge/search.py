"""
fileforge.search
================

Locate files by name, glob, extension, size, date and content. Also provides
a recursive "grep" implementation that understands glob filters.

All functions return lists of :class:`~fileforge.utils.Entry` (or a grep
match record) so the caller decides how to render them.
"""

from __future__ import annotations

import fnmatch
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from . import utils
from .utils import Entry, PathError, iter_entries, resolve

# --------------------------------------------------------------------------- #
# Size parsing  (10M, 512k, 1G, 100, 1.5mb ...)
# --------------------------------------------------------------------------- #

_SIZE_UNITS = {
    "": 1, "b": 1,
    "k": 1024, "kb": 1024, "kib": 1024,
    "m": 1024 ** 2, "mb": 1024 ** 2, "mib": 1024 ** 2,
    "g": 1024 ** 3, "gb": 1024 ** 3, "gib": 1024 ** 3,
    "t": 1024 ** 4, "tb": 1024 ** 4, "tib": 1024 ** 4,
}

_DURATION_UNITS = {
    "s": 1, "sec": 1, "second": 1, "seconds": 1,
    "m": 60, "min": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hour": 3600, "hours": 3600,
    "d": 86400, "day": 86400, "days": 86400,
    "w": 604800, "week": 604800, "weeks": 604800,
}


def parse_size(text: str) -> int:
    """Parse a human size string such as '10M', '512k', '1.5GB' to bytes."""
    m = re.fullmatch(r"\s*([0-9]*\.?[0-9]+)\s*([a-zA-Z]*)\s*", text)
    if not m:
        raise PathError(f"Invalid size value: {text!r}")
    value, unit = float(m.group(1)), m.group(2).lower()
    if unit not in _SIZE_UNITS:
        raise PathError(f"Unknown size unit {unit!r} in {text!r}")
    return int(value * _SIZE_UNITS[unit])


def parse_duration(text: str) -> float:
    """Parse '7d', '24h', '30m', '45s' (optionally '3d12h') to seconds."""
    if not text:
        raise PathError("Empty duration")
    total = 0.0
    for value, unit in re.findall(r"([0-9]*\.?[0-9]+)\s*([a-zA-Z]+)", text):
        key = unit.lower()
        if key not in _DURATION_UNITS:
            raise PathError(f"Unknown duration unit {unit!r}")
        total += float(value) * _DURATION_UNITS[key]
    if total == 0.0:
        raise PathError(f"Invalid duration: {text!r}")
    return total


# --------------------------------------------------------------------------- #
# Find
# --------------------------------------------------------------------------- #

@dataclass
class FindCriteria:
    root: str = "."
    name: Sequence[str] = field(default_factory=list)      # glob patterns
    regex: Optional[str] = None
    extensions: Sequence[str] = field(default_factory=list)  # e.g. [".py", "txt"]
    min_size: Optional[int] = None
    max_size: Optional[int] = None
    newer_than: Optional[float] = None   # seconds ago
    older_than: Optional[float] = None   # seconds ago
    content: Optional[str] = None
    files_only: bool = False
    dirs_only: bool = False
    empty: bool = False
    include_hidden: bool = False
    max_depth: Optional[int] = None
    follow_symlinks: bool = False
    limit: Optional[int] = None


def find(criteria: FindCriteria) -> List[Entry]:
    root = resolve(criteria.root)
    if not root.exists():
        raise PathError(f"Search root does not exist: {root}")

    exts = {e.lower() if e.startswith(".") else "." + e.lower()
            for e in criteria.extensions}
    now = time.time()
    results: List[Entry] = []

    for e in iter_entries(
        root,
        recursive=criteria.max_depth is None or criteria.max_depth > 0,
        include_hidden=criteria.include_hidden,
        follow_symlinks=criteria.follow_symlinks,
        max_depth=criteria.max_depth,
    ):
        if criteria.files_only and e.is_dir:
            continue
        if criteria.dirs_only and not e.is_dir:
            continue
        if criteria.name and not utils.glob_match(e.path.name, criteria.name):
            continue
        if criteria.regex and not utils.regex_search(
                criteria.regex, e.path.name, ignore_case=True):
            continue
        if exts and (e.is_dir or e.ext not in exts):
            continue
        if criteria.min_size is not None and (e.is_dir or e.size < criteria.min_size):
            continue
        if criteria.max_size is not None and (e.is_dir or e.size > criteria.max_size):
            continue
        if criteria.newer_than is not None and (now - e.mtime) > criteria.newer_than:
            continue
        if criteria.older_than is not None and (now - e.mtime) < criteria.older_than:
            continue
        if criteria.empty and not e.is_dir and e.size != 0:
            continue
        if criteria.empty and e.is_dir:
            try:
                if any(e.path.iterdir()):
                    continue
            except OSError:
                continue
        if criteria.content and not e.is_dir:
            if not _file_contains(e.path, criteria.content):
                continue

        results.append(e)
        if criteria.limit and len(results) >= criteria.limit:
            break

    results.sort(key=lambda x: (not x.is_dir, x.rel.lower()))
    return results


def _file_contains(path: Path, needle: str, max_bytes: int = 20 << 20) -> bool:
    try:
        if utils.is_binary(path):
            return False
        with path.open("r", encoding="utf-8", errors="ignore") as fh:
            read = 0
            while True:
                chunk = fh.read(1 << 16)
                if not chunk:
                    return False
                read += len(chunk)
                if needle in chunk:
                    return True
                if read > max_bytes:
                    return False
    except OSError:
        return False


# --------------------------------------------------------------------------- #
# Grep
# --------------------------------------------------------------------------- #

@dataclass
class GrepMatch:
    path: Path
    line_no: int
    line: str


def grep(pattern: str, paths: Sequence[str] = (".",), regex: bool = False,
         ignore_case: bool = True, include: Sequence[str] = (),
         exclude: Sequence[str] = (), recursive: bool = True,
         max_matches: int = 0, context: int = 0,
         binary_skip: bool = True) -> List[GrepMatch]:
    """
    Search text files for `pattern`.

    `include`/`exclude` are glob patterns applied to the file name.
    `max_matches` = 0 means unlimited.
    """
    flags = re.IGNORECASE if ignore_case else 0
    if regex:
        try:
            compiled = re.compile(pattern, flags)
        except re.error as exc:
            raise PathError(f"Invalid regex: {exc}") from exc

        def matcher(line: str) -> bool:
            return compiled.search(line) is not None
    else:
        needle = pattern.lower() if ignore_case else pattern

        def matcher(line: str) -> bool:
            return (needle in line.lower()) if ignore_case else (needle in line)

    files: List[Path] = []
    for raw in paths:
        p = resolve(raw)
        if not p.exists():
            raise PathError(f"Path does not exist: {p}")
        if p.is_file():
            files.append(p)
        elif recursive:
            for e in iter_entries(p, recursive=True, include_hidden=False):
                if not e.is_dir:
                    files.append(e.path)
        else:
            for c in sorted(p.iterdir()):
                if c.is_file():
                    files.append(c)

    matches: List[GrepMatch] = []
    for f in files:
        if include and not utils.glob_match(f.name, include):
            continue
        if exclude and utils.glob_match(f.name, exclude):
            continue
        if binary_skip and utils.is_binary(f):
            continue
        try:
            with f.open("r", encoding="utf-8", errors="ignore") as fh:
                lines = fh.readlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            if matcher(line):
                matches.append(GrepMatch(f, i, line.rstrip("\n")))
                if max_matches and len(matches) >= max_matches:
                    return matches
    return matches
