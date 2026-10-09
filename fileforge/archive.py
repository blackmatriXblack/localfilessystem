"""
fileforge.archive
=================

Archive creation / extraction (zip, tar, tar.gz, tar.bz2, tar.xz), single
file gzip compression, file splitting and merging.
"""

from __future__ import annotations

import gzip
import os
import shutil
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

from . import utils
from .utils import PathError, ensure_parent, iter_entries, resolve

# --------------------------------------------------------------------------- #
# Create archive
# --------------------------------------------------------------------------- #

_ZIP_EXTS = {".zip", ".jar", ".whl", ".egg", ".apk", ".cbz"}
_TAR_EXTS = {".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz"}


def detect_archive_format(path: Path) -> str:
    name = path.name.lower()
    for ext in _TAR_EXTS:
        if name.endswith(ext):
            return "tar"
    if path.suffix.lower() in _ZIP_EXTS:
        return "zip"
    if name.endswith(".gz"):
        return "gz"
    return "zip"  # sensible default


def _tar_mode(path: Path) -> str:
    name = path.name.lower()
    if name.endswith((".tar.gz", ".tgz")):
        return "w:gz"
    if name.endswith((".tar.bz2", ".tbz2")):
        return "w:bz2"
    if name.endswith((".tar.xz", ".txz")):
        return "w:xz"
    return "w"


def _tar_read_mode(path: Path) -> str:
    name = path.name.lower()
    if name.endswith((".tar.gz", ".tgz")):
        return "r:gz"
    if name.endswith((".tar.bz2", ".tbz2")):
        return "r:bz2"
    if name.endswith((".tar.xz", ".txz")):
        return "r:xz"
    return "r:*"


def create_archive(sources: Sequence[str], output: str, fmt: Optional[str] = None,
                   base_dir: Optional[str] = None) -> Path:
    """Create an archive from a list of files / directories."""
    out = resolve(output)
    ensure_parent(out)
    fmt = fmt or detect_archive_format(out)
    paths = [resolve(s) for s in sources]
    for p in paths:
        if not p.exists():
            raise PathError(f"Source does not exist: {p}")

    if fmt == "zip":
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in paths:
                _zip_add(zf, p, base_dir)
    elif fmt == "tar":
        mode = _tar_mode(out)
        with tarfile.open(out, mode) as tf:
            for p in paths:
                arcname = _rel_arcname(p, base_dir)
                tf.add(p, arcname=arcname, recursive=True)
    else:
        raise PathError(f"Unsupported archive output format: {fmt}")
    return out


def _rel_arcname(p: Path, base_dir: Optional[str]) -> str:
    if base_dir:
        try:
            return str(p.relative_to(resolve(base_dir)))
        except ValueError:
            return p.name
    return p.name


def _zip_add(zf: zipfile.ZipFile, p: Path, base_dir: Optional[str]) -> None:
    if p.is_dir():
        prefix = _rel_arcname(p, base_dir).replace("\\", "/")
        entries = list(iter_entries(p, recursive=True, include_hidden=True))
        for e in entries:
            if e.is_dir:
                continue
            arc = f"{prefix}/{e.rel}".replace("\\", "/")
            zf.write(e.path, arc)
        if not any(not e.is_dir for e in entries):
            zf.writestr(prefix + "/", "")
    else:
        zf.write(p, _rel_arcname(p, base_dir))


# --------------------------------------------------------------------------- #
# Extract archive
# --------------------------------------------------------------------------- #

def _safe_extract_member(base: Path, name: str) -> Path:
    """Guard against path traversal (zip-slip)."""
    target = (base / name).resolve()
    base_res = base.resolve()
    if not str(target).startswith(str(base_res)):
        raise PathError(f"Unsafe archive member path: {name}")
    return target


def extract_archive(archive: str, dest: str = ".", members: Optional[Sequence[str]] = None) -> Path:
    arc = resolve(archive)
    utils.ensure_exists(arc)
    base = resolve(dest)
    base.mkdir(parents=True, exist_ok=True)

    fmt = detect_archive_format(arc)
    if fmt == "zip":
        with zipfile.ZipFile(arc) as zf:
            for info in zf.infolist():
                if members and info.filename not in members:
                    continue
                _safe_extract_member(base, info.filename)
            zf.extractall(base)
    elif fmt == "tar":
        with tarfile.open(arc, _tar_read_mode(arc)) as tf:
            safe_members = []
            for m in tf.getmembers():
                if members and m.name not in members:
                    continue
                _safe_extract_member(base, m.name)
                if m.issym() or m.islnk():
                    continue  # skip links for safety
                safe_members.append(m)
            tf.extractall(base, members=safe_members)
    elif fmt == "gz":
        out = base / arc.stem
        with gzip.open(arc, "rb") as src, out.open("wb") as dst:
            shutil.copyfileobj(src, dst)
    else:
        raise PathError(f"Unsupported archive: {arc}")
    return base


def list_archive(archive: str) -> List[dict]:
    arc = resolve(archive)
    utils.ensure_exists(arc)
    fmt = detect_archive_format(arc)
    items: List[dict] = []
    if fmt == "zip":
        with zipfile.ZipFile(arc) as zf:
            for info in zf.infolist():
                items.append({
                    "name": info.filename,
                    "size": info.file_size,
                    "compressed": info.compress_size,
                    "date": "%04d-%02d-%02d %02d:%02d"
                            % info.date_time[:5],
                    "is_dir": info.is_dir(),
                })
    elif fmt == "tar":
        with tarfile.open(arc, _tar_read_mode(arc)) as tf:
            for m in tf.getmembers():
                items.append({
                    "name": m.name,
                    "size": m.size,
                    "compressed": None,
                    "date": utils.human_time(m.mtime),
                    "is_dir": m.isdir(),
                })
    return items


# --------------------------------------------------------------------------- #
# Gzip single file
# --------------------------------------------------------------------------- #

def gzip_file(path: str, keep: bool = False) -> Path:
    src = resolve(path)
    utils.ensure_exists(src)
    out = src.with_name(src.name + ".gz")
    with src.open("rb") as fi, gzip.open(out, "wb", compresslevel=6) as fo:
        shutil.copyfileobj(fi, fo)
    if not keep:
        src.unlink()
    return out


def gunzip_file(path: str, keep: bool = False) -> Path:
    src = resolve(path)
    utils.ensure_exists(src)
    out = src.with_suffix("") if src.suffix == ".gz" else src.with_name(src.name + ".out")
    with gzip.open(src, "rb") as fi, out.open("wb") as fo:
        shutil.copyfileobj(fi, fo)
    if not keep:
        src.unlink()
    return out


# --------------------------------------------------------------------------- #
# Split / merge
# --------------------------------------------------------------------------- #

def split_file(path: str, part_size: int, out_dir: Optional[str] = None) -> List[Path]:
    """Split `path` into parts of `part_size` bytes. Returns part paths."""
    src = resolve(path)
    utils.ensure_exists(src)
    if part_size <= 0:
        raise PathError("Part size must be > 0")
    dest = ensure_parent(resolve(out_dir)) if out_dir else src.parent
    dest.mkdir(parents=True, exist_ok=True)

    parts: List[Path] = []
    total = src.stat().st_size
    nparts = (total + part_size - 1) // part_size or 1
    width = len(str(nparts))
    with src.open("rb") as fh:
        index = 1
        while True:
            block = fh.read(part_size)
            if not block:
                break
            part = dest / f"{src.name}.part{index:0{width}d}"
            part.write_bytes(block)
            parts.append(part)
            index += 1
    return parts


def merge_files(parts: Sequence[str], output: str) -> Path:
    """Concatenate parts (in given order) back into a single file."""
    out = ensure_parent(resolve(output))
    with out.open("wb") as fo:
        for raw in parts:
            p = resolve(raw)
            utils.ensure_exists(p)
            with p.open("rb") as fi:
                shutil.copyfileobj(fi, fo)
    return out


# --------------------------------------------------------------------------- #
# Incremental directory mirror (sync-lite)
# --------------------------------------------------------------------------- #

@dataclass
class SyncReport:
    copied: int = 0
    skipped: int = 0
    updated: int = 0
    removed: int = 0


def sync_tree(src: str, dst: str, delete: bool = False,
              dry_run: bool = False) -> SyncReport:
    """
    Mirror `src` into `dst`, copying only new / changed files.
    Compares by size then mtime (fast), falling back to nothing else.
    If `delete` is True, files in `dst` missing from `src` are removed.
    """
    s = resolve(src)
    d = resolve(dst)
    if not s.is_dir():
        raise PathError(f"Source is not a directory: {s}")
    d.mkdir(parents=True, exist_ok=True)
    report = SyncReport()

    src_files = {e.rel: e for e in iter_entries(s, recursive=True, include_hidden=True)
                 if not e.is_dir}
    for rel, e in src_files.items():
        target = d / rel
        if not target.exists():
            report.copied += 1
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(e.path, target)
        else:
            st = target.stat()
            if st.st_size == e.size and int(st.st_mtime) == int(e.mtime):
                report.skipped += 1
            else:
                report.updated += 1
                if not dry_run:
                    shutil.copy2(e.path, target)

    if delete:
        for e in iter_entries(d, recursive=True, include_hidden=True):
            if e.is_dir:
                continue
            if e.rel not in src_files:
                report.removed += 1
                if not dry_run:
                    e.path.unlink()
    return report
