"""
fileforge.core
==============

Core file-system operations shared by the CLI and the interactive shell.

Every function accepts plain strings or :class:`pathlib.Path` objects and
returns structured data so the CLI layer can format it. No printing happens
here (except where explicitly noted) which keeps the module reusable.
"""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

from . import utils
from .utils import Entry, PathError, ensure_exists, ensure_parent, iter_entries, resolve, unique_path


# --------------------------------------------------------------------------- #
# Read / write
# --------------------------------------------------------------------------- #

def read_text(path: str, encoding: str = "utf-8", errors: str = "strict") -> str:
    p = ensure_exists(resolve(path))
    if p.is_dir():
        raise PathError(f"Not a file: {p}")
    return p.read_text(encoding=encoding, errors=errors)


def read_bytes(path: str) -> bytes:
    p = ensure_exists(resolve(path))
    return p.read_bytes()


def write_text(path: str, content: str, encoding: str = "utf-8",
               append: bool = False, newline: bool = False) -> int:
    """Write (or append) text. Returns number of bytes written."""
    p = ensure_parent(resolve(path))
    mode = "a" if append else "w"
    with p.open(mode, encoding=encoding, newline="\n" if newline else None) as fh:
        n = fh.write(content)
    return len(content.encode(encoding))


def write_bytes(path: str, data: bytes, append: bool = False) -> int:
    p = ensure_parent(resolve(path))
    mode = "ab" if append else "wb"
    with p.open(mode) as fh:
        fh.write(data)
    return len(data)


def touch(path: str, create: bool = True) -> Path:
    """Create an empty file if missing and bump its mtime."""
    p = resolve(path)
    if create:
        ensure_parent(p)
    if not p.exists():
        p.touch()
    else:
        os.utime(p, None)
    return p


def truncate(path: str, size: int = 0) -> int:
    p = ensure_exists(resolve(path))
    with p.open("r+b") as fh:
        fh.truncate(size)
    return size


# --------------------------------------------------------------------------- #
# Create / remove
# --------------------------------------------------------------------------- #

def make_dir(path: str, parents: bool = True, exist_ok: bool = True) -> Path:
    p = resolve(path)
    p.mkdir(parents=parents, exist_ok=exist_ok)
    return p


def remove(path: str, recursive: bool = False, force: bool = False) -> List[str]:
    """Remove a file or directory. Returns the list of removed paths."""
    p = resolve(path)
    removed: List[str] = []
    if not p.exists() and not p.is_symlink():
        if force:
            return removed
        raise PathError(f"Path does not exist: {p}")

    if p.is_dir() and not p.is_symlink():
        if recursive:
            for e in iter_entries(p, recursive=True, include_hidden=True):
                removed.append(str(e.path))
            shutil.rmtree(p)
            removed.append(str(p))
        else:
            try:
                p.rmdir()
                removed.append(str(p))
            except OSError as exc:
                raise PathError(
                    f"Directory not empty (use --recursive): {p}"
                ) from exc
    else:
        p.unlink()
        removed.append(str(p))
    return removed


# --------------------------------------------------------------------------- #
# Copy / move / rename
# --------------------------------------------------------------------------- #

def copy(path: str, dest: str, overwrite: bool = False,
         recursive: bool = True, preserve: bool = True) -> Path:
    src = ensure_exists(resolve(path))
    dst = resolve(dest)

    # If dest is an existing directory, copy *into* it.
    if dst.is_dir():
        dst = dst / src.name

    if dst.exists():
        if not overwrite:
            raise PathError(f"Destination exists (use --overwrite): {dst}")
        if dst.is_dir() and not dst.is_symlink():
            shutil.rmtree(dst)
        else:
            dst.unlink()

    ensure_parent(dst)
    if src.is_dir():
        if not recursive:
            raise PathError(f"Source is a directory (use --recursive): {src}")
        shutil.copytree(src, dst, symlinks=not preserve)
    else:
        shutil.copy2(src, dst) if preserve else shutil.copy(src, dst)
    return dst


def move(path: str, dest: str, overwrite: bool = False) -> Path:
    src = ensure_exists(resolve(path))
    dst = resolve(dest)
    if dst.is_dir():
        dst = dst / src.name
    if dst.exists() and not overwrite:
        raise PathError(f"Destination exists (use --overwrite): {dst}")
    ensure_parent(dst)
    shutil.move(str(src), str(dst))
    return dst


def rename(path: str, new_name: str) -> Path:
    src = ensure_exists(resolve(path))
    dst = src.parent / new_name
    if dst.exists():
        raise PathError(f"Target already exists: {dst}")
    src.rename(dst)
    return dst


@dataclass
class RenameResult:
    changed: int
    skipped: int
    mapping: List[tuple]


def batch_rename(paths: Sequence[str], pattern: str, replacement: str,
                 use_regex: bool = False, dry_run: bool = False,
                 ignore_case: bool = False) -> RenameResult:
    """
    Rename a batch of files.

    - Plain mode: substring replace (`pattern` -> `replacement`).
    - Regex mode: `pattern` is a python regex, `replacement` supports \\1 groups.
    """
    import re

    mapping: List[tuple] = []
    changed = skipped = 0
    for raw in paths:
        p = resolve(raw)
        if not p.exists():
            skipped += 1
            continue
        old = p.name
        if use_regex:
            flags = re.IGNORECASE if ignore_case else 0
            try:
                new = re.sub(pattern, replacement, old, flags=flags)
            except re.error as exc:
                raise PathError(f"Invalid regex: {exc}") from exc
        else:
            if ignore_case:
                import re as _re

                new = _re.sub(pattern, replacement, old, flags=_re.IGNORECASE)
            else:
                new = old.replace(pattern, replacement)

        if new == old or not new:
            skipped += 1
            continue
        target = p.parent / new
        if target.exists():
            target = unique_path(target)
        mapping.append((str(p), str(target)))
        if not dry_run:
            p.rename(target)
        changed += 1
    return RenameResult(changed=changed, skipped=skipped, mapping=mapping)


# --------------------------------------------------------------------------- #
# List / tree
# --------------------------------------------------------------------------- #

def list_dir(path: str = ".", show_hidden: bool = False,
             long: bool = False, sort: str = "name") -> List[Entry]:
    p = resolve(path)
    if not p.exists():
        raise PathError(f"Path does not exist: {p}")
    if p.is_file():
        st = p.stat()
        return [Entry(p, p.name, False, p.is_symlink(), st.st_size, st.st_mtime,
                      st.st_mode, p.suffix.lower())]
    entries = list(iter_entries(p, recursive=False, include_hidden=show_hidden))
    key = {
        "name": lambda e: e.path.name.lower(),
        "size": lambda e: e.size,
        "time": lambda e: e.mtime,
        "ext": lambda e: e.ext,
    }.get(sort, lambda e: e.path.name.lower())
    entries.sort(key=lambda e: (not e.is_dir, key(e)))
    return entries


@dataclass
class TreeNode:
    name: str
    is_dir: bool
    size: int
    children: List["TreeNode"]
    count: int = 0
    total_size: int = 0


def build_tree(path: str, max_depth: Optional[int] = None,
               include_hidden: bool = False) -> TreeNode:
    root = resolve(path)
    if not root.exists():
        raise PathError(f"Path does not exist: {root}")

    def _walk(p: Path, depth: int) -> TreeNode:
        st = p.stat()
        node = TreeNode(p.name or str(p), p.is_dir(), st.st_size, [])
        if not p.is_dir():
            node.count = 1
            node.total_size = st.st_size
            return node
        node.count = 0
        node.total_size = 0
        if max_depth is not None and depth >= max_depth:
            return node
        try:
            children = sorted(
                p.iterdir(),
                key=lambda c: (not c.is_dir(), c.name.lower()),
            )
        except OSError:
            return node
        for child in children:
            if not include_hidden and child.name.startswith("."):
                continue
            try:
                sub = _walk(child, depth + 1)
            except OSError:
                continue
            node.children.append(sub)
            node.count += sub.count
            node.total_size += sub.total_size
        if node.count == 0:
            node.count = 1
            node.total_size = node.size
        return node

    return _walk(root, 0)


def render_tree(node: TreeNode, show_size: bool = True,
                prefix: str = "", is_last: bool = True, is_root: bool = True) -> List[str]:
    """Return a list of lines (ASCII box drawing) for a tree node."""
    lines: List[str] = []
    if is_root:
        label = node.name
    else:
        connector = "`-- " if is_last else "|-- "
        label = connector + node.name
    if show_size:
        if node.is_dir:
            label += f"  ({utils.human_size(node.total_size)}, {node.count} items)"
        else:
            label += f"  ({utils.human_size(node.size)})"
    lines.append(prefix + label if not is_root else label)

    if is_root:
        child_prefix = ""
    else:
        child_prefix = prefix + ("    " if is_last else "|   ")
    for i, child in enumerate(node.children):
        last = i == len(node.children) - 1
        lines.extend(render_tree(child, show_size, child_prefix, last, is_root=False))
    return lines


# --------------------------------------------------------------------------- #
# Stat / info
# --------------------------------------------------------------------------- #

def stat_info(path: str) -> dict:
    p = ensure_exists(resolve(path))
    st = p.lstat()
    info = {
        "path": str(p),
        "name": p.name,
        "type": utils.role_of(p),
        "size_bytes": st.st_size,
        "size_human": utils.human_size(st.st_size),
        "mode": utils.mode_string(st.st_mode),
        "mode_octal": utils.octal_mode(st.st_mode),
        "uid": getattr(st, "st_uid", None),
        "gid": getattr(st, "st_gid", None),
        "atime": utils.human_time(st.st_atime),
        "mtime": utils.human_time(st.st_mtime),
        "ctime": utils.human_time(st.st_ctime),
        "inode": getattr(st, "st_ino", None),
        "nlink": getattr(st, "st_nlink", None),
        "is_symlink": p.is_symlink(),
    }
    if p.is_symlink():
        try:
            info["symlink_target"] = str(os.readlink(p))
        except OSError:
            info["symlink_target"] = "?"
    if p.is_dir():
        files = dirs = 0
        total = 0
        for e in iter_entries(p, recursive=True, include_hidden=True):
            if e.is_dir:
                dirs += 1
            else:
                files += 1
                total += e.size
        info.update({
            "contains_files": files,
            "contains_dirs": dirs,
            "contains_bytes": total,
            "contains_human": utils.human_size(total),
        })
    elif p.is_file():
        info["mime"] = utils.sniff_type(p)
        info["is_binary"] = utils.is_binary(p)
    return info


# --------------------------------------------------------------------------- #
# Timestamps
# --------------------------------------------------------------------------- #

def set_times(path: str, atime: Optional[float] = None,
              mtime: Optional[float] = None) -> Path:
    p = ensure_exists(resolve(path))
    now = time.time()
    os.utime(p, (atime if atime is not None else now,
                 mtime if mtime is not None else now))
    return p


# --------------------------------------------------------------------------- #
# Symlinks
# --------------------------------------------------------------------------- #

def make_symlink(target: str, link_path: str) -> Path:
    link = resolve(link_path)
    ensure_parent(link)
    if link.exists() or link.is_symlink():
        raise PathError(f"Link path already exists: {link}")
    os.symlink(target, link,
               target_is_directory=resolve(target).is_dir())
    return link


def read_symlink(path: str) -> str:
    p = ensure_exists(resolve(path))
    if not p.is_symlink():
        raise PathError(f"Not a symbolic link: {p}")
    return str(os.readlink(p))


# --------------------------------------------------------------------------- #
# Line / text utilities
# --------------------------------------------------------------------------- #

@dataclass
class FileStats:
    lines: int
    words: int
    chars: int
    bytes: int


def word_count(path: str, encoding: str = "utf-8") -> FileStats:
    p = ensure_exists(resolve(path))
    raw = p.read_bytes()
    text = raw.decode(encoding, errors="replace")
    return FileStats(
        lines=text.count("\n") + (1 if text and not text.endswith("\n") else 0),
        words=len(text.split()),
        chars=len(text),
        bytes=len(raw),
    )


def replace_in_file(path: str, old: str, new: str, regex: bool = False,
                    ignore_case: bool = False, dry_run: bool = False,
                    encoding: str = "utf-8") -> int:
    """Replace occurrences in a text file. Returns number of replacements."""
    import re

    p = ensure_exists(resolve(path))
    text = p.read_text(encoding=encoding, errors="replace")
    if regex:
        flags = re.MULTILINE | (re.IGNORECASE if ignore_case else 0)
        new_text, count = re.subn(old, new, text, flags=flags)
    else:
        if ignore_case:
            pattern = re.compile(re.escape(old), re.IGNORECASE)
            new_text, count = pattern.subn(new, text)
        else:
            count = text.count(old)
            new_text = text.replace(old, new)
    if count and not dry_run:
        p.write_text(new_text, encoding=encoding)
    return count


def convert_encoding(path: str, to_encoding: str, from_encoding: str = "utf-8",
                     in_place: bool = True, out_path: Optional[str] = None) -> Path:
    """Transcode a text file between encodings."""
    src = ensure_exists(resolve(path))
    text = src.read_text(encoding=from_encoding, errors="replace")
    if out_path:
        dst = ensure_parent(resolve(out_path))
    elif in_place:
        dst = src
    else:
        dst = src.with_suffix(src.suffix + f".{to_encoding}")
    dst.write_text(text, encoding=to_encoding)
    return dst
