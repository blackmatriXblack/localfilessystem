"""
fileforge.analytics
===================

Read-only analysis of a directory tree: disk usage, largest files, newest
files, empty items, broken symlinks, extension breakdown and a one-shot
summary report.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from . import utils
from .utils import Entry, PathError, iter_entries, resolve


# --------------------------------------------------------------------------- #
# Disk usage
# --------------------------------------------------------------------------- #

@dataclass
class UsageReport:
    files: int = 0
    dirs: int = 0
    links: int = 0
    total_bytes: int = 0
    by_ext: Dict[str, Tuple[int, int]] = field(default_factory=lambda: defaultdict(lambda: (0, 0)))
    by_dir: Dict[str, int] = field(default_factory=lambda: defaultdict(int))


def disk_usage(root: str, include_hidden: bool = True) -> UsageReport:
    base = resolve(root)
    utils.ensure_exists(base)
    rep = UsageReport()
    for e in iter_entries(base, recursive=True, include_hidden=include_hidden):
        if e.is_link:
            rep.links += 1
        if e.is_dir:
            rep.dirs += 1
            continue
        rep.files += 1
        rep.total_bytes += e.size
        ext = e.ext or "<none>"
        count, size = rep.by_ext.get(ext, (0, 0))
        rep.by_ext[ext] = (count + 1, size + e.size)
        top = e.rel.split("\\")[0].split("/")[0]
        rep.by_dir[top] += e.size
    return rep


# --------------------------------------------------------------------------- #
# Largest / newest
# --------------------------------------------------------------------------- #

def largest_files(root: str, limit: int = 20, include_hidden: bool = False,
                  min_size: int = 0) -> List[Entry]:
    base = resolve(root)
    utils.ensure_exists(base)
    items = [e for e in iter_entries(base, recursive=True, include_hidden=include_hidden)
             if not e.is_dir and e.size >= min_size]
    items.sort(key=lambda e: e.size, reverse=True)
    return items[:limit]


def newest_files(root: str, limit: int = 20, include_hidden: bool = False) -> List[Entry]:
    base = resolve(root)
    utils.ensure_exists(base)
    items = [e for e in iter_entries(base, recursive=True, include_hidden=include_hidden)
             if not e.is_dir]
    items.sort(key=lambda e: e.mtime, reverse=True)
    return items[:limit]


def oldest_files(root: str, limit: int = 20, include_hidden: bool = False) -> List[Entry]:
    base = resolve(root)
    utils.ensure_exists(base)
    items = [e for e in iter_entries(base, recursive=True, include_hidden=include_hidden)
             if not e.is_dir]
    items.sort(key=lambda e: e.mtime)
    return items[:limit]


# --------------------------------------------------------------------------- #
# Empty items
# --------------------------------------------------------------------------- #

@dataclass
class EmptyReport:
    empty_files: List[Path] = field(default_factory=list)
    empty_dirs: List[Path] = field(default_factory=list)


def find_empty(root: str, include_hidden: bool = False) -> EmptyReport:
    base = resolve(root)
    utils.ensure_exists(base)
    rep = EmptyReport()
    for e in iter_entries(base, recursive=True, include_hidden=include_hidden):
        if e.is_link:
            continue
        if e.is_dir:
            try:
                if not any(e.path.iterdir()):
                    rep.empty_dirs.append(e.path)
            except OSError:
                continue
        elif e.size == 0:
            rep.empty_files.append(e.path)
    return rep


# --------------------------------------------------------------------------- #
# Broken symlinks
# --------------------------------------------------------------------------- #

def find_broken_links(root: str) -> List[Path]:
    import os

    base = resolve(root)
    utils.ensure_exists(base)
    broken: List[Path] = []
    for e in iter_entries(base, recursive=True, include_hidden=True, follow_symlinks=False):
        if e.is_link and not e.path.exists():
            broken.append(e.path)
    # is_link comes from lstat; also sweep with os.walk to be safe
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        for name in dirnames + filenames:
            p = Path(dirpath) / name
            if p.is_symlink() and not p.exists():
                if p not in broken:
                    broken.append(p)
    return broken


# --------------------------------------------------------------------------- #
# Extension summary  + full report
# --------------------------------------------------------------------------- #

def extension_summary(root: str, include_hidden: bool = False) -> List[Tuple[str, int, int]]:
    rep = disk_usage(root, include_hidden=include_hidden)
    rows = [(ext, count, size) for ext, (count, size) in rep.by_ext.items()]
    rows.sort(key=lambda r: r[2], reverse=True)
    return rows


@dataclass
class Summary:
    root: Path
    files: int
    dirs: int
    links: int
    total_bytes: int
    empty_files: int
    empty_dirs: int
    broken_links: int
    top_ext: List[Tuple[str, int, int]]
    largest: List[Entry]
    newest: List[Entry]
    oldest: List[Entry]


def summarize(root: str, include_hidden: bool = False, top: int = 5) -> Summary:
    base = resolve(root)
    utils.ensure_exists(base)
    rep = disk_usage(base, include_hidden=include_hidden)
    empty = find_empty(base, include_hidden=include_hidden)
    broken = find_broken_links(base)
    return Summary(
        root=base,
        files=rep.files,
        dirs=rep.dirs,
        links=rep.links,
        total_bytes=rep.total_bytes,
        empty_files=len(empty.empty_files),
        empty_dirs=len(empty.empty_dirs),
        broken_links=len(broken),
        top_ext=extension_summary(base, include_hidden)[:top],
        largest=largest_files(base, limit=top, include_hidden=include_hidden),
        newest=newest_files(base, limit=top, include_hidden=include_hidden),
        oldest=oldest_files(base, limit=top, include_hidden=include_hidden),
    )
