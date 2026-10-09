#!/usr/bin/env python3
"""
fileforge.treemap
=================

Terminal "treemap" views of disk usage, built on top of the live, cache-free
scanner in :mod:`fileforge.treeview`.

Two complementary visuals are provided:

``blocks``
    A proportional block map. Each directory/file gets a run of ``█``
    characters whose length is proportional to its share of the parent.

``bars``
    A ranked horizontal bar chart of the largest directories with a
    human readable size and file count.

Both read the disk live - nothing is cached between runs.

Command line
------------
    python fileforge.py treemap .
    python fileforge.py treemap D:\\ -L 3 --top 25 --mode bars
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

try:  # package import
    from .treeview import Options, build_tree, dir_sizes
    from .utils import human_size
except ImportError:  # pragma: no cover - direct script execution fallback
    from treeview import Options, build_tree, dir_sizes  # type: ignore
    from utils import human_size  # type: ignore

BLOCK = "█"
PALETTE = [31, 32, 33, 34, 35, 36, 91, 92, 93, 94, 95, 96]


def _color(text: str, code: int, enabled: bool) -> str:
    if not enabled:
        return text
    return f"\033[{code}m{text}\033[0m"


def render_blocks(rows: List[Tuple[str, int]], width: int = 76,
                  color: bool = True) -> List[str]:
    """
    Render ``(label, size)`` pairs as one proportional line of block glyphs.

    Sizes are normalised against the largest entry, so the widest row fills
    the requested ``width``.
    """
    if not rows:
        return []
    total = sum(size for _label, size in rows) or 1
    out: List[str] = []
    line = []
    legend: List[str] = []
    for index, (label, size) in enumerate(rows):
        share = size / total
        cells = max(1, int(round(share * width)))
        code = PALETTE[index % len(PALETTE)]
        segment = BLOCK * cells
        line.append(_color(segment, code, color))
        legend.append(
            f"  {_color(BLOCK * 2, code, color)}  {label:<42} "
            f"{human_size(size):>10}  {share * 100:5.1f}%"
        )
    out.append("".join(line))
    out.append("")
    out.extend(legend)
    return out


def render_bars(rows: List[Tuple[str, int, int]], width: int = 52,
                color: bool = True) -> List[str]:
    """Render ``(label, size, files)`` as a ranked bar chart."""
    if not rows:
        return []
    biggest = max(size for _l, size, _f in rows) or 1
    out: List[str] = []
    for index, (label, size, files) in enumerate(rows):
        cells = max(1, int(round(size / biggest * width)))
        code = PALETTE[index % len(PALETTE)]
        # pad manually: ANSI escapes would otherwise corrupt the alignment
        bar = _color(BLOCK * cells, code, color) + " " * max(0, width - cells)
        out.append(f"{human_size(size):>10}  {bar}  {files:>7} f   {label}")
    return out


def collect(root: str, opts: Optional[Options] = None,
            top: int = 20) -> Tuple[List[Tuple[str, int]], List[Tuple[str, int, int]]]:
    """
    Return ``(top_level_rows, largest_dir_rows)`` for ``root``.

    * ``top_level_rows``   - immediate children of ``root`` with their
      aggregated size (used by the block map).
    * ``largest_dir_rows`` - the ``top`` biggest directories anywhere below.
    """
    opts = opts or Options(max_depth=4)
    tree = build_tree(root, opts)

    top_level: List[Tuple[str, int]] = []
    for child in tree.children:
        size = child.node.agg_size or child.node.size
        top_level.append((child.node.name + (os.sep if child.node.is_dir else ""), size))
    top_level.sort(key=lambda r: r[1], reverse=True)
    top_level = top_level[:top]

    largest = [(str(p), s, f) for p, s, f in dir_sizes(root, opts, top=top)]
    return top_level, largest


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fileforge treemap",
        description="Terminal treemap / bar chart of disk usage (live scan).",
    )
    parser.add_argument("path", nargs="?", default=".", help="root directory")
    parser.add_argument("-L", "--max-depth", type=int, default=4,
                        help="how deep to aggregate (default: 4)")
    parser.add_argument("-n", "--top", type=int, default=20, help="how many entries")
    parser.add_argument("--mode", choices=["blocks", "bars", "both"], default="both")
    parser.add_argument("-a", "--all", action="store_true", help="include hidden entries")
    parser.add_argument("--width", type=int, default=76, help="chart width in columns")
    parser.add_argument("--no-color", action="store_true", help="disable ANSI colors")
    args = parser.parse_args(argv)

    color = not args.no_color
    opts = Options(max_depth=args.max_depth, include_hidden=args.all)

    try:
        top_level, largest = collect(args.path, opts, top=args.top)
    except (OSError, ValueError) as exc:
        print(f"treemap: {exc}", file=sys.stderr)
        return 1

    root_label = str(Path(args.path).expanduser())
    if args.mode in ("blocks", "both"):
        print(f"\nBlock map of {root_label} (top level, {human_size(sum(s for _, s in top_level))})")
        for line in render_blocks(top_level, width=args.width, color=color):
            print(line)

    if args.mode in ("bars", "both"):
        print(f"\nLargest directories under {root_label}")
        for line in render_bars(largest, width=max(20, args.width - 24), color=color):
            print(line)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
