#!/usr/bin/env python3
"""
fileforge.computerkit
=====================

Extra **"This PC" / whole-computer** commands.

``fileforge.computer`` prints the machine as a tree and
``fileforge.computerui`` opens the Tkinter "This PC" window.  This module
adds the *analysis* side of the same idea: every command below scans all
drives / mount points live (no cache, no index, no background service) and
answers one question about the whole machine.

Commands
--------
    computerinfo      machine + volume overview (capacity, used, free)
    computerdrives    every drive / mount point with a usage bar
    computerscan      one full scan: counts, bytes, per-volume table
    computertree      the whole machine as a text tree
    computerdirs      biggest directories anywhere on the machine
    computerlarge     biggest files anywhere on the machine
    computernew       most recently modified files
    computerold       least recently modified files
    computerempty     empty files and empty directories
    computerext       size / count grouped by file extension
    computerstats     one-shot statistical report (buckets, ages, top)
    computermap       terminal block map of every volume
    computerfind      find files by name / glob across every drive
    computergrep      search file *contents* across every drive
    computerdupes     duplicate files across every drive
    computertemp      temporary / cache / junk files
    computerexport    export the whole machine to JSON / CSV / TXT
    computersnapshot  save a snapshot (path + size + mtime)
    computerdiff      diff two snapshots (added / removed / changed)
    computerwatch     live watch: created / deleted / modified
    computeraudit     permission audit (world-writable, setuid, setgid)

Every command also has a short alias (``pcinfo``, ``pcscan``, ...).

Library use
-----------
    from fileforge.computerkit import scan_stats, top_files

    stats = scan_stats(max_items=50000)
    print(stats["files"], stats["bytes"])

Command line
------------
    fileforge pcscan --max-items 20000
    fileforge pclarge -n 30 --root C:\\
    fileforge pcgrep "TODO" --ext .py -n 50
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Optional, Sequence, Tuple

try:  # package import
    from .treeview import (Node, Options, human_size, human_time, parse_duration,
                           parse_size, system_roots, _list_dir)
    from .computer import (iter_all_files, iter_computer_tree, describe_volumes,
                           volumes)
    from .utils import free_space, hash_file, is_binary, platform_name
    from .treemap import BLOCK, PALETTE, render_blocks, render_bars
except ImportError:  # pragma: no cover - direct script execution fallback
    from treeview import (Node, Options, human_size, human_time, parse_duration,  # type: ignore
                          parse_size, system_roots, _list_dir)  # type: ignore
    from computer import (iter_all_files, iter_computer_tree, describe_volumes,  # type: ignore
                          volumes)  # type: ignore
    from utils import free_space, hash_file, is_binary, platform_name  # type: ignore
    from treemap import BLOCK, PALETTE, render_blocks, render_bars  # type: ignore

APP = "fileforge"

#: Scans walk this many levels below each volume by default.
DEFAULT_DEPTH = 32

#: Hard ceiling so a typo cannot turn into a 6-hour scan.
DEFAULT_MAX_ITEMS = 200000

#: Names / globs treated as temporary or junk by ``computertemp``.
TEMP_PATTERNS = (
    "*.tmp", "*.temp", "*.temp.*", "*.bak", "*.old", "*.orig", "*.swp",
    "*.swo", "*~", "*.part", "*.crdownload", "*.partial", "*.download",
    "*.log", "*.dmp", "*.stackdump", "*.pyc", "*.pyo", "*.class",
    "thumbs.db", ".ds_store", "desktop.ini", "*.lock", "*.pid",
)

#: Directory names considered caches by ``computertemp``.
TEMP_DIR_NAMES = {
    "__pycache__", "node_modules", ".cache", "cache", "tmp", "temp",
    ".tmp", "logs", "crash-reports", ".gradle", ".m2", ".npm",
}

SIZE_BUCKETS: Tuple[Tuple[str, int, Optional[int]], ...] = (
    ("< 1 KB", 0, 1024),
    ("1 KB - 1 MB", 1024, 1024 ** 2),
    ("1 - 10 MB", 1024 ** 2, 10 * 1024 ** 2),
    ("10 - 100 MB", 10 * 1024 ** 2, 100 * 1024 ** 2),
    ("100 MB - 1 GB", 100 * 1024 ** 2, 1024 ** 3),
    ("1 - 10 GB", 1024 ** 3, 10 * 1024 ** 3),
    (">= 10 GB", 10 * 1024 ** 3, None),
)


# --------------------------------------------------------------------------- #
# Command specification: (group, name, one-line help)
# --------------------------------------------------------------------------- #
SPEC: List[Tuple[str, str, str]] = [
    ("This PC - open", [
        ("computerui",   "Open the This PC window (all drives, live)"),
        ("treeui",       "Tk tree explorer - This PC when no path is given"),
        ("computer",     "Print the whole machine as one tree"),
        ("computertree", "Whole-machine tree with extra filters"),
    ]),
    ("This PC - inventory", [
        ("computerinfo",   "Machine + volume overview (capacity, used, free)"),
        ("computerdrives", "Every drive / mount point with a usage bar"),
        ("computerscan",   "One full scan: counts, bytes, per-volume table"),
        ("computerexport", "Export the whole machine to JSON / CSV / TXT"),
    ]),
    ("This PC - what is big", [
        ("computerdirs",  "Biggest directories anywhere on the machine"),
        ("computerlarge", "Biggest files anywhere on the machine"),
        ("computermap",   "Terminal block map of every volume"),
        ("computerext",   "Size / count grouped by file extension"),
    ]),
    ("This PC - by age", [
        ("computernew",   "Most recently modified files"),
        ("computerold",   "Least recently modified files"),
        ("computerempty", "Empty files and empty directories"),
        ("computerstats", "One-shot statistical report (buckets, ages, top)"),
    ]),
    ("This PC - search & integrity", [
        ("computerfind",  "Find files by name / glob across every drive"),
        ("computergrep",  "Search file contents across every drive"),
        ("computerdupes", "Duplicate files across every drive"),
        ("computertemp",  "Temporary / cache / junk files"),
    ]),
    ("This PC - track changes", [
        ("computersnapshot", "Save a snapshot (path + size + mtime)"),
        ("computerdiff",     "Diff two snapshots (added / removed / changed)"),
        ("computerwatch",    "Live watch: created / deleted / modified"),
    ]),
    ("This PC - safety", [
        ("computeraudit", "Permission audit (world-writable, setuid, setgid)"),
    ]),
]

#: Short alias -> canonical command name.
ALIASES: Dict[str, str] = {
    "pcui": "computerui",
    "pcgui": "computerui",
    "thispcui": "computerui",
    "pc": "computer",
    "thispc": "computer",
    "pctree": "computertree",
    "pcexplorer": "treeui",
    "pcinfo": "computerinfo",
    "pcsysinfo": "computerinfo",
    "pcdrives": "computerdrives",
    "pcvolumes": "computerdrives",
    "pcscan": "computerscan",
    "pcexport": "computerexport",
    "pcdirs": "computerdirs",
    "pcbigdirs": "computerdirs",
    "pclarge": "computerlarge",
    "pcbig": "computerlarge",
    "pcmap": "computermap",
    "pcext": "computerext",
    "pcnew": "computernew",
    "pcrecent": "computernew",
    "pcold": "computerold",
    "pcempty": "computerempty",
    "pcstats": "computerstats",
    "pcfind": "computerfind",
    "pcgrep": "computergrep",
    "pcdupes": "computerdupes",
    "pcduplicates": "computerdupes",
    "pctemp": "computertemp",
    "pcjunk": "computertemp",
    "pcsnapshot": "computersnapshot",
    "pcdiff": "computerdiff",
    "pcwatch": "computerwatch",
    "pcaudit": "computeraudit",
}


def command_names() -> List[str]:
    """Canonical command names implemented here, in catalogue order."""
    return [name for _group, entries in SPEC for name, _help in entries]


# --------------------------------------------------------------------------- #
# Shared argument plumbing
# --------------------------------------------------------------------------- #
def _add_common(p: argparse.ArgumentParser, *, depth: int = DEFAULT_DEPTH,
                limit: Optional[int] = None, out: bool = True) -> None:
    p.add_argument("-r", "--root", action="append", default=[], metavar="DIR",
                   help="limit the scan to this volume/dir (repeatable; "
                        "default: every drive on this machine)")
    p.add_argument("-L", "--max-depth", type=int, default=depth,
                   help=f"levels below each volume (default: {depth})")
    p.add_argument("-a", "--all", action="store_true",
                   help="include hidden entries")
    p.add_argument("--ext", action="append", default=[], metavar="EXT",
                   help="keep only this extension (repeatable)")
    p.add_argument("--include", action="append", default=[], metavar="GLOB",
                   help="keep names matching this glob (repeatable)")
    p.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                   help="drop names matching this glob (repeatable)")
    p.add_argument("--min-size", metavar="SIZE", help="minimum size, e.g. 10M")
    p.add_argument("--max-size", metavar="SIZE", help="maximum size, e.g. 1G")
    p.add_argument("--newer", metavar="AGE",
                   help="only files modified within e.g. 7d")
    p.add_argument("--older", metavar="AGE",
                   help="only files NOT modified within e.g. 30d")
    p.add_argument("--follow-links", action="store_true",
                   help="follow symlinks / junctions (may hang on shares)")
    p.add_argument("--max-children", type=int, default=0, metavar="N",
                   help="cap entries read per directory (0 = unlimited)")
    p.add_argument("--max-items", type=int, default=DEFAULT_MAX_ITEMS,
                   metavar="N", help=f"stop scanning after N files "
                                     f"(default: {DEFAULT_MAX_ITEMS})")
    p.add_argument("--no-color", action="store_true", help="disable ANSI colors")
    p.add_argument("-q", "--quiet", action="store_true",
                   help="no progress output on stderr")
    p.add_argument("--json", action="store_true",
                   help="emit JSON on stdout instead of a report")
    if out:
        p.add_argument("--out", metavar="FILE",
                       help="write the report / JSON to this file")
    if limit is not None:
        p.add_argument("-n", "--limit", type=int, default=limit,
                       help=f"how many rows to print (default: {limit})")


def _opts(args: argparse.Namespace, **overrides) -> Options:
    now = time.time()
    base = dict(
        max_depth=max(1, int(args.max_depth)),
        include_hidden=bool(args.all),
        follow_links=bool(getattr(args, "follow_links", False)),
        extensions=tuple(args.ext or ()),
        include=tuple(args.include or ()),
        exclude=tuple(args.exclude or ()),
        min_size=parse_size(args.min_size) if args.min_size else None,
        max_size=parse_size(args.max_size) if args.max_size else None,
        newer_than=(now - parse_duration(args.newer)) if args.newer else None,
        older_than=(now - parse_duration(args.older)) if args.older else None,
        sort_by="name",
        max_children=(args.max_children or None),
    )
    base.update(overrides)
    return Options(**base)


def _roots(args: argparse.Namespace) -> List[str]:
    roots = [str(Path(r).expanduser()) for r in (args.root or [])]
    return roots or system_roots()


def _tick(count: int, started: float, args: argparse.Namespace) -> None:
    if args.quiet or count % 2000:
        return
    sys.stderr.write(f"\r  scanning {count:,} entries "
                     f"({time.time() - started:.1f}s)...   ")
    sys.stderr.flush()


def _tick_end(args: argparse.Namespace) -> None:
    if not args.quiet:
        sys.stderr.write("\r" + " " * 60 + "\r")
        sys.stderr.flush()


def _write(text: str, args: argparse.Namespace) -> None:
    if getattr(args, "out", None):
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"written: {args.out}")
    else:
        print(text)


def _dump(obj, args: argparse.Namespace) -> int:
    """Honour ``--json`` / ``--out`` for structured results."""
    text = json.dumps(obj, indent=2, ensure_ascii=False, default=str)
    if getattr(args, "json", False) or getattr(args, "out", None):
        _write(text, args)
        return 0
    return 1  # caller should print the human report instead


def _files(args: argparse.Namespace, opts: Options) -> Iterator[Node]:
    return iter_all_files(opts, roots=_roots(args),
                          max_items=args.max_items or None,
                          max_depth=max(1, int(args.max_depth)))


def _walk(roots: Sequence[str], opts: Options, max_items: Optional[int],
          depth_cap: int) -> Iterator[Node]:
    """Yield **both** directories and files (used when dirs matter)."""
    produced = 0
    for root in roots:
        stack: List[Tuple[Path, int]] = [(Path(root), 0)]
        while stack:
            path, depth = stack.pop()
            if depth >= depth_cap:
                continue
            items, _err, _hidden = _list_dir(path, opts, depth + 1)
            for node in items:
                if node.is_dir:
                    stack.append((node.path, depth + 1))
            for node in items:
                produced += 1
                yield node
                if max_items and produced >= max_items:
                    return


# --------------------------------------------------------------------------- #
# 1. computerinfo - machine + volume overview
# --------------------------------------------------------------------------- #
def _parser_info() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge computerinfo",
                                description="Machine and volume overview.")
    p.add_argument("--json", action="store_true", help="emit JSON")
    p.add_argument("--out", metavar="FILE", help="write JSON here")
    p.add_argument("--no-color", action="store_true")
    return p


def cmd_info(args: argparse.Namespace) -> int:
    import platform

    rows = volumes()
    payload = {
        "platform": platform_name(),
        "platform_detail": platform.platform(),
        "python": platform.python_version(),
        "hostname": platform.node(),
        "volumes": [
            {"root": root,
             "total": total,
             "free": free,
             "used": (total - free) if total else 0,
             "percent_used": round((total - free) * 100.0 / total, 1) if total else None}
            for root, total, free in rows
        ],
        "total_capacity": sum(t for _r, t, _f in rows),
        "total_free": sum(f for _r, _t, f in rows),
    }
    if _dump(payload, args) == 0:
        return 0

    print(f"This PC - {payload['platform']} ({payload['platform_detail']})")
    print(f"host {payload['hostname']}    python {payload['python']}")
    print(f"capacity {human_size(payload['total_capacity'])}    "
          f"free {human_size(payload['total_free'])}\n")
    width = max((len(r) for r, _t, _f in rows), default=8)
    for row in payload["volumes"]:
        total = row["total"]
        if not total:
            print(f"  {row['root']:<{width}}  unavailable")
            continue
        used_pct = row["percent_used"]
        filled = int(round(used_pct / 100.0 * 30))
        bar = "#" * filled + "." * (30 - filled)
        print(f"  {row['root']:<{width}}  [{bar}] {used_pct:5.1f}% used   "
              f"{human_size(row['free']):>10} free of "
              f"{human_size(total):>10}")
    return 0


# --------------------------------------------------------------------------- #
# 2. computerdrives - every mount point with a bar
# --------------------------------------------------------------------------- #
def _parser_drives() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge computerdrives",
                                description="List every drive / mount point.")
    p.add_argument("--json", action="store_true")
    p.add_argument("--out", metavar="FILE")
    p.add_argument("--no-color", action="store_true")
    return p


def cmd_drives(args: argparse.Namespace) -> int:
    rows = volumes()
    payload = [{"root": r, "total": t, "free": f} for r, t, f in rows]
    if _dump(payload, args) == 0:
        return 0
    print(f"Mount points / drives on this machine ({len(rows)}):")
    for root, total, free in rows:
        if not total:
            print(f"  {root:<24} unavailable")
            continue
        used = total - free
        pct = used * 100.0 / total
        print(f"  {root:<24} {human_size(free):>10} free of "
              f"{human_size(total):>10}   ({pct:5.1f}% used)")
    return 0


# --------------------------------------------------------------------------- #
# 3. computerscan - one full scan
# --------------------------------------------------------------------------- #
def _parser_scan() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge computerscan",
                                description="Scan the whole machine once.")
    _add_common(p)
    p.add_argument("--per-volume", action="store_true",
                   help="print a row per drive as well as the total")
    return p


def scan_stats(opts: Optional[Options] = None, roots: Optional[Sequence[str]] = None,
               max_items: Optional[int] = DEFAULT_MAX_ITEMS,
               per_volume: bool = False) -> Dict[str, object]:
    """Scan the machine and return a statistics dictionary."""
    opts = opts or Options(max_depth=DEFAULT_DEPTH)
    stats = {"files": 0, "dirs": 0, "bytes": 0, "errors": 0, "elapsed": 0.0,
             "volumes": {}}
    started = time.time()
    roots = list(roots) if roots else system_roots()
    per: Dict[str, Dict[str, int]] = {r: {"files": 0, "bytes": 0} for r in roots}

    for root in roots:
        for node in iter_all_files(opts, roots=[root],
                                   max_items=max_items,
                                   max_depth=max(1, opts.max_depth)):
            stats["files"] += 1
            stats["bytes"] += node.size
            per[root]["files"] += 1
            per[root]["bytes"] += node.size

    stats["elapsed"] = round(time.time() - started, 3)
    if per_volume:
        stats["volumes"] = {r: v for r, v in per.items() if v["files"]}
    return stats


def cmd_scan(args: argparse.Namespace) -> int:
    opts = _opts(args)
    roots = _roots(args)
    started = time.time()
    counts: Dict[str, Dict[str, int]] = {r: {"files": 0, "bytes": 0} for r in roots}
    total_files = 0
    total_bytes = 0
    biggest: List[Node] = []

    for root in roots:
        count = 0
        for node in iter_all_files(opts, roots=[root],
                                   max_items=args.max_items or None,
                                   max_depth=max(1, int(args.max_depth))):
            count += 1
            total_files += 1
            total_bytes += node.size
            counts[root]["files"] += 1
            counts[root]["bytes"] += node.size
            if len(biggest) < 10:
                biggest.append(node)
                if len(biggest) == 10:
                    biggest.sort(key=lambda n: n.size, reverse=True)
            elif node.size > biggest[-1].size:
                biggest[-1] = node
                biggest.sort(key=lambda n: n.size, reverse=True)
            if not args.quiet and count % 2000 == 0:
                sys.stderr.write(f"\r  {root}  {count:,} files...")
                sys.stderr.flush()
        _tick_end(args)

    payload = {
        "roots": roots,
        "files": total_files,
        "bytes": total_bytes,
        "elapsed_sec": round(time.time() - started, 3),
        "per_volume": {r: v for r, v in counts.items()},
        "largest": [{"path": str(n.path), "size": n.size} for n in biggest],
    }
    if _dump(payload, args) == 0:
        return 0

    print(f"Scanned {len(roots)} volume(s) in {payload['elapsed_sec']:.2f}s")
    print(f"  files: {total_files:,}    bytes: {human_size(total_bytes)}"
          f" ({total_bytes:,})")
    for root, row in counts.items():
        if row["files"]:
            print(f"  {root:<24} {row['files']:>10,} files  "
                  f"{human_size(row['bytes']):>12}")
    if biggest:
        print("\nlargest files seen:")
        for node in biggest[:10]:
            print(f"  {human_size(node.size):>12}  {node.path}")
    return 0


# --------------------------------------------------------------------------- #
# 4. computertree - whole machine as a tree
# --------------------------------------------------------------------------- #
def _parser_tree() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge computertree",
                                description="Whole machine as a text tree.")
    _add_common(p, depth=2)
    p.add_argument("--ascii", action="store_true", help="ASCII branch characters")
    p.add_argument("--no-size", action="store_true", help="hide sizes")
    p.add_argument("--stats", action="store_true", help="print a summary")
    p.add_argument("--files", action="store_true",
                   help="flat list of files instead of a tree")
    p.add_argument("--full-path", action="store_true",
                   help="with --files, print absolute paths")
    return p


def cmd_tree(args: argparse.Namespace) -> int:
    from .treeview import Stats, format_node  # local: keeps startup cheap

    opts = _opts(args)
    roots = _roots(args)
    if args.files:
        rows = []
        for node in _files(args, opts):
            text = str(node.path) if args.full_path else node.name
            if args.out or args.json:
                rows.append({"path": str(node.path), "size": node.size,
                             "mtime": human_time(node.mtime)})
            else:
                print(f"{human_size(node.size):>10}  {text}")
        if rows:
            _dump(rows, args)
        return 0

    stats = Stats()
    limit = None
    for _prefix, node, stats in iter_computer_tree(opts, roots=roots, limit=limit):
        print(_prefix_str(_prefix, args.ascii)
              + format_node(node, opts, show_size=not args.no_size,
                            color=not args.no_color))
    if args.stats:
        print(f"\n{stats.dirs} director{'y' if stats.dirs == 1 else 'ies'}, "
              f"{stats.files} file(s), {human_size(stats.bytes)} total, "
              f"{stats.errors} unreadable, {stats.elapsed:.2f}s")
    return 0


def _prefix_str(prefix: str, ascii_box: bool) -> str:
    if not ascii_box:
        return prefix
    return (prefix.replace("├── ", "|-- ").replace("└── ", "`-- ")
                  .replace("│   ", "|   "))


# --------------------------------------------------------------------------- #
# 5. computerdirs - biggest directories
# --------------------------------------------------------------------------- #
def _parser_dirs() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge computerdirs",
                                description="Biggest directories on the machine.")
    _add_common(p, limit=20)
    return p


def dir_totals(roots: Sequence[str], opts: Options,
               max_items: Optional[int]) -> Dict[Path, Tuple[int, int]]:
    """Aggregate (bytes, file_count) per directory, including parents."""
    totals: Dict[Path, Tuple[int, int]] = defaultdict(lambda: (0, 0))
    for node in iter_all_files(opts, roots=roots, max_items=max_items,
                               max_depth=max(1, opts.max_depth)):
        parent = node.path.parent
        seen: List[Path] = []
        cursor = parent
        while True:
            size, count = totals[cursor]
            totals[cursor] = (size + node.size, count + 1)
            seen.append(cursor)
            up = cursor.parent
            if up == cursor:
                break
            cursor = up
    return dict(totals)


def cmd_dirs(args: argparse.Namespace) -> int:
    opts = _opts(args)
    started = time.time()
    step = 0
    totals: Dict[Path, Tuple[int, int]] = defaultdict(lambda: (0, 0))
    for node in _files(args, opts):
        step += 1
        _tick(step, started, args)
        cursor = node.path.parent
        while True:
            size, count = totals[cursor]
            totals[cursor] = (size + node.size, count + 1)
            up = cursor.parent
            if up == cursor:
                break
            cursor = up
    _tick_end(args)

    rows = sorted(totals.items(), key=lambda kv: kv[1][0], reverse=True)
    rows = rows[:max(1, int(args.limit))]
    if _dump([{"path": str(p), "size": s, "files": c} for p, (s, c) in rows],
             args) == 0:
        return 0

    print(f"Largest directories on this machine "
          f"({time.time() - started:.2f}s, {len(totals):,} folders seen):")
    for path, (size, count) in rows:
        print(f"{human_size(size):>12}  {count:>9,} f   {path}")
    return 0


# --------------------------------------------------------------------------- #
# 6/7/8. biggest / newest / oldest files
# --------------------------------------------------------------------------- #
def _parser_top(kind: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=f"fileforge computer{kind}",
                                description=f"{kind} files on the machine.")
    _add_common(p, limit=20)
    return p


def top_files(opts: Optional[Options] = None, key: str = "size",
              count: int = 20, roots: Optional[Sequence[str]] = None,
              max_items: Optional[int] = DEFAULT_MAX_ITEMS) -> List[Node]:
    """Return the top ``count`` files by ``key`` (``size`` or ``mtime``)."""
    import heapq

    opts = opts or Options(max_depth=DEFAULT_DEPTH)
    reverse = key == "size"
    heap: List[Tuple[float, int, Node]] = []
    counter = 0
    for node in iter_all_files(opts, roots=roots, max_items=max_items,
                               max_depth=max(1, opts.max_depth)):
        counter += 1
        value = float(node.size if key == "size" else node.mtime)
        item = (value, counter, node)
        if len(heap) < count:
            heapq.heappush(heap, item)
        elif (value > heap[0][0]) == bool(reverse):
            heapq.heapreplace(heap, item)
    ordered = sorted(heap, key=lambda it: it[0], reverse=True)
    return [it[2] for it in ordered]


def _cmd_top(args: argparse.Namespace, key: str, title: str) -> int:
    opts = _opts(args)
    started = time.time()
    nodes = top_files(opts, key=key, count=max(1, int(args.limit)),
                      roots=_roots(args), max_items=args.max_items or None)
    if _dump([{"path": str(n.path), "size": n.size,
               "mtime": human_time(n.mtime)} for n in nodes], args) == 0:
        return 0
    _tick_end(args)
    print(f"{title} ({len(nodes)} shown, {time.time() - started:.2f}s):")
    for node in nodes:
        if key == "size":
            print(f"{human_size(node.size):>12}  {human_time(node.mtime)}  {node.path}")
        else:
            print(f"{human_time(node.mtime)}  {human_size(node.size):>10}  {node.path}")
    return 0


def cmd_large(args: argparse.Namespace) -> int:
    return _cmd_top(args, "size", "Largest files on this machine")


def cmd_new(args: argparse.Namespace) -> int:
    return _cmd_top(args, "mtime", "Most recently modified files")


def _parser_old() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge computerold",
                                description="Least recently modified files.")
    _add_common(p, limit=20)
    return p


def cmd_old(args: argparse.Namespace) -> int:
    import heapq

    opts = _opts(args)
    started = time.time()
    count = max(1, int(args.limit))
    # max-heap on -mtime keeps the *oldest* mtimes
    heap: List[Tuple[float, int, Node]] = []
    seen = 0
    for node in _files(args, opts):
        seen += 1
        _tick(seen, started, args)
        item = (-float(node.mtime), seen, node)
        if len(heap) < count:
            heapq.heappush(heap, item)
        elif item[0] > heap[0][0]:
            heapq.heapreplace(heap, item)
    _tick_end(args)
    # -mtime descending == mtime ascending (oldest first)
    nodes = [it[2] for it in sorted(heap, key=lambda it: it[0], reverse=True)]
    if _dump([{"path": str(n.path), "size": n.size,
               "mtime": human_time(n.mtime)} for n in nodes], args) == 0:
        return 0
    print(f"Least recently modified files ({len(nodes)} shown, "
          f"{time.time() - started:.2f}s):")
    for node in nodes:
        print(f"{human_time(node.mtime)}  {human_size(node.size):>10}  {node.path}")
    return 0


# --------------------------------------------------------------------------- #
# 9. computerempty
# --------------------------------------------------------------------------- #
def _parser_empty() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge computerempty",
                                description="Empty files and empty directories.")
    _add_common(p, limit=40)
    p.add_argument("--dirs", action="store_true", help="only empty directories")
    p.add_argument("--files", action="store_true", help="only empty files")
    return p


def cmd_empty(args: argparse.Namespace) -> int:
    opts = _opts(args)
    roots = _roots(args)
    started = time.time()
    empty_files: List[str] = []
    empty_dirs: List[str] = []
    seen = 0

    # NB: do NOT set files_only here -- iter_all_files walks directories by
    # pushing the directory nodes, and files_only filters those out.
    for node in _files(args, opts):
        seen += 1
        _tick(seen, started, args)
        if node.size == 0:
            empty_files.append(str(node.path))
            if args.files and len(empty_files) >= args.limit:
                break

    if not args.files:
        dir_opts = Options(**{**opts.__dict__, "dirs_only": True})
        for node in _walk(roots, dir_opts, args.max_items or None,
                          max(1, int(args.max_depth))):
            if not node.is_dir:
                continue
            children, _err, _hidden = _list_dir(node.path, Options(
                include_hidden=True, follow_links=opts.follow_links), 1)
            if not children:
                empty_dirs.append(str(node.path))
                if args.dirs and len(empty_dirs) >= args.limit:
                    break
    _tick_end(args)

    payload = {"empty_files": empty_files[:args.limit],
               "empty_dirs": empty_dirs[:args.limit],
               "empty_file_count": len(empty_files),
               "empty_dir_count": len(empty_dirs)}
    if _dump(payload, args) == 0:
        return 0

    limit = max(1, int(args.limit))
    if not args.dirs:
        print(f"Empty files ({len(empty_files):,} found)"
              f" - showing {min(limit, len(empty_files))}:")
        for path in empty_files[:limit]:
            print(f"  {path}")
    if not args.files:
        print(f"\nEmpty directories ({len(empty_dirs):,} found)"
              f" - showing {min(limit, len(empty_dirs))}:")
        for path in empty_dirs[:limit]:
            print(f"  {path}")
    return 0


# --------------------------------------------------------------------------- #
# 10. computerext - by extension
# --------------------------------------------------------------------------- #
def _parser_ext() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge computerext",
                                description="Size / count grouped by extension.")
    _add_common(p, limit=25)
    p.add_argument("--sort", choices=["size", "count", "name"], default="size")
    return p


def ext_summary(opts: Optional[Options] = None,
                roots: Optional[Sequence[str]] = None,
                max_items: Optional[int] = DEFAULT_MAX_ITEMS
                ) -> Dict[str, Dict[str, int]]:
    """Return ``{ext: {"count": n, "size": bytes}}`` for the machine."""
    opts = opts or Options(max_depth=DEFAULT_DEPTH)
    table: Dict[str, Dict[str, int]] = defaultdict(lambda: {"count": 0, "size": 0})
    for node in iter_all_files(opts, roots=roots, max_items=max_items,
                               max_depth=max(1, opts.max_depth)):
        row = table[node.ext or "(none)"]
        row["count"] += 1
        row["size"] += node.size
    return dict(table)


def cmd_ext(args: argparse.Namespace) -> int:
    opts = _opts(args)
    started = time.time()
    table: Dict[str, Dict[str, int]] = defaultdict(lambda: {"count": 0, "size": 0})
    seen = 0
    for node in _files(args, opts):
        seen += 1
        _tick(seen, started, args)
        row = table[node.ext or "(none)"]
        row["count"] += 1
        row["size"] += node.size
    _tick_end(args)

    items = list(table.items())
    if args.sort == "size":
        items.sort(key=lambda kv: kv[1]["size"], reverse=True)
    elif args.sort == "count":
        items.sort(key=lambda kv: kv[1]["count"], reverse=True)
    else:
        items.sort(key=lambda kv: kv[0])

    limit = max(1, int(args.limit))
    rows = items[:limit]
    payload = [{"ext": e, "count": v["count"], "size": v["size"]} for e, v in rows]
    if _dump({"extensions": payload, "total_bytes": sum(v["size"] for v in table.values()),
              "total_files": sum(v["count"] for v in table.values())}, args) == 0:
        return 0

    print(f"Extensions on this machine ({len(items)} distinct, "
          f"{sum(v['count'] for v in table.values()):,} files):")
    for ext, row in rows:
        print(f"{human_size(row['size']):>12}  {row['count']:>9,} f   {ext}")
    return 0


# --------------------------------------------------------------------------- #
# 11. computerstats - full statistical report
# --------------------------------------------------------------------------- #
def _parser_stats() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge computerstats",
                                description="Whole-machine statistics report.")
    _add_common(p, limit=10)
    return p


def cmd_stats(args: argparse.Namespace) -> int:
    opts = _opts(args)
    started = time.time()
    files = 0
    total = 0
    buckets: Dict[str, Dict[str, int]] = {name: {"count": 0, "size": 0}
                                          for name, _lo, _hi in SIZE_BUCKETS}
    ages = {"today": 0, "7 days": 0, "30 days": 0, "1 year": 0, "older": 0}
    table: Dict[str, Dict[str, int]] = defaultdict(lambda: {"count": 0, "size": 0})
    biggest: List[Node] = []
    now = time.time()

    for node in _files(args, opts):
        files += 1
        total += node.size
        for name, low, high in SIZE_BUCKETS:
            if node.size >= low and (high is None or node.size < high):
                buckets[name]["count"] += 1
                buckets[name]["size"] += node.size
                break
        age_days = (now - node.mtime) / 86400.0
        if age_days < 1:
            ages["today"] += 1
        elif age_days < 7:
            ages["7 days"] += 1
        elif age_days < 30:
            ages["30 days"] += 1
        elif age_days < 365:
            ages["1 year"] += 1
        else:
            ages["older"] += 1
        row = table[node.ext or "(none)"]
        row["count"] += 1
        row["size"] += node.size
        if len(biggest) < max(1, int(args.limit)):
            biggest.append(node)
            biggest.sort(key=lambda n: n.size, reverse=True)
        elif node.size > biggest[-1].size:
            biggest[-1] = node
            biggest.sort(key=lambda n: n.size, reverse=True)
        _tick(files, started, args)
    _tick_end(args)

    top_ext = sorted(table.items(), key=lambda kv: kv[1]["size"], reverse=True)[:10]
    payload = {
        "files": files,
        "bytes": total,
        "elapsed_sec": round(time.time() - started, 3),
        "size_buckets": {k: v for k, v in buckets.items()},
        "age_buckets": ages,
        "top_extensions": [{"ext": e, **v} for e, v in top_ext],
        "largest": [{"path": str(n.path), "size": n.size} for n in biggest],
    }
    if _dump(payload, args) == 0:
        return 0

    print(f"This PC statistics - {files:,} files, {human_size(total)} "
          f"in {payload['elapsed_sec']:.2f}s\n")
    print("by size:")
    for name, _lo, _hi in SIZE_BUCKETS:
        row = buckets[name]
        if row["count"]:
            print(f"  {name:<14} {row['count']:>10,} f   {human_size(row['size']):>12}")
    print("\nby age (last modified):")
    for key, value in ages.items():
        print(f"  {key:<14} {value:>10,} f")
    print("\ntop extensions:")
    for ext, row in top_ext:
        print(f"  {ext:<14} {row['count']:>10,} f   {human_size(row['size']):>12}")
    print("\nlargest files:")
    for node in biggest:
        print(f"  {human_size(node.size):>12}  {node.path}")
    return 0


# --------------------------------------------------------------------------- #
# 12. computermap - block map of every volume
# --------------------------------------------------------------------------- #
def _parser_map() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge computermap",
                                description="Terminal block map of every volume.")
    p.add_argument("-r", "--root", action="append", default=[], metavar="DIR")
    p.add_argument("--width", type=int, default=76)
    p.add_argument("--mode", choices=["blocks", "bars", "both"], default="both")
    p.add_argument("--deep", action="store_true",
                   help="also aggregate the top level of every volume (slow)")
    p.add_argument("-L", "--max-depth", type=int, default=3)
    p.add_argument("-n", "--top", type=int, default=15)
    p.add_argument("-a", "--all", action="store_true")
    p.add_argument("--no-color", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--out", metavar="FILE")
    p.add_argument("-q", "--quiet", action="store_true")
    return p


def _paint_blocks(cells: int, color: bool, seed: str) -> str:
    """A short coloured bar; ``seed`` keeps the colour stable per row."""
    bar = BLOCK * cells
    if not color:
        return bar
    code = PALETTE[sum(ord(c) for c in seed) % len(PALETTE)]
    return f"\033[{code}m{bar}\033[0m"


def cmd_map(args: argparse.Namespace) -> int:
    color = not args.no_color
    roots = [str(Path(r).expanduser()) for r in args.root] or system_roots()
    rows: List[Tuple[str, int]] = []
    for root in roots:
        try:
            total, _used, free = free_space(Path(root))
        except OSError:
            continue
        rows.append((root, total - free if total else 0))
    rows.sort(key=lambda r: r[1], reverse=True)

    payload = {"volumes": [{"root": r, "used": s} for r, s in rows]}
    if args.deep:
        opts = Options(max_depth=args.max_depth, include_hidden=args.all)
        deep = []
        for root in roots:
            try:
                from .treemap import collect
                top_level, largest = collect(root, opts, top=args.top)
            except (OSError, ValueError):
                continue
            deep.append({"root": root,
                         "top_level": [{"name": n, "size": s} for n, s in top_level],
                         "largest": [{"path": p, "size": s, "files": f}
                                     for p, s, f in largest]})
        payload["deep"] = deep
    if _dump(payload, args) == 0:
        return 0

    if args.mode in ("blocks", "both"):
        print(f"\nUsed space per volume "
              f"({human_size(sum(s for _r, s in rows))} total):")
        for line in render_blocks(rows, width=args.width, color=color):
            print(line)
    if args.mode in ("bars", "both"):
        print("\nRanked usage:")
        biggest = max((s for _r, s in rows), default=0) or 1
        width = max(20, args.width // 2)
        for root, size in rows:
            cells = max(1, int(round(size / biggest * width)))
            bar = _paint_blocks(cells, color, root)
            print(f"{human_size(size):>10}  {bar:<{width}}  {root}")
    if args.deep:
        for entry in payload.get("deep", []):
            print(f"\n{entry['root']} - largest directories:")
            for row in entry["largest"][:args.top]:
                print(f"  {human_size(row['size']):>12}  {row['files']:>7} f   "
                      f"{row['path']}")
    return 0


# --------------------------------------------------------------------------- #
# 13. computerfind - by name / glob
# --------------------------------------------------------------------------- #
def _parser_find() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge computerfind",
                                description="Find files by name across all drives.")
    p.add_argument("pattern", help="glob matched against the file name, e.g. '*.iso'")
    _add_common(p, limit=50)
    p.add_argument("--full-path", action="store_true",
                   help="match against the whole path instead of the name")
    p.add_argument("--regex", action="store_true",
                   help="treat the pattern as a regular expression")
    p.add_argument("--ignore-case", action="store_true", help="case-insensitive")
    p.add_argument("--dirs", action="store_true", help="also match directories")
    return p


def cmd_find(args: argparse.Namespace) -> int:
    import fnmatch

    opts = _opts(args)
    started = time.time()
    flags = re.IGNORECASE if args.ignore_case else 0
    rx = re.compile(args.pattern, flags) if args.regex else None
    hits: List[str] = []
    seen = 0
    source = (_walk(_roots(args), opts, args.max_items or None,
                    max(1, int(args.max_depth)))
              if args.dirs else _files(args, opts))
    for node in source:
        seen += 1
        _tick(seen, started, args)
        target = str(node.path) if args.full_path else node.name
        if rx:
            matched = bool(rx.search(target))
        elif args.ignore_case:
            matched = fnmatch.fnmatch(target.lower(), args.pattern.lower())
        else:
            matched = fnmatch.fnmatch(target, args.pattern)
        if matched:
            hits.append(str(node.path))
            if len(hits) >= max(1, int(args.limit)):
                break
    _tick_end(args)

    if _dump({"matches": hits, "count": len(hits), "scanned": seen}, args) == 0:
        return 0
    print(f"{len(hits)} match(es) for {args.pattern!r} "
          f"(scanned {seen:,} entries in {time.time() - started:.2f}s):")
    for path in hits:
        print(f"  {path}")
    return 0


# --------------------------------------------------------------------------- #
# 14. computergrep - content search
# --------------------------------------------------------------------------- #
def _parser_grep() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge computergrep",
                                description="Search file contents on every drive.")
    p.add_argument("pattern", help="regular expression to look for")
    _add_common(p, limit=50)
    p.add_argument("--ignore-case", action="store_true")
    p.add_argument("--encoding", default="utf-8")
    p.add_argument("--file-size-limit", default="20M",
                   help="skip files bigger than this (default: 20M)")
    p.add_argument("--no-content", action="store_true",
                   help="print matching file names only")
    p.add_argument("--context", type=int, default=0,
                   help="print N lines around each match")
    return p


def cmd_grep(args: argparse.Namespace) -> int:
    opts = _opts(args)
    flags = re.IGNORECASE if args.ignore_case else 0
    try:
        rx = re.compile(args.pattern, flags)
    except re.error as exc:
        print(f"computergrep: bad pattern: {exc}", file=sys.stderr)
        return 2

    size_cap = parse_size(args.file_size_limit)
    started = time.time()
    limit = max(1, int(args.limit))
    hits: List[Dict[str, object]] = []
    scanned = 0
    matched_files = 0

    for node in _files(args, opts):
        scanned += 1
        _tick(scanned, started, args)
        if node.size == 0 or node.size > size_cap:
            continue
        try:
            if is_binary(node.path):
                continue
            text = node.path.read_text(encoding=args.encoding, errors="replace")
        except (OSError, ValueError, MemoryError):
            continue
        lines = text.splitlines()
        file_hit = False
        for index, line in enumerate(lines):
            if not rx.search(line):
                continue
            file_hit = True
            hits.append({"path": str(node.path), "line": index + 1,
                         "text": line.strip()[:400]})
            if args.no_content:
                break
            _print_match(node.path, lines, index, rx, args)
            if len(hits) >= limit:
                break
        if file_hit:
            matched_files += 1
        if len(hits) >= limit:
            break
    _tick_end(args)

    if _dump({"hits": hits, "files_matched": matched_files, "scanned": scanned},
             args) == 0:
        return 0
    if args.no_content:
        seen_paths = []
        for hit in hits:
            if hit["path"] not in seen_paths:
                seen_paths.append(str(hit["path"]))
        for path in seen_paths:
            print(path)
    if not args.quiet:
        print(f"\n{len(hits)} match(es) in {matched_files} file(s) "
              f"(scanned {scanned:,} files in {time.time() - started:.2f}s)")
    return 0


def _print_match(path: Path, lines: List[str], index: int, rx, args) -> None:
    if getattr(args, "json", False) or getattr(args, "out", None):
        return
    lo = max(0, index - args.context)
    hi = min(len(lines), index + args.context + 1)
    for i in range(lo, hi):
        mark = ">" if i == index else " "
        print(f"{path}:{i + 1}:{mark}{lines[i][:400]}")


# --------------------------------------------------------------------------- #
# 15. computerdupes
# --------------------------------------------------------------------------- #
def _parser_dupes() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge computerdupes",
                                description="Duplicate files across all drives.")
    _add_common(p, limit=25)
    p.add_argument("--algorithm", default="sha256",
                   choices=["md5", "sha1", "sha256", "blake2b"])
    p.add_argument("--min-dup-size", default="1",
                   help="ignore files smaller than this (default: 1)")
    return p


def find_duplicates(opts: Optional[Options] = None,
                    roots: Optional[Sequence[str]] = None,
                    algorithm: str = "sha256",
                    max_items: Optional[int] = DEFAULT_MAX_ITEMS,
                    min_size: int = 1) -> List[Dict[str, object]]:
    """Return duplicate groups as ``{"size", "hash", "paths": [...]}``."""
    opts = opts or Options(max_depth=DEFAULT_DEPTH)
    by_size: Dict[int, List[Node]] = defaultdict(list)
    for node in iter_all_files(opts, roots=roots, max_items=max_items,
                               max_depth=max(1, opts.max_depth)):
        if node.size >= min_size:
            by_size[node.size].append(node)

    groups: List[Dict[str, object]] = []
    for size, bucket in by_size.items():
        if len(bucket) < 2:
            continue
        by_hash: Dict[str, List[str]] = defaultdict(list)
        for node in bucket:
            try:
                digest = hash_file(node.path, algorithm)
            except OSError:
                continue
            by_hash[digest].append(str(node.path))
        for digest, paths in by_hash.items():
            if len(paths) > 1:
                groups.append({"size": size, "hash": digest,
                               "paths": sorted(paths)})
    groups.sort(key=lambda g: int(g["size"]) * (len(g["paths"]) - 1),
                reverse=True)
    return groups


def cmd_dupes(args: argparse.Namespace) -> int:
    opts = _opts(args)
    started = time.time()
    min_size = parse_size(args.min_dup_size)
    by_size: Dict[int, List[Node]] = defaultdict(list)
    seen = 0
    for node in _files(args, opts):
        seen += 1
        _tick(seen, started, args)
        if node.size >= min_size:
            by_size[node.size].append(node)
    _tick_end(args)

    groups: List[Dict[str, object]] = []
    hashed = 0
    for size, bucket in by_size.items():
        if len(bucket) < 2:
            continue
        by_hash: Dict[str, List[str]] = defaultdict(list)
        for node in bucket:
            try:
                digest = hash_file(node.path, args.algorithm)
            except OSError:
                continue
            hashed += 1
            by_hash[digest].append(str(node.path))
        for digest, paths in by_hash.items():
            if len(paths) > 1:
                groups.append({"size": size, "hash": digest,
                               "paths": sorted(paths)})
    groups.sort(key=lambda g: int(g["size"]) * (len(g["paths"]) - 1), reverse=True)
    reclaimable = sum(int(g["size"]) * (len(g["paths"]) - 1) for g in groups)
    payload = {"groups": groups[:max(1, int(args.limit))],
               "group_count": len(groups),
               "hashed": hashed,
               "reclaimable_bytes": reclaimable}
    if _dump(payload, args) == 0:
        return 0

    print(f"{len(groups)} duplicate group(s), "
          f"{human_size(reclaimable)} reclaimable "
          f"({hashed:,} files hashed, {time.time() - started:.2f}s)")
    for group in groups[:max(1, int(args.limit))]:
        print(f"\n  {human_size(int(group['size']))} x {len(group['paths'])}  "
              f"[{str(group['hash'])[:16]}]")
        for path in group["paths"]:
            print(f"    {path}")
    return 0


# --------------------------------------------------------------------------- #
# 16. computertemp
# --------------------------------------------------------------------------- #
def _parser_temp() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge computertemp",
                                description="Temporary / cache / junk files.")
    _add_common(p, limit=50)
    p.add_argument("--dirs", action="store_true",
                   help="also report cache directories")
    return p


def cmd_temp(args: argparse.Namespace) -> int:
    import fnmatch

    opts = _opts(args)
    started = time.time()
    hits: List[Dict[str, object]] = []
    total = 0
    seen = 0
    dir_hits: List[Dict[str, object]] = []
    source = (_walk(_roots(args), opts, args.max_items or None,
                    max(1, int(args.max_depth)))
              if args.dirs else _files(args, opts))
    for node in source:
        seen += 1
        _tick(seen, started, args)
        if node.is_dir:
            if node.name.lower() in TEMP_DIR_NAMES:
                dir_hits.append({"path": str(node.path), "kind": "cache dir"})
            continue
        if any(fnmatch.fnmatch(node.name.lower(), pat) for pat in TEMP_PATTERNS):
            total += node.size
            hits.append({"path": str(node.path), "size": node.size,
                         "mtime": human_time(node.mtime)})
            if len(hits) >= max(1, int(args.limit)) and not args.dirs:
                break
    _tick_end(args)

    payload = {"files": hits, "file_count": len(hits), "bytes": total,
               "dirs": dir_hits[:max(1, int(args.limit))],
               "dir_count": len(dir_hits)}
    if _dump(payload, args) == 0:
        return 0

    print(f"Temporary / junk files: {len(hits):,} found, {human_size(total)} "
          f"({time.time() - started:.2f}s)")
    for hit in hits[:max(1, int(args.limit))]:
        print(f"  {human_size(int(hit['size'])):>10}  {hit['mtime']}  {hit['path']}")
    if args.dirs and dir_hits:
        print(f"\nCache directories: {len(dir_hits):,}")
        for hit in dir_hits[:max(1, int(args.limit))]:
            print(f"  {hit['path']}")
    return 0


# --------------------------------------------------------------------------- #
# 17. computerexport
# --------------------------------------------------------------------------- #
def _parser_export() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge computerexport",
                                description="Export the whole machine to a file.")
    _add_common(p, out=False)
    p.add_argument("--format", choices=["json", "csv", "txt"], default="json")
    p.add_argument("--out", metavar="FILE", default="computer-export.json")
    p.add_argument("--dirs", action="store_true", help="include directories")
    return p


def cmd_export(args: argparse.Namespace) -> int:
    opts = _opts(args)
    out = Path(args.out)
    started = time.time()
    count = 0
    total = 0

    if args.format == "json":
        payload: Dict[str, object] = {
            "generated": human_time(time.time()),
            "roots": _roots(args),
            "entries": [],
        }
        entries: List[Dict[str, object]] = payload["entries"]  # type: ignore[assignment]
        source = (_walk(_roots(args), opts, args.max_items or None,
                        max(1, int(args.max_depth)))
                  if args.dirs else _files(args, opts))
        for node in source:
            count += 1
            total += node.size
            _tick(count, started, args)
            entries.append({
                "path": str(node.path),
                "name": node.name,
                "is_dir": node.is_dir,
                "size": node.size,
                "ext": node.ext,
                "mtime": node.mtime,
            })
        _tick_end(args)
        payload["count"] = count
        payload["bytes"] = total
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                       encoding="utf-8")
    else:
        source = (_walk(_roots(args), opts, args.max_items or None,
                        max(1, int(args.max_depth)))
                  if args.dirs else _files(args, opts))
        with out.open("w", encoding="utf-8", newline="") as fh:
            if args.format == "csv":
                fh.write("path,name,is_dir,size,ext,mtime\n")
            for node in source:
                count += 1
                total += node.size
                _tick(count, started, args)
                if args.format == "csv":
                    fh.write("{},{},{},{},{},{}\n".format(
                        str(node.path).replace(",", " "),
                        node.name.replace(",", " "),
                        int(node.is_dir), node.size, node.ext,
                        human_time(node.mtime)))
                else:
                    fh.write(f"{human_size(node.size):>12}  {node.path}\n")
        _tick_end(args)

    print(f"exported {count:,} entries ({human_size(total)}) -> {out} "
          f"[{args.format}] in {time.time() - started:.2f}s")
    return 0


# --------------------------------------------------------------------------- #
# 18/19. snapshot / diff
# --------------------------------------------------------------------------- #
def _parser_snapshot() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge computersnapshot",
                                description="Save a snapshot of the machine.")
    _add_common(p, out=False)
    p.add_argument("--out", metavar="FILE", default="",
                   help="snapshot file (default: pc-snapshot-<timestamp>.json)")
    return p


def snapshot(opts: Optional[Options] = None,
             roots: Optional[Sequence[str]] = None,
             max_items: Optional[int] = DEFAULT_MAX_ITEMS
             ) -> Dict[str, Dict[str, float]]:
    """Return ``{path: {"size": n, "mtime": ts}}`` for the machine."""
    opts = opts or Options(max_depth=DEFAULT_DEPTH)
    snap: Dict[str, Dict[str, float]] = {}
    for node in iter_all_files(opts, roots=roots, max_items=max_items,
                               max_depth=max(1, opts.max_depth)):
        snap[str(node.path)] = {"size": float(node.size), "mtime": node.mtime}
    return snap


def cmd_snapshot(args: argparse.Namespace) -> int:
    opts = _opts(args)
    started = time.time()
    snap: Dict[str, Dict[str, float]] = {}
    seen = 0
    for node in _files(args, opts):
        seen += 1
        _tick(seen, started, args)
        snap[str(node.path)] = {"size": float(node.size), "mtime": node.mtime}
    _tick_end(args)

    out = args.out or f"pc-snapshot-{time.strftime('%Y%m%d-%H%M%S')}.json"
    payload = {"generated": time.time(), "generated_text": human_time(time.time()),
               "roots": _roots(args), "count": len(snap), "files": snap}
    Path(out).write_text(json.dumps(payload, ensure_ascii=False),
                         encoding="utf-8")
    print(f"snapshot of {len(snap):,} files written to {out} "
          f"({time.time() - started:.2f}s)")
    return 0


def _parser_diff() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge computerdiff",
                                description="Diff two snapshots.")
    p.add_argument("old_snapshot")
    p.add_argument("new_snapshot")
    p.add_argument("-n", "--limit", type=int, default=30,
                   help="rows per section (default: 30)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--out", metavar="FILE")
    p.add_argument("-q", "--quiet", action="store_true")
    return p


def diff_snapshots(old: Dict[str, Dict[str, float]],
                   new: Dict[str, Dict[str, float]]) -> Dict[str, List[str]]:
    """Compare two snapshots produced by :func:`snapshot`."""
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = sorted(p for p in set(old) & set(new)
                     if old[p].get("size") != new[p].get("size")
                     or abs(float(old[p].get("mtime", 0)) -
                            float(new[p].get("mtime", 0))) > 0.5)
    return {"added": added, "removed": removed, "changed": changed}


def cmd_diff(args: argparse.Namespace) -> int:
    try:
        old = json.loads(Path(args.old_snapshot).read_text(encoding="utf-8"))
        new = json.loads(Path(args.new_snapshot).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"computerdiff: {exc}", file=sys.stderr)
        return 1
    old_files = old.get("files", old)
    new_files = new.get("files", new)
    result = diff_snapshots(old_files, new_files)
    result["summary"] = {
        "old_count": len(old_files),
        "new_count": len(new_files),
        "added": len(result["added"]),
        "removed": len(result["removed"]),
        "changed": len(result["changed"]),
    }
    if _dump(result, args) == 0:
        return 0

    limit = max(1, int(args.limit))
    print(f"snapshot diff: {len(old_files):,} -> {len(new_files):,} files")
    for section in ("added", "removed", "changed"):
        rows = result[section]
        print(f"\n{section}: {len(rows):,}")
        for path in rows[:limit]:
            print(f"  {path}")
        if len(rows) > limit:
            print(f"  ... {len(rows) - limit} more")
    return 0


# --------------------------------------------------------------------------- #
# 20. computerwatch
# --------------------------------------------------------------------------- #
def _parser_watch() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge computerwatch",
                                description="Live watch for file changes.")
    p.add_argument("path", nargs="?", default=".", help="directory to watch")
    p.add_argument("--interval", type=float, default=2.0,
                   help="seconds between polls (default: 2)")
    p.add_argument("--duration", type=float, default=0,
                   help="stop after this many seconds (0 = run forever)")
    p.add_argument("-L", "--max-depth", type=int, default=DEFAULT_DEPTH)
    p.add_argument("-a", "--all", action="store_true")
    p.add_argument("--max-items", type=int, default=DEFAULT_MAX_ITEMS)
    p.add_argument("--out", metavar="FILE", help="append events to this file")
    p.add_argument("-q", "--quiet", action="store_true")
    p.add_argument("--no-color", action="store_true")
    return p


def cmd_watch(args: argparse.Namespace) -> int:
    root = str(Path(args.path).expanduser())
    opts = Options(max_depth=max(1, int(args.max_depth)),
                   include_hidden=args.all)
    previous = snapshot(opts, roots=[root], max_items=args.max_items or None)
    started = time.time()
    if not args.quiet:
        print(f"watching {root} ({len(previous):,} files) - Ctrl+C to stop")
    handle = None
    if args.out:
        handle = Path(args.out).open("a", encoding="utf-8")
    try:
        while True:
            if args.duration and time.time() - started > args.duration:
                break
            time.sleep(max(0.2, args.interval))
            current = snapshot(opts, roots=[root],
                               max_items=args.max_items or None)
            delta = diff_snapshots(previous, current)
            stamp = time.strftime("%H:%M:%S")
            for path in delta["added"]:
                _emit_event(f"[{stamp}] + {path}", handle)
            for path in delta["removed"]:
                _emit_event(f"[{stamp}] - {path}", handle)
            for path in delta["changed"]:
                _emit_event(f"[{stamp}] ~ {path} "
                            f"({human_size(int(current[path]['size']))})", handle)
            previous = current
    except KeyboardInterrupt:
        print("\nstopped")
        return 130
    finally:
        if handle:
            handle.close()
    return 0


def _emit_event(text: str, handle=None) -> None:
    print(text)
    if handle:
        handle.write(text + "\n")
        handle.flush()


# --------------------------------------------------------------------------- #
# 21. computeraudit
# --------------------------------------------------------------------------- #
def _parser_audit() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge computeraudit",
                                description="Permission audit across the machine.")
    _add_common(p, limit=40)
    return p


def cmd_audit(args: argparse.Namespace) -> int:
    # POSIX permission bits are meaningless on Windows (every file reports
    # 0o666), so the mode scan only runs where it actually means something.
    posix = os.name != "nt"
    if not posix:
        print("computeraudit: POSIX permission bits do not exist on Windows; "
              "only a reachability scan is performed.", file=sys.stderr)

    opts = _opts(args)
    started = time.time()
    world_writable: List[str] = []
    setuid: List[str] = []
    setgid: List[str] = []
    unreadable: List[str] = []
    seen = 0
    limit = max(1, int(args.limit))
    for node in _files(args, opts):
        seen += 1
        _tick(seen, started, args)
        if not posix:
            if node.error:
                unreadable.append(str(node.path))
            continue
        mode = node.mode
        if mode & 0o002:
            world_writable.append(str(node.path))
        if mode & 0o4000:
            setuid.append(str(node.path))
        if mode & 0o2000:
            setgid.append(str(node.path))
        if len(world_writable) >= limit:
            break
    _tick_end(args)

    payload = {"posix": posix,
               "world_writable": world_writable[:limit],
               "setuid": setuid[:limit],
               "setgid": setgid[:limit],
               "unreadable": unreadable[:limit],
               "world_writable_count": len(world_writable),
               "scanned": seen}
    if _dump(payload, args) == 0:
        return 0

    print(f"audit: scanned {seen:,} files in {time.time() - started:.2f}s")
    if not posix:
        print("  POSIX mode bits unavailable on this platform - "
              "run this on Linux/macOS for the permission report.")
        if unreadable:
            print(f"  unreadable ({len(unreadable):,}):")
            for path in unreadable[:limit]:
                print(f"    {path}")
        return 0
    print(f"\nworld-writable ({len(world_writable):,}) - showing {limit}:")
    for path in world_writable[:limit]:
        print(f"  {path}")
    if setuid:
        print(f"\nsetuid ({len(setuid):,}):")
        for path in setuid[:limit]:
            print(f"  {path}")
    if setgid:
        print(f"\nsetgid ({len(setgid):,}):")
        for path in setgid[:limit]:
            print(f"  {path}")
    return 0


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
PARSERS: Dict[str, Callable[[], argparse.ArgumentParser]] = {
    "computerinfo": _parser_info,
    "computerdrives": _parser_drives,
    "computerscan": _parser_scan,
    "computertree": _parser_tree,
    "computerdirs": _parser_dirs,
    "computerlarge": lambda: _parser_top("large"),
    "computernew": lambda: _parser_top("new"),
    "computerold": _parser_old,
    "computerempty": _parser_empty,
    "computerext": _parser_ext,
    "computerstats": _parser_stats,
    "computermap": _parser_map,
    "computerfind": _parser_find,
    "computergrep": _parser_grep,
    "computerdupes": _parser_dupes,
    "computertemp": _parser_temp,
    "computerexport": _parser_export,
    "computersnapshot": _parser_snapshot,
    "computerdiff": _parser_diff,
    "computerwatch": _parser_watch,
    "computeraudit": _parser_audit,
}

HANDLERS: Dict[str, Callable[[argparse.Namespace], int]] = {
    "computerinfo": cmd_info,
    "computerdrives": cmd_drives,
    "computerscan": cmd_scan,
    "computertree": cmd_tree,
    "computerdirs": cmd_dirs,
    "computerlarge": cmd_large,
    "computernew": cmd_new,
    "computerold": cmd_old,
    "computerempty": cmd_empty,
    "computerext": cmd_ext,
    "computerstats": cmd_stats,
    "computermap": cmd_map,
    "computerfind": cmd_find,
    "computergrep": cmd_grep,
    "computerdupes": cmd_dupes,
    "computertemp": cmd_temp,
    "computerexport": cmd_export,
    "computersnapshot": cmd_snapshot,
    "computerdiff": cmd_diff,
    "computerwatch": cmd_watch,
    "computeraudit": cmd_audit,
}


def build_parser(name: str) -> argparse.ArgumentParser:
    return PARSERS[name]()


def run(name: str, argv: Sequence[str]) -> int:
    """Run one computerkit command by (canonical) name."""
    parser = PARSERS[name]()
    try:
        args = parser.parse_args(list(argv))
    except SystemExit as exc:  # argparse --help / bad usage
        return int(exc.code or 0)
    try:
        return HANDLERS[name](args)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    except OSError as exc:
        print(f"{APP} {name}: {exc}", file=sys.stderr)
        return 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(__doc__)
        return 0
    name = ALIASES.get(args[0], args[0])
    if name not in HANDLERS:
        print(f"{APP}: computerkit has no command {args[0]!r}", file=sys.stderr)
        return 2
    return run(name, args[1:])


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
