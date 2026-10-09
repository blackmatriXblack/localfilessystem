#!/usr/bin/env python3
"""
fileforge.computer
==================

Whole-machine ("This PC") scanning engine.

Where :mod:`fileforge.treeview` looks at *one* root, this module looks at
**every** drive / mount point of the computer at once, so a caller can see
the full machine in a single view.

Everything is read live from disk - there is no cache, no index and no
background crawler. Windows junctions, reparse points and POSIX symlinks are
skipped by default because they routinely point at offline network locations.

Library use
-----------
    from fileforge.computer import iter_computer_tree, iter_all_files

    for prefix, node, stats in iter_computer_tree():
        print(prefix + node.name)

    for node in iter_all_files(max_items=5000):
        print(node.path)

Command line
------------
    python fileforge.py computer -L 2
    python fileforge.py computer --files --limit 500
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Sequence, Tuple

try:  # package import
    from .treeview import (Node, Options, Stats, _list_dir, human_size,
                           human_time, system_roots)
    from .utils import free_space
except ImportError:  # pragma: no cover - direct script execution fallback
    from treeview import (Node, Options, Stats, _list_dir, human_size,  # type: ignore
                          human_time, system_roots)  # type: ignore
    from utils import free_space  # type: ignore


#: Public, documented wrapper around the safe directory lister.
def list_dir(path: Path, opts: Optional[Options] = None,
             depth: int = 1) -> Tuple[List[Node], Optional[str]]:
    """List one directory without ever following a reparse point."""
    return _list_dir(Path(path), opts or Options(), depth)


# --------------------------------------------------------------------------- #
# Volume inventory
# --------------------------------------------------------------------------- #


def volumes() -> List[Tuple[str, int, int]]:
    """
    Return ``(root, total_bytes, free_bytes)`` for every mounted volume.

    Volumes that cannot be queried (offline network drives, empty card
    readers) simply report ``0`` instead of raising.
    """
    rows: List[Tuple[str, int, int]] = []
    for root in system_roots():
        try:
            total, _used, free = free_space(Path(root))
        except OSError:
            total, free = 0, 0
        rows.append((root, total, free))
    return rows


def describe_volumes() -> List[str]:
    """Human readable one-liner per volume."""
    lines = []
    for root, total, free in volumes():
        if total:
            used = total - free
            lines.append(
                f"{root:<24} {human_size(free):>10} free of {human_size(total):>10}"
                f"  ({used * 100 // total}% used)"
            )
        else:
            lines.append(f"{root:<24} {'unavailable':>10}")
    return lines


# --------------------------------------------------------------------------- #
# Whole-machine tree
# --------------------------------------------------------------------------- #


def iter_computer_tree(opts: Optional[Options] = None,
                       roots: Optional[Sequence[str]] = None,
                       limit: Optional[int] = None
                       ) -> Iterator[Tuple[str, Node, Stats]]:
    """
    Stream the tree of the whole computer.

    Yields ``(prefix, node, stats)``. Each volume appears as a top level
    directory node, so the output reads like the "This PC" view of a file
    manager. ``stats`` is a single live object accumulated across volumes.
    """
    from .treeview import iter_tree  # local import keeps the module importable

    opts = opts or Options()
    roots = list(roots) if roots else system_roots()
    stats = Stats()
    started = time.time()

    for root in roots:
        try:
            st = os.stat(root)
        except OSError:
            continue
        volume = Node(
            path=Path(root),
            name=root,
            is_dir=True,
            size=st.st_size,
            mtime=st.st_mtime,
            mode=st.st_mode,
            depth=0,
        )
        stats.scanned += 1
        stats.dirs += 1
        yield "", volume, stats

        if limit is not None and stats.scanned >= limit:
            stats.truncated = True
            stats.elapsed = time.time() - started
            return

        first = True
        try:
            for prefix, node, _sub in iter_tree(root, opts):
                if first:  # skip the duplicate root line of the sub-walk
                    first = False
                    continue
                stats.scanned += 1
                if node.is_dir:
                    stats.dirs += 1
                else:
                    stats.files += 1
                    stats.bytes += node.size
                yield prefix, node, stats
                if limit is not None and stats.scanned >= limit:
                    stats.truncated = True
                    stats.elapsed = time.time() - started
                    return
        except Exception:  # noqa: BLE001 - one bad volume must not stop the rest
            stats.errors += 1
            continue

    stats.elapsed = time.time() - started


# --------------------------------------------------------------------------- #
# Whole-machine flat file list
# --------------------------------------------------------------------------- #


def iter_all_files(opts: Optional[Options] = None,
                   roots: Optional[Sequence[str]] = None,
                   max_items: Optional[int] = 200000,
                   max_depth: Optional[int] = None,
                   should_stop=None) -> Iterator[Node]:
    """
    Yield every regular file on the machine, depth-first, volume by volume.

    ``should_stop`` is an optional zero-argument callable polled between
    batches so a GUI can cancel a long scan.
    """
    opts = opts or Options()
    roots = list(roots) if roots else system_roots()
    depth_cap = max_depth if max_depth is not None else max(opts.max_depth, 1)
    produced = 0

    for root in roots:
        stack: List[Tuple[Path, int]] = [(Path(root), 0)]
        while stack:
            if should_stop is not None and should_stop():
                return
            path, depth = stack.pop()
            if depth >= depth_cap:
                continue
            items, _err, _hidden = _list_dir(path, opts, depth + 1)
            # directories first, then files, so the visible list fills faster
            for node in items:
                if node.is_dir:
                    stack.append((node.path, depth + 1))
            for node in items:
                if node.is_dir or opts.dirs_only:
                    continue
                # checked per item so a GUI "Stop" reacts immediately
                if should_stop is not None and should_stop():
                    return
                produced += 1
                yield node
                if max_items is not None and produced >= max_items:
                    return


def count_files(opts: Optional[Options] = None,
                roots: Optional[Sequence[str]] = None,
                max_items: Optional[int] = None) -> int:
    """Count files reachable on the machine (bounded by ``max_items``)."""
    return sum(1 for _ in iter_all_files(opts, roots, max_items))


# --------------------------------------------------------------------------- #
# Command line
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="fileforge computer",
        description="Show the whole computer's file structure as a tree.",
    )
    p.add_argument("-L", "--max-depth", type=int, default=2,
                   help="levels below each volume (default: 2)")
    p.add_argument("-a", "--all", action="store_true", help="include hidden entries")
    p.add_argument("-d", "--dirs-only", action="store_true", help="directories only")
    p.add_argument("--ext", action="append", default=[], help="keep only this extension")
    p.add_argument("--include", action="append", default=[], help="glob include filter")
    p.add_argument("--exclude", action="append", default=[], help="glob exclude filter")
    p.add_argument("--min-size", help="minimum file size, e.g. 10M")
    p.add_argument("--max-size", help="maximum file size, e.g. 1G")
    p.add_argument("--sort", choices=["name", "size", "mtime", "none"], default="name")
    p.add_argument("-n", "--limit", type=int, help="stop after N entries")
    p.add_argument("--max-children", type=int, default=0, metavar="N",
                   help="cap entries listed per directory (0 = unlimited)")
    p.add_argument("--stats", action="store_true", help="print a summary")
    p.add_argument("--ascii", action="store_true", help="ASCII branch characters")
    p.add_argument("--no-color", action="store_true", help="disable ANSI colors")
    p.add_argument("--no-size", action="store_true", help="hide file sizes")
    p.add_argument("--volumes", action="store_true",
                   help="only list the volumes with their free space")
    p.add_argument("--files", action="store_true",
                   help="print a flat list of every file instead of a tree")
    p.add_argument("--full-path", action="store_true",
                   help="with --files, print absolute paths")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    from .treeview import format_node, parse_size

    args = build_parser().parse_args(argv)

    if args.volumes:
        for line in describe_volumes():
            print(line)
        return 0

    opts = Options(
        max_depth=max(0, args.max_depth),
        include_hidden=args.all,
        dirs_only=args.dirs_only,
        follow_links=False,
        extensions=tuple(args.ext or ()),
        include=tuple(args.include or ()),
        exclude=tuple(args.exclude or ()),
        sort_by=args.sort,
        max_children=args.max_children if args.max_children > 0 else None,
        min_size=parse_size(args.min_size) if args.min_size else None,
        max_size=parse_size(args.max_size) if args.max_size else None,
    )

    color = not args.no_color
    box_ascii = args.ascii
    limit = args.limit
    shown = 0

    try:
        if args.files:
            for node in iter_all_files(opts, max_items=limit,
                                       max_depth=max(opts.max_depth, 1)):
                text = str(node.path) if args.full_path else node.name
                if not args.no_size:
                    print(f"{human_size(node.size):>10}  {text}")
                else:
                    print(text)
                shown += 1
            print(f"\n{shown} file(s) listed", file=sys.stderr)
            return 0

        stats = Stats()
        for prefix, node, stats in iter_computer_tree(opts, limit=limit):
            line = prefix
            if box_ascii:
                line = (line.replace("├── ", "|-- ").replace("└── ", "`-- ")
                            .replace("│   ", "|   "))
            print(line + format_node(node, opts, show_size=not args.no_size,
                                     color=color))
            shown += 1

        if args.stats:
            print(
                f"\n{stats.dirs} director{'y' if stats.dirs == 1 else 'ies'}, "
                f"{stats.files} file(s), {human_size(stats.bytes)} total, "
                f"{stats.errors} unreadable, {stats.elapsed:.2f}s"
                + (" [truncated]" if stats.truncated else "")
            )
        return 0
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    except OSError as exc:
        print(f"computer: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
