"""
fileforge.hashutil
==================

Checksums, integrity manifests and comparison helpers.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from . import utils
from .utils import PathError, iter_entries, resolve

MANIFEST_VERSION = 1


# --------------------------------------------------------------------------- #
# Single / multiple file hashing
# --------------------------------------------------------------------------- #

@dataclass
class HashResult:
    path: Path
    size: int
    digest: str
    algorithm: str


def hash_paths(paths: Sequence[str], algorithm: str = "sha256",
               recursive: bool = False) -> List[HashResult]:
    results: List[HashResult] = []
    for raw in paths:
        p = resolve(raw)
        if not p.exists():
            raise PathError(f"Path does not exist: {p}")
        files: Iterable[Path]
        if p.is_dir():
            if not recursive:
                raise PathError(f"Directory given without --recursive: {p}")
            files = [e.path for e in iter_entries(p, recursive=True)
                     if not e.is_dir]
        else:
            files = [p]
        for f in files:
            results.append(HashResult(
                path=f, size=f.stat().st_size,
                digest=utils.hash_file(f, algorithm), algorithm=algorithm))
    return results


def compare_hash(a: str, b: str, algorithm: str = "sha256") -> bool:
    pa, pb = resolve(a), resolve(b)
    utils.ensure_exists(pa)
    utils.ensure_exists(pb)
    return utils.hash_file(pa, algorithm) == utils.hash_file(pb, algorithm)


# --------------------------------------------------------------------------- #
# Manifest (checksum file) create / verify
# --------------------------------------------------------------------------- #

def create_manifest(root: str, algorithm: str = "sha256",
                    include_hidden: bool = False,
                    out: Optional[str] = None) -> Path:
    base = resolve(root)
    if not base.exists():
        raise PathError(f"Root does not exist: {base}")

    entries = []
    for e in iter_entries(base, recursive=True, include_hidden=include_hidden):
        if e.is_dir:
            continue
        entries.append({
            "path": e.rel.replace("\\", "/"),
            "size": e.size,
            "digest": utils.hash_file(e.path, algorithm),
        })

    manifest = {
        "tool": "fileforge",
        "version": MANIFEST_VERSION,
        "algorithm": algorithm,
        "root": str(base),
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "count": len(entries),
        "files": entries,
    }
    target = resolve(out) if out else base / f".fileforge-manifest-{algorithm}.json"
    utils.ensure_parent(target)
    target.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return target


@dataclass
class VerifyReport:
    checked: int = 0
    ok: int = 0
    modified: List[str] = None  # type: ignore[assignment]
    missing: List[str] = None   # type: ignore[assignment]
    extra: List[str] = None     # type: ignore[assignment]
    algorithm: str = "sha256"

    def __post_init__(self) -> None:
        self.modified = self.modified or []
        self.missing = self.missing or []
        self.extra = self.extra or []


def verify_manifest(manifest_path: str, detect_extra: bool = False) -> VerifyReport:
    mp = resolve(manifest_path)
    utils.ensure_exists(mp)
    data = json.loads(mp.read_text(encoding="utf-8"))
    root = Path(data.get("root", mp.parent))
    algorithm = data.get("algorithm", "sha256")
    report = VerifyReport(algorithm=algorithm)

    seen = set()
    for item in data.get("files", []):
        rel = item["path"]
        seen.add(rel.replace("\\", "/"))
        f = root / rel
        report.checked += 1
        if not f.exists():
            report.missing.append(rel)
            continue
        digest = utils.hash_file(f, algorithm)
        if digest == item["digest"]:
            report.ok += 1
        else:
            report.modified.append(rel)

    if detect_extra:
        for e in iter_entries(root, recursive=True, include_hidden=True):
            if e.is_dir:
                continue
            rel = e.rel.replace("\\", "/")
            if rel not in seen and not rel.startswith(".fileforge-manifest"):
                report.extra.append(rel)
    return report


# --------------------------------------------------------------------------- #
# Duplicate finder
# --------------------------------------------------------------------------- #

@dataclass
class DuplicateGroup:
    digest: str
    size: int
    files: List[Path]

    @property
    def wasted(self) -> int:
        return self.size * (len(self.files) - 1)


def find_duplicates(root: str, algorithm: str = "sha256",
                    min_size: int = 1, include_hidden: bool = False,
                    same_size_filter: bool = True) -> List[DuplicateGroup]:
    """
    Find duplicate files under `root`.

    Strategy: group by size first (cheap), then hash only colliding files.
    """
    base = resolve(root)
    if not base.exists():
        raise PathError(f"Root does not exist: {base}")

    by_size: Dict[int, List[Path]] = {}
    for e in iter_entries(base, recursive=True, include_hidden=include_hidden):
        if e.is_dir or e.is_link or e.size < min_size:
            continue
        by_size.setdefault(e.size, []).append(e.path)

    groups: List[DuplicateGroup] = []
    for size, files in by_size.items():
        if same_size_filter and len(files) < 2:
            continue
        by_hash: Dict[str, List[Path]] = {}
        for f in files:
            by_hash.setdefault(utils.hash_file(f, algorithm), []).append(f)
        for digest, dups in by_hash.items():
            if len(dups) > 1:
                groups.append(DuplicateGroup(digest, size, dups))

    groups.sort(key=lambda g: g.wasted, reverse=True)
    return groups


# --------------------------------------------------------------------------- #
# File comparison (diff-lite)
# --------------------------------------------------------------------------- #

@dataclass
class CompareResult:
    identical: bool
    same_size: bool
    size_a: int
    size_b: int
    digest_a: str
    digest_b: str
    first_diff: Optional[int] = None


def compare_files(a: str, b: str, algorithm: str = "sha256") -> CompareResult:
    pa, pb = resolve(a), resolve(b)
    utils.ensure_exists(pa)
    utils.ensure_exists(pb)
    sa, sb = pa.stat().st_size, pb.stat().st_size
    da = utils.hash_file(pa, algorithm)
    db = utils.hash_file(pb, algorithm)
    first_diff = None
    if da != db:
        with pa.open("rb") as fa, pb.open("rb") as fb:
            offset = 0
            while True:
                ca = fa.read(1 << 16)
                cb = fb.read(1 << 16)
                if ca != cb:
                    for i in range(min(len(ca), len(cb))):
                        if ca[i] != cb[i]:
                            first_diff = offset + i
                            break
                    if first_diff is None:
                        first_diff = offset + min(len(ca), len(cb))
                    break
                if not ca:
                    break
                offset += len(ca)
    return CompareResult(da == db, sa == sb, sa, sb, da, db, first_diff)
