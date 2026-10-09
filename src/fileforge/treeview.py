#!/usr/bin/env python3
"""
fileforge.treeview
==================

Live, **cache-free** file-system tree scanner and renderer.

Design goals
------------
* **No cache at all.** Every run re-reads the disk through ``os.scandir``.
  Nothing is persisted to disk, nothing is reused between runs, and the
  tree always reflects the current state of the volume.
* **Streaming output.** Lines are emitted while the scan is still running,
  so memory usage stays proportional to the tree *depth* instead of the
  tree *size*. A 10-million-file drive can be rendered with a few KB of RAM.
* **Never hangs.** Windows junctions / reparse points and POSIX symlinks are
  not followed by default. They frequently point at unreachable network
  locations and would otherwise block the whole scan for minutes.
* **Cross platform.** Linux, Windows and macOS, standard library only.

Library use
-----------
    from fileforge.treeview import Options, iter_tree

    opts = Options(max_depth=2, dirs_only=True)
    for prefix, node in iter_tree("D:/", opts):
        print(prefix + node.name)

Command line
------------
    python fileforge.py tree D:\\ -L 2
    python fileforge.py drives
    python fileforge.py tree . --du --stats
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import string
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

try:  # package import
    from .utils import IS_MACOS, IS_WINDOWS, human_size, human_time, resolve
except ImportError:  # pragma: no cover - direct script execution fallback
    from utils import IS_MACOS, IS_WINDOWS, human_size, human_time, resolve  # type: ignore

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

#: Hard ceiling so a runaway ``-L`` can never blow the Python stack.
MAX_DEPTH_LIMIT = 512

_UNICODE_BOX = {"tee": "├── ", "elbow": "└── ", "pipe": "│   ", "blank": "    "}
_ASCII_BOX = {"tee": "|-- ", "elbow": "`-- ", "pipe": "|   ", "blank": "    "}

if IS_WINDOWS:
    _FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
else:
    _FILE_ATTRIBUTE_REPARSE_POINT = 0


class TreeError(Exception):
    """Raised for recoverable tree-scanning problems."""


# --------------------------------------------------------------------------- #
# Options / models
# --------------------------------------------------------------------------- #


@dataclass
class Options:
    """Filtering and rendering options for a tree scan."""

    max_depth: int = 3
    include_hidden: bool = False
    dirs_only: bool = False
    files_only: bool = False
    follow_links: bool = False
    min_size: Optional[int] = None
    max_size: Optional[int] = None
    extensions: Tuple[str, ...] = ()
    include: Tuple[str, ...] = ()
    exclude: Tuple[str, ...] = ()
    sort_by: str = "name"          # name | size | mtime | none
    reverse: bool = False
    dirs_first: bool = True
    limit: Optional[int] = None
    newer_than: Optional[float] = None
    older_than: Optional[float] = None
    #: Cap on children rendered per directory. A folder with 300k entries is
    #: neither viewable nor cheap to enumerate, so GUIs set this (e.g. 500)
    #: and show a "+N more" marker instead of stalling the whole scan.
    max_children: Optional[int] = None

    def normalized_extensions(self) -> Tuple[str, ...]:
        return tuple(e.lower() if e.startswith(".") else "." + e.lower()
                     for e in self.extensions if e)


@dataclass
class Node:
    """One entry produced by a tree scan."""

    path: Path
    name: str
    is_dir: bool = False
    is_link: bool = False
    size: int = 0
    mtime: float = 0.0
    mode: int = 0
    depth: int = 0
    error: Optional[str] = None
    # Aggregated values, only filled when ``--du``/JSON mode is used.
    agg_size: int = 0
    n_files: int = 0
    n_dirs: int = 0

    @property
    def ext(self) -> str:
        return os.path.splitext(self.name)[1].lower()

    @property
    def is_hidden(self) -> bool:
        return self.name.startswith(".")


@dataclass
class Stats:
    """Counters collected while a scan is running."""

    files: int = 0
    dirs: int = 0
    bytes: int = 0
    errors: int = 0
    scanned: int = 0
    elapsed: float = 0.0
    truncated: bool = False

    def as_dict(self) -> Dict[str, object]:
        return {
            "files": self.files,
            "dirs": self.dirs,
            "bytes": self.bytes,
            "errors": self.errors,
            "scanned": self.scanned,
            "elapsed_sec": round(self.elapsed, 3),
            "truncated": self.truncated,
        }


# --------------------------------------------------------------------------- #
# Low level helpers
# --------------------------------------------------------------------------- #


def parse_size(text: str) -> int:
    """Parse ``'10M'``/``'512'``/``'1.5GiB'`` into a byte count."""
    raw = str(text).strip().lower().replace(" ", "")
    if not raw:
        raise TreeError("Empty size expression")
    for suffix in ("kib", "mib", "gib", "tib", "kb", "mb", "gb", "tb", "k", "m", "g", "t", "b"):
        if raw.endswith(suffix):
            num = raw[: -len(suffix)]
            mult = {
                "b": 1, "k": 1024, "kb": 1024, "kib": 1024,
                "m": 1024 ** 2, "mb": 1024 ** 2, "mib": 1024 ** 2,
                "g": 1024 ** 3, "gb": 1024 ** 3, "gib": 1024 ** 3,
                "t": 1024 ** 4, "tb": 1024 ** 4, "tib": 1024 ** 4,
            }[suffix]
            return int(float(num) * mult)
    return int(float(raw))


def parse_duration(text: str) -> float:
    """Parse ``'7d'``/``'12h'``/``'30m'``/``'90s'`` into seconds."""
    raw = str(text).strip().lower()
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    if raw.endswith(tuple(units)) and raw[:-1].replace(".", "", 1).isdigit():
        return float(raw[:-1]) * units[raw[-1]]
    if raw.isdigit():
        return float(raw)
    raise TreeError(f"Invalid duration: {text!r} (use e.g. 7d, 12h, 30m)")


def _is_reparse(st: os.stat_result) -> bool:
    """True for symlinks and (on Windows) junctions / reparse points."""
    if stat.S_ISLNK(st.st_mode):
        return True
    if IS_WINDOWS:
        attrs = getattr(st, "st_file_attributes", 0)
        return bool(attrs & _FILE_ATTRIBUTE_REPARSE_POINT)
    return False


def system_roots() -> List[str]:
    """Return the mount points / drive letters of this machine."""
    roots: List[str] = []
    if IS_WINDOWS:
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            try:
                if os.path.exists(drive):
                    roots.append(drive)
            except OSError:
                continue
        return roots
    if IS_MACOS:
        volumes = Path("/Volumes")
        if volumes.is_dir():
            try:
                roots.extend(str(p) for p in sorted(volumes.iterdir()) if p.is_dir())
            except OSError:
                pass
    if not roots:
        roots.append("/")
    if IS_LINUX_FALLBACK():
        roots.extend(_linux_mounts())
    # de-duplicate while preserving order
    seen = set()
    unique = []
    for r in roots:
        if r not in seen:
            seen.add(r)
            unique.append(r)
    return unique


def IS_LINUX_FALLBACK() -> bool:  # noqa: N802 - kept explicit for readability
    return os.name == "posix" and not IS_MACOS


def _linux_mounts() -> List[str]:
    """Best-effort list of real mount points from /proc/mounts."""
    mounts: List[str] = []
    try:
        with open("/proc/mounts", "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) < 3:
                    continue
                target = parts[1]
                if target.startswith(("/", "/mnt", "/media", "/run/media")) is False:
                    continue
                if target in ("/", "/proc", "/sys", "/dev", "/dev/pts", "/run"):
                    continue
                mounts.append(target)
    except OSError:
        pass
    return mounts


def _glob_match(name: str, patterns: Sequence[str]) -> bool:
    import fnmatch

    return any(fnmatch.fnmatch(name, pat) for pat in patterns)


def _keep(node: "Node", opts: Options) -> bool:
    if not opts.include_hidden and node.is_hidden:
        return False
    if opts.dirs_only and not node.is_dir:
        return False
    if opts.files_only and node.is_dir:
        return False
    if opts.extensions and not node.is_dir:
        if node.ext not in opts.normalized_extensions():
            return False
    if opts.include and not _glob_match(node.name, opts.include):
        return False
    if opts.exclude and _glob_match(node.name, opts.exclude):
        return False
    if not node.is_dir:
        if opts.min_size is not None and node.size < opts.min_size:
            return False
        if opts.max_size is not None and node.size > opts.max_size:
            return False
        if opts.newer_than is not None and node.mtime < opts.newer_than:
            return False
        if opts.older_than is not None and node.mtime > opts.older_than:
            return False
    return True


def _sort_key(node: "Node", opts: Options):
    key_lower = node.name.lower()
    if opts.sort_by == "size":
        return (0 if (node.is_dir and opts.dirs_first) else 1, -node.size, key_lower)
    if opts.sort_by == "mtime":
        return (0 if (node.is_dir and opts.dirs_first) else 1, -node.mtime, key_lower)
    if opts.sort_by == "none":
        return (0, 0, "")
    if opts.dirs_first:
        return (0 if node.is_dir else 1, 0, key_lower)
    return (0, 0, key_lower)


def _is_reparse_path(path) -> bool:
    """
    True when ``path`` is a symlink / junction / reparse point.

    This has to be checked *before* calling ``os.scandir``: opening a
    junction resolves its target, and if that target is an offline network
    share the call blocks for minutes.
    """
    try:
        st = os.lstat(os.fspath(path))
    except OSError:
        return False
    return _is_reparse(st)


def _list_dir(path: Path, opts: Options, depth: int
              ) -> Tuple[List[Node], Optional[str], int]:
    """
    List one directory.

    Returns ``(nodes, error_message_or_None, hidden_count)``. ``hidden_count``
    is how many further entries were skipped because ``opts.max_children``
    was reached.
    """
    items: List[Node] = []
    # Never descend into a reparse point: it may resolve to an offline share.
    if not opts.follow_links and _is_reparse_path(path):
        return [], None, 0
    seen = 0
    hidden = 0
    try:
        with os.scandir(str(path)) as scanner:
            for entry in scanner:
                try:
                    st = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                is_link = _is_reparse(st)
                if is_link and not opts.follow_links:
                    continue
                is_dir = entry.is_dir(follow_symlinks=False)
                node = Node(
                    path=Path(entry.path),
                    name=entry.name,
                    is_dir=is_dir,
                    is_link=is_link,
                    size=st.st_size,
                    mtime=st.st_mtime,
                    mode=st.st_mode,
                    depth=depth,
                )
                if not _keep(node, opts):
                    continue
                seen += 1
                if opts.max_children and len(items) >= opts.max_children:
                    hidden += 1
                    continue
                items.append(node)
    except (OSError, PermissionError) as exc:
        return [], f"{type(exc).__name__}: {exc}", 0
    items.sort(key=lambda n: _sort_key(n, opts), reverse=opts.reverse)
    return items, None, hidden


# --------------------------------------------------------------------------- #
# Streaming walk (constant memory, emits as it scans)
# --------------------------------------------------------------------------- #


def iter_tree(root: str, opts: Optional[Options] = None) -> Iterator[Tuple[str, Node, Stats]]:
    """
    Walk ``root`` and yield ``(prefix, node, stats)`` triples.

    ``prefix`` is the already-rendered branch string (``'├── '`` etc.), so a
    caller can simply ``print(prefix + node.name)``. ``stats`` is a *live*
    object mutated during the walk - read it at the end for totals.
    """
    opts = opts or Options()
    stats = Stats()
    started = time.time()

    base = resolve(str(root))
    try:
        st = os.stat(str(base))
    except OSError as exc:
        raise TreeError(f"Cannot access {base}: {exc}") from exc

    root_node = Node(
        path=base,
        name=base.name or str(base),
        is_dir=os.path.isdir(str(base)),
        size=st.st_size,
        mtime=st.st_mtime,
        mode=st.st_mode,
        depth=0,
    )
    stats.scanned += 1
    if root_node.is_dir:
        stats.dirs += 1
    else:
        stats.files += 1
        stats.bytes += root_node.size
    yield "", root_node, stats

    if not root_node.is_dir:
        stats.elapsed = time.time() - started
        return

    max_depth = min(opts.max_depth, MAX_DEPTH_LIMIT)
    # Explicit stack: (path, depth, prefix, children, index)
    children, err, hidden = _list_dir(base, opts, depth=1)
    if hidden:
        root_node.error = f"+{hidden} more entries (max-children reached)"
    if err:
        root_node.error = err
        stats.errors += 1
    stack: List[Tuple[Path, int, str, List[Node], int]] = [
        (base, 1, "", children, 0)
    ]

    while stack:
        path, depth, prefix, items, idx = stack.pop()
        total = len(items)
        while idx < total:
            node = items[idx]
            idx += 1
            last = idx == total
            stats.scanned += 1
            if node.is_dir:
                stats.dirs += 1
            else:
                stats.files += 1
                stats.bytes += node.size

            yield prefix + ("└── " if last else "├── "), node, stats

            if opts.limit is not None and stats.scanned >= opts.limit:
                stats.truncated = True
                stats.elapsed = time.time() - started
                return

            if node.is_dir and depth < max_depth:
                stack.append((path, depth, prefix, items, idx))
                sub, sub_err, sub_hidden = _list_dir(node.path, opts, depth + 1)
                if sub_hidden:
                    node.error = f"+{sub_hidden} more entries (max-children reached)"
                if sub_err:
                    node.error = sub_err
                    stats.errors += 1
                stack.append(
                    (node.path, depth + 1,
                     prefix + ("    " if last else "│   "), sub, 0)
                )
                break
    stats.elapsed = time.time() - started


# --------------------------------------------------------------------------- #
# Materialised tree (needed for --du, JSON export, treemap)
# --------------------------------------------------------------------------- #


@dataclass
class TreeNode:
    """A materialised node used for aggregate computations."""

    node: Node
    children: List["TreeNode"] = field(default_factory=list)

    @property
    def path(self) -> Path:
        return self.node.path


def build_tree(root: str, opts: Optional[Options] = None,
               stats: Optional[Stats] = None) -> TreeNode:
    """Materialise the (filtered) tree under ``root`` in memory."""
    opts = opts or Options()
    stats = stats if stats is not None else Stats()
    started = time.time()
    base = resolve(str(root))

    try:
        st = os.stat(str(base))
    except OSError as exc:
        raise TreeError(f"Cannot access {base}: {exc}") from exc

    is_dir = os.path.isdir(str(base))
    root_node = Node(path=base, name=base.name or str(base), is_dir=is_dir,
                     size=st.st_size, mtime=st.st_mtime, mode=st.st_mode, depth=0)
    root_tree = TreeNode(root_node)
    stats.scanned += 1
    if is_dir:
        stats.dirs += 1
    else:
        stats.files += 1
        stats.bytes += root_node.size

    if not is_dir:
        stats.elapsed = time.time() - started
        return root_tree

    max_depth = min(opts.max_depth, MAX_DEPTH_LIMIT)
    stack: List[Tuple[TreeNode, int]] = [(root_tree, 0)]
    while stack:
        parent, depth = stack.pop()
        if depth >= max_depth:
            continue
        children, err, hidden = _list_dir(parent.node.path, opts, depth + 1)
        if hidden:
            parent.node.error = f"+{hidden} more entries (max-children reached)"
        if err:
            parent.node.error = err
            stats.errors += 1
        for child in children:
            stats.scanned += 1
            if child.is_dir:
                stats.dirs += 1
            else:
                stats.files += 1
                stats.bytes += child.size
            sub = TreeNode(child)
            parent.children.append(sub)
            if child.is_dir:
                stack.append((sub, depth + 1))
        if opts.limit is not None and stats.scanned >= opts.limit:
            stats.truncated = True
            break

    _aggregate(root_tree)
    stats.elapsed = time.time() - started
    return root_tree


def _aggregate(tree: TreeNode) -> Tuple[int, int, int]:
    """Bottom-up aggregation of size / file count / dir count."""
    node = tree.node
    if not node.is_dir:
        node.agg_size = node.size
        node.n_files = 1
        node.n_dirs = 0
        return node.agg_size, node.n_files, node.n_dirs
    size = 0
    files = 0
    dirs = 0
    for child in tree.children:
        c_size, c_files, c_dirs = _aggregate(child)
        size += c_size
        files += c_files
        dirs += c_dirs
        if child.node.is_dir:
            dirs += 1
    node.agg_size = size
    node.n_files = files
    node.n_dirs = dirs
    return size, files, dirs


def flatten(tree: TreeNode, max_depth: Optional[int] = None
            ) -> Iterator[Tuple[str, TreeNode]]:
    """Yield ``(prefix, TreeNode)`` from a materialised tree."""
    yield "", tree
    if not tree.children or max_depth == 0:
        return
    yield from _flatten_children(tree.children, "", 1, max_depth)


def _flatten_children(children: List[TreeNode], prefix: str, depth: int,
                      max_depth: Optional[int]):
    total = len(children)
    for i, child in enumerate(children):
        last = i == total - 1
        yield prefix + ("└── " if last else "├── "), child
        if child.children and (max_depth is None or depth < max_depth):
            yield from _flatten_children(
                child.children, prefix + ("    " if last else "│   "), depth + 1, max_depth)


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #


def format_node(node: Node, opts: Options, show_size: bool = False,
                show_time: bool = False, show_dirsize: bool = False,
                color: bool = True) -> str:
    """Render the label part of a tree line."""
    label = node.name
    if node.is_dir:
        label += os.sep
        if color:
            label = _paint(label, "\033[1;34m")
    elif node.is_link:
        if color:
            label = _paint(label, "\033[1;36m")
    else:
        if color:
            label = _paint(label, "\033[0m")

    bits = [label]
    if show_dirsize and node.is_dir and node.agg_size:
        bits.append(f"[{human_size(node.agg_size)}"
                    f"{f' / {node.n_files}f' if node.n_files else ''}]")
    elif show_size and not node.is_dir:
        bits.append(f"({human_size(node.size)})")
    if show_time and node.mtime:
        bits.append(human_time(node.mtime, "%Y-%m-%d %H:%M"))
    if node.error:
        bits.append(_paint(f"<{node.error}>", "\033[31m") if color else f"<{node.error}>")
    elif node.is_dir and node.error is None and node.n_dirs and show_dirsize:
        pass
    return " ".join(bits)


def _paint(text: str, code: str) -> str:
    if os.environ.get("NO_COLOR"):
        return text
    return f"{code}{text}\033[0m"


def render(root: str, opts: Optional[Options] = None, *,
           show_size: bool = True, show_time: bool = False,
           show_dirsize: bool = False, ascii_box: bool = False,
           color: bool = True, out=sys.stdout) -> Stats:
    """Stream a full tree to ``out``. Returns the collected :class:`Stats`."""
    opts = opts or Options()
    box = _ASCII_BOX if ascii_box else _UNICODE_BOX
    stats = Stats()

    if show_dirsize:
        tree = build_tree(root, opts, stats)
        for prefix, tnode in flatten(tree):
            line = prefix.replace("├── ", box["tee"]).replace("└── ", box["elbow"])
            line = line.replace("│   ", box["pipe"]).replace("    ", box["blank"])
            out.write(line + format_node(tnode.node, opts, show_size, show_time,
                                         show_dirsize, color) + "\n")
        return stats

    for prefix, node, live in iter_tree(root, opts):
        line = prefix.replace("├── ", box["tee"]).replace("└── ", box["elbow"])
        line = line.replace("│   ", box["pipe"]).replace("    ", box["blank"])
        out.write(line + format_node(node, opts, show_size, show_time,
                                     show_dirsize, color) + "\n")
        stats = live
    return stats


def to_text(root: str, opts: Optional[Options] = None, **kw) -> str:
    """Return the rendered tree as a string."""
    import io

    buf = io.StringIO()
    render(root, opts, out=buf, color=False, **kw)
    return buf.getvalue()


def to_dict(tree: TreeNode) -> Dict[str, object]:
    """Convert a materialised tree into a JSON-serialisable dict."""
    node = tree.node
    return {
        "name": node.name,
        "path": str(node.path),
        "type": "dir" if node.is_dir else ("link" if node.is_link else "file"),
        "size": node.size,
        "agg_size": node.agg_size,
        "files": node.n_files,
        "dirs": node.n_dirs,
        "mtime": node.mtime,
        "modified": human_time(node.mtime),
        "error": node.error,
        "children": [to_dict(c) for c in tree.children],
    }


def to_json(root: str, opts: Optional[Options] = None, indent: int = 2) -> str:
    tree = build_tree(root, opts)
    return json.dumps(to_dict(tree), ensure_ascii=False, indent=indent)


def dir_sizes(root: str, opts: Optional[Options] = None,
              top: int = 20) -> List[Tuple[Path, int, int]]:
    """Return the ``top`` largest directories as ``(path, size, file_count)``."""
    tree = build_tree(root, opts)
    rows: List[Tuple[Path, int, int]] = []

    def visit(t: TreeNode) -> None:
        if t.node.is_dir:
            rows.append((t.node.path, t.node.agg_size, t.node.n_files))
        for c in t.children:
            visit(c)

    visit(tree)
    rows.sort(key=lambda r: r[1], reverse=True)
    return rows[:top]


# --------------------------------------------------------------------------- #
# Command line
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="fileforge tree",
        description="Display a live file-system tree (no cache, streamed).",
    )
    p.add_argument("path", nargs="?", default=".",
                   help="root directory (default: current directory)")
    p.add_argument("-L", "--max-depth", type=int, default=3,
                   help="maximum depth to display (default: 3)")
    p.add_argument("-a", "--all", action="store_true", help="include hidden entries")
    p.add_argument("-d", "--dirs-only", action="store_true", help="directories only")
    p.add_argument("-f", "--files-only", action="store_true", help="files only")
    p.add_argument("--follow-links", action="store_true",
                   help="follow symlinks/junctions (can be slow or unsafe)")
    p.add_argument("--min-size", help="minimum file size, e.g. 10M")
    p.add_argument("--max-size", help="maximum file size, e.g. 1G")
    p.add_argument("--newer", help="only files modified within e.g. 7d")
    p.add_argument("--older", help="only files NOT modified within e.g. 30d")
    p.add_argument("--ext", action="append", default=[],
                   help="keep only this extension (repeatable)")
    p.add_argument("--include", action="append", default=[],
                   help="keep names matching this glob (repeatable)")
    p.add_argument("--exclude", action="append", default=[],
                   help="drop names matching this glob (repeatable)")
    p.add_argument("--sort", choices=["name", "size", "mtime", "none"], default="name")
    p.add_argument("--reverse", action="store_true", help="reverse the sort order")
    p.add_argument("--no-dirs-first", action="store_true",
                   help="do not group directories before files")
    p.add_argument("-n", "--limit", type=int, help="stop after N entries")
    p.add_argument("--max-children", type=int, default=0, metavar="N",
                   help="cap entries listed per directory (0 = unlimited)")
    p.add_argument("--no-size", action="store_true", help="hide file sizes")
    p.add_argument("--time", action="store_true", help="show modification time")
    p.add_argument("--du", action="store_true",
                   help="show aggregated directory sizes (reads whole subtree)")
    p.add_argument("--ascii", action="store_true", help="use ASCII branch characters")
    p.add_argument("--no-color", action="store_true", help="disable ANSI colors")
    p.add_argument("--stats", action="store_true", help="print a summary at the end")
    p.add_argument("--json", metavar="FILE", help="export the tree as JSON")
    p.add_argument("--out", metavar="FILE", help="write the tree text to a file")
    p.add_argument("--top-dirs", type=int, metavar="N",
                   help="print the N largest directories instead of a tree")
    return p


def options_from_args(args: argparse.Namespace) -> Options:
    now = time.time()
    return Options(
        max_depth=max(0, args.max_depth),
        include_hidden=args.all,
        dirs_only=args.dirs_only,
        files_only=args.files_only,
        follow_links=args.follow_links,
        min_size=parse_size(args.min_size) if args.min_size else None,
        max_size=parse_size(args.max_size) if args.max_size else None,
        extensions=tuple(args.ext or ()),
        include=tuple(args.include or ()),
        exclude=tuple(args.exclude or ()),
        sort_by=args.sort,
        reverse=args.reverse,
        dirs_first=not args.no_dirs_first,
        limit=args.limit,
        max_children=args.max_children if args.max_children > 0 else None,
        newer_than=(now - parse_duration(args.newer)) if args.newer else None,
        older_than=(now - parse_duration(args.older)) if args.older else None,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    opts = options_from_args(args)

    try:
        if args.top_dirs:
            rows = dir_sizes(args.path, opts, top=args.top_dirs)
            for path, size, files in rows:
                print(f"{human_size(size):>12}  {files:>8} files  {path}")
            return 0

        if args.json:
            Path(args.json).write_text(to_json(args.path, opts), encoding="utf-8")
            print(f"JSON tree written to {args.json}")

        if args.out:
            text = to_text(args.path, opts, show_size=not args.no_size,
                           show_time=args.time, show_dirsize=args.du,
                           ascii_box=args.ascii)
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"Tree written to {args.out}")
            return 0

        stats = render(
            args.path, opts,
            show_size=not args.no_size,
            show_time=args.time,
            show_dirsize=args.du,
            ascii_box=args.ascii,
            color=not args.no_color,
        )
        if args.stats:
            print(
                f"\n{stats.dirs} director{'y' if stats.dirs == 1 else 'ies'}, "
                f"{stats.files} file(s), {human_size(stats.bytes)} total, "
                f"{stats.errors} unreadable, {stats.elapsed:.2f}s"
                + (" [truncated]" if stats.truncated else "")
            )
        return 0
    except (TreeError, OSError) as exc:
        print(f"tree: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
