#!/usr/bin/env python3
"""
fileforge.filekit
=================

A toolbox for **individual files** (as opposed to ``computerkit``, which
looks at the whole machine, and ``cli``, which manages paths).

Every command is pure standard library, cross-platform and safe by default:
nothing is written unless you pass ``--apply`` / ``-o``.

Commands
--------
    filemeta      complete metadata report for one path
    filediff      line diff of two files, or inventory diff of two dirs
    filesanitize  find (and optionally fix) illegal / reserved file names
    filenorm      normalise names (Unicode NFC, case, spaces)
    fileextract   pull URLs / e-mails / IPv4 addresses out of a file
    fileencode    base64 / hex / url-encode a file
    filedecode    base64 / hex / url-decode a file
    filetrim      strip blank lines, trailing whitespace, BOM, CRLF
    filesort      sort / de-duplicate the lines of a text file
    filebackup    timestamped copy (``name.bak-20260101-120000``)
    filepreview   preview any file: text head or binary hex
    filehex       hex dump with offset, length and width control

Aliases: ``fmeta``, ``fdiff``, ``fsanitize``, ``fnorm``, ``fextract``,
``fenc``, ``fdec``, ``ftrim``, ``fsort``, ``fbackup``, ``fpreview``,
``fhex``.

Command line
------------
    fileforge filemeta README.md --json
    fileforge fdiff old.txt new.txt --unified
    fileforge fsanitize "bad:name?.txt" --apply
    fileforge fextract notes.txt --all --unique
    fileforge fhex data.bin --length 256
"""

from __future__ import annotations

import argparse
import base64
import binascii
import difflib
import fnmatch
import os
import re
import shutil
import stat
import sys
import time
import unicodedata
from pathlib import Path
from typing import Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

try:  # package import
    from .utils import (human_size, human_time, is_binary, mode_string,
                        sniff_type, hash_file, resolve)
except ImportError:  # pragma: no cover - direct script execution fallback
    from utils import (human_size, human_time, is_binary, mode_string,  # type: ignore
                       sniff_type, hash_file, resolve)  # type: ignore

APP = "fileforge"

#: Characters Windows refuses in a file name.
WINDOWS_ILLEGAL = set('<>:"/\\|?*')
#: Names Windows reserves regardless of extension.
WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *{f"COM{i}" for i in range(1, 10)},
    *{f"LPT{i}" for i in range(1, 10)},
}

URL_RE = re.compile(r"https?://[^\s<>\"')\]]+|ftp://[^\s<>\"')\]]+", re.I)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


# --------------------------------------------------------------------------- #
# Command specification: (group, [(name, help), ...])
# --------------------------------------------------------------------------- #
SPEC: List[Tuple[str, List[Tuple[str, str]]]] = [
    ("Files - inspect", [
        ("filemeta",    "Complete metadata report for one path"),
        ("filepreview", "Preview any file: text head or binary hex"),
        ("filehex",     "Hex dump with offset / length / width control"),
    ]),
    ("Files - compare & fix names", [
        ("filediff",     "Line diff of two files, or inventory diff of two dirs"),
        ("filesanitize", "Find (and optionally fix) illegal / reserved names"),
        ("filenorm",     "Normalise names (Unicode NFC, case, spaces)"),
    ]),
    ("Files - content tools", [
        ("fileextract", "Pull URLs / e-mails / IPv4 addresses out of a file"),
        ("fileencode",  "base64 / hex / url-encode a file"),
        ("filedecode",  "base64 / hex / url-decode a file"),
    ]),
    ("Files - housekeeping", [
        ("filetrim",   "Strip blank lines, trailing whitespace, BOM, CRLF"),
        ("filesort",   "Sort / de-duplicate the lines of a text file"),
        ("filebackup", "Timestamped copy (name.bak-20260101-120000)"),
    ]),
]

ALIASES: Dict[str, str] = {
    "fmeta": "filemeta",
    "fstat": "filemeta",
    "fpreview": "filepreview",
    "fcat": "filepreview",
    "fhex": "filehex",
    "hexdump": "filehex",
    "fdiff": "filediff",
    "fsanitize": "filesanitize",
    "fnorm": "filenorm",
    "fextract": "fileextract",
    "fenc": "fileencode",
    "fencode": "fileencode",
    "fdec": "filedecode",
    "fdecode": "filedecode",
    "ftrim": "filetrim",
    "fsort": "filesort",
    "fbackup": "filebackup",
}


def command_names() -> List[str]:
    return [name for _group, entries in SPEC for name, _help in entries]


# --------------------------------------------------------------------------- #
# 1. filemeta
# --------------------------------------------------------------------------- #
def _parser_meta() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge filemeta",
                                description="Complete metadata for one path.")
    p.add_argument("path", help="file or directory")
    p.add_argument("--hash", dest="algorithm", default="",
                   help="also checksum with md5/sha1/sha256/blake2b")
    p.add_argument("--json", action="store_true")
    p.add_argument("--out", metavar="FILE")
    return p


def file_meta(path: str, algorithm: str = "") -> Dict[str, object]:
    """Return a metadata dictionary for ``path``."""
    p = Path(path).expanduser()
    try:
        st = os.stat(p)            # follows symlinks
        lstat = os.lstat(p)
    except OSError as exc:
        return {"path": str(p), "exists": False, "error": str(exc)}

    is_link = stat.S_ISLNK(lstat.st_mode)
    info: Dict[str, object] = {
        "path": str(p),
        "abs": str(p.resolve()),
        "exists": True,
        "name": p.name,
        "type": "directory" if stat.S_ISDIR(st.st_mode) else (
            "symlink" if is_link else "file"),
        "size": st.st_size,
        "size_human": human_size(st.st_size),
        "mode": oct(st.st_mode),
        "mode_string": mode_string(st.st_mode),
        "nlink": getattr(st, "st_nlink", 1),
        "inode": getattr(st, "st_ino", 0),
        "device": getattr(st, "st_dev", 0),
        "atime": st.st_atime,
        "atime_text": human_time(st.st_atime),
        "mtime": st.st_mtime,
        "mtime_text": human_time(st.st_mtime),
        "ctime": st.st_ctime,
        "ctime_text": human_time(st.st_ctime),
        "age_days": round((time.time() - st.st_mtime) / 86400.0, 3),
        "ext": os.path.splitext(p.name)[1].lower(),
        "hidden": p.name.startswith("."),
        "symlink": is_link,
    }
    if hasattr(st, "st_uid"):       # POSIX only
        info["uid"] = st.st_uid
        info["gid"] = st.st_gid
    if is_link:
        try:
            info["link_target"] = str(os.readlink(p))
        except OSError:
            info["link_target"] = None
    if stat.S_ISREG(st.st_mode):
        try:
            info["mime"] = sniff_type(p)
            info["binary"] = is_binary(p)
        except OSError:
            info["mime"] = "unknown"
            info["binary"] = None
        if algorithm:
            try:
                info["hash"] = hash_file(p, algorithm)
                info["algorithm"] = algorithm
            except OSError as exc:
                info["hash_error"] = str(exc)
    else:
        try:
            info["entries"] = len(list(os.scandir(p)))
        except OSError:
            info["entries"] = None
    return info


def cmd_meta(args: argparse.Namespace) -> int:
    info = file_meta(args.path, args.algorithm)
    text = _json_or_report(info, args)
    if text is not None:
        return 0
    if not info.get("exists"):
        print(f"filemeta: {info.get('error')}", file=sys.stderr)
        return 1
    order = ["path", "abs", "type", "size_human", "size", "mode_string",
             "mode", "nlink", "inode", "device", "uid", "gid",
             "mtime_text", "atime_text", "ctime_text", "age_days",
             "ext", "hidden", "symlink", "link_target", "mime", "binary",
             "hash", "entries"]
    for key in order:
        if key in info:
            print(f"  {key:<12} {info[key]}")
    return 0


# --------------------------------------------------------------------------- #
# 2. filediff
# --------------------------------------------------------------------------- #
def _parser_diff() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge filediff",
                                description="Diff two files or two directories.")
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("--unified", action="store_true",
                   help="unified diff with 3 lines of context")
    p.add_argument("--context", type=int, default=3)
    p.add_argument("--ignore-case", action="store_true")
    p.add_argument("--ignore-space", action="store_true")
    p.add_argument("--ignore-blank", action="store_true")
    p.add_argument("--max-lines", type=int, default=200)
    p.add_argument("--json", action="store_true")
    p.add_argument("--out", metavar="FILE")
    return p


def _read_lines(path: Path, ignore_case: bool, ignore_space: bool,
                ignore_blank: bool) -> List[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if ignore_blank:
        lines = [ln for ln in lines if ln.strip()]
    if ignore_space:
        lines = [re.sub(r"\s+", " ", ln).strip() for ln in lines]
    if ignore_case:
        lines = [ln.lower() for ln in lines]
    return lines


def diff_files(a: str, b: str, *, unified: bool = False, context: int = 3,
               ignore_case: bool = False, ignore_space: bool = False,
               ignore_blank: bool = False) -> List[str]:
    """Return the diff of two text files as a list of lines."""
    pa, pb = Path(a), Path(b)
    la = _read_lines(pa, ignore_case, ignore_space, ignore_blank)
    lb = _read_lines(pb, ignore_case, ignore_space, ignore_blank)
    if unified:
        return list(difflib.unified_diff(la, lb, fromfile=str(pa),
                                         tofile=str(pb), n=context))
    return list(difflib.ndiff(la, lb))


def _inventory(root: Path) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            full = Path(dirpath) / name
            try:
                out[str(full.relative_to(root))] = full.stat().st_size
            except OSError:
                out[str(full.relative_to(root))] = -1
    return out


def diff_dirs(a: str, b: str) -> Dict[str, List[str]]:
    """Compare the file inventories of two directories."""
    ia, ib = _inventory(Path(a)), _inventory(Path(b))
    only_a = sorted(set(ia) - set(ib))
    only_b = sorted(set(ib) - set(ia))
    changed = sorted(p for p in set(ia) & set(ib) if ia[p] != ib[p])
    same = len(set(ia) & set(ib)) - len(changed)
    return {"only_in_a": only_a, "only_in_b": only_b,
            "changed": changed, "identical": same,
            "count_a": len(ia), "count_b": len(ib)}


def cmd_diff(args: argparse.Namespace) -> int:
    pa, pb = Path(args.a), Path(args.b)
    if not pa.exists() or not pb.exists():
        print(f"filediff: no such path: {args.a if not pa.exists() else args.b}",
              file=sys.stderr)
        return 1

    if pa.is_dir() and pb.is_dir():
        result = diff_dirs(args.a, args.b)
        if _json_or_report(result, args) is not None:
            return 0
        print(f"{args.a}: {result['count_a']} files   "
              f"{args.b}: {result['count_b']} files   "
              f"identical: {result['identical']}")
        for label, key in (("only in A", "only_in_a"),
                           ("only in B", "only_in_b"),
                           ("changed", "changed")):
            rows = result[key]
            print(f"\n{label} ({len(rows)}):")
            for row in rows[:args.max_lines]:
                print(f"  {row}")
            if len(rows) > args.max_lines:
                print(f"  ... {len(rows) - args.max_lines} more")
        return 0

    if pa.is_dir() != pb.is_dir():
        print("filediff: one path is a directory and the other is not",
              file=sys.stderr)
        return 2

    # Short circuit: for identical inputs ndiff still echoes every line,
    # which reads as noise rather than "these are the same".
    if _read_lines(pa, args.ignore_case, args.ignore_space,
                   args.ignore_blank) == _read_lines(pb, args.ignore_case,
                                                     args.ignore_space,
                                                     args.ignore_blank):
        print("files are identical")
        return 0

    lines = diff_files(args.a, args.b, unified=args.unified,
                       context=args.context, ignore_case=args.ignore_case,
                       ignore_space=args.ignore_space,
                       ignore_blank=args.ignore_blank)
    if _json_or_report({"diff": lines[:args.max_lines]}, args) is not None:
        return 0
    shown = 0
    for line in lines:
        print(line)
        shown += 1
        if shown >= args.max_lines:
            print(f"... {len(lines) - shown} more lines "
                  f"(raise with --max-lines)")
            break
    if not lines:
        print("files are identical")
    return 0


# --------------------------------------------------------------------------- #
# 3. filesanitize
# --------------------------------------------------------------------------- #
def _parser_sanitize() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge filesanitize",
                                description="Find / fix illegal file names.")
    p.add_argument("paths", nargs="+")
    p.add_argument("--apply", action="store_true",
                   help="actually rename (default: dry run)")
    p.add_argument("--replacement", default="_",
                   help="character used for illegal ones (default: _)")
    p.add_argument("--windows", action="store_true",
                   help="apply the Windows rule set on any platform")
    p.add_argument("--json", action="store_true")
    p.add_argument("--out", metavar="FILE")
    return p


def sanitize_name(name: str, replacement: str = "_",
                  windows: bool = False) -> Tuple[str, List[str]]:
    """Return ``(safe_name, problems_found)`` for one file name."""
    problems: List[str] = []
    if not name or name in (".", ".."):
        return name, ["empty or reserved name"]
    safe = name
    if windows or os.name == "nt":
        bad = [c for c in safe if c in WINDOWS_ILLEGAL]
        if bad:
            problems.append("illegal characters: " + "".join(sorted(set(bad))))
            for c in set(bad):
                safe = safe.replace(c, replacement)
        stem = os.path.splitext(safe)[0].upper()
        if stem in WINDOWS_RESERVED:
            problems.append(f"reserved name: {stem}")
            safe = replacement + safe
    ctrl = [c for c in safe if ord(c) < 32]
    if ctrl:
        problems.append("control characters")
        for c in set(ctrl):
            safe = safe.replace(c, replacement)
    if safe != safe.rstrip(" ."):
        problems.append("trailing dot or space")
        safe = safe.rstrip(" .")
    if len(safe.encode("utf-8", "replace")) > 255:
        problems.append("name longer than 255 bytes")
        while len(safe.encode("utf-8", "replace")) > 255:
            safe = safe[:-1]
    if not safe.strip():
        safe = "unnamed"
        problems.append("name became empty")
    return safe, problems


def cmd_sanitize(args: argparse.Namespace) -> int:
    rows: List[Dict[str, object]] = []
    for raw in args.paths:
        path = Path(raw).expanduser()
        name = path.name
        safe, problems = sanitize_name(name, args.replacement, args.windows)
        row: Dict[str, object] = {"path": str(path), "name": name,
                                  "safe_name": safe, "problems": problems,
                                  "renamed": False}
        if problems and args.apply and path.exists():
            target = path.with_name(safe)
            if target.exists():
                row["error"] = "target already exists"
            else:
                try:
                    path.rename(target)
                    row["renamed"] = True
                except OSError as exc:
                    row["error"] = str(exc)
        rows.append(row)

    if _json_or_report({"results": rows}, args) is not None:
        return 0
    dirty = [r for r in rows if r["problems"]]
    for row in rows:
        flag = "FIXED" if row["renamed"] else ("DIRTY" if row["problems"] else "ok")
        print(f"  [{flag:<5}] {row['name']}")
        if row["problems"]:
            print(f"          -> {row['safe_name']}  ({', '.join(row['problems'])})")
        if "error" in row:
            print(f"          !! {row['error']}")
    print(f"\n{len(dirty)} of {len(rows)} name(s) need attention"
          + ("" if args.apply else " (dry run - add --apply to rename)"))
    return 0


# --------------------------------------------------------------------------- #
# 4. filenorm
# --------------------------------------------------------------------------- #
def _parser_norm() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge filenorm",
                                description="Normalise file names.")
    p.add_argument("paths", nargs="+")
    p.add_argument("--nfc", action="store_true", help="Unicode NFC form")
    p.add_argument("--case", choices=["lower", "upper", "title", "none"],
                   default="none")
    p.add_argument("--space", choices=["underscore", "dash", "collapse", "none"],
                   default="none", help="what to do with spaces")
    p.add_argument("--strip-accents", action="store_true",
                   help="transliterate accents to ASCII")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--out", metavar="FILE")
    return p


def normalize_name(name: str, *, nfc: bool = False, case: str = "none",
                   space: str = "none", strip_accents: bool = False) -> str:
    """Apply the requested name transformations."""
    out = name
    if nfc:
        out = unicodedata.normalize("NFC", out)
    if strip_accents:
        decomposed = unicodedata.normalize("NFKD", out)
        out = "".join(c for c in decomposed if not unicodedata.combining(c))
    if space == "underscore":
        out = re.sub(r"\s+", "_", out)
    elif space == "dash":
        out = re.sub(r"\s+", "-", out)
    elif space == "collapse":
        out = re.sub(r"\s+", " ", out).strip()
    if case == "lower":
        out = out.lower()
    elif case == "upper":
        out = out.upper()
    elif case == "title":
        out = out.title()
    return out


def cmd_norm(args: argparse.Namespace) -> int:
    rows: List[Dict[str, object]] = []
    for raw in args.paths:
        path = Path(raw).expanduser()
        new = normalize_name(path.name, nfc=args.nfc, case=args.case,
                             space=args.space,
                             strip_accents=args.strip_accents)
        row: Dict[str, object] = {"path": str(path), "name": path.name,
                                  "new_name": new,
                                  "changed": new != path.name, "renamed": False}
        if row["changed"] and args.apply and path.exists():
            target = path.with_name(new)
            if target.exists():
                row["error"] = "target already exists"
            else:
                try:
                    path.rename(target)
                    row["renamed"] = True
                except OSError as exc:
                    row["error"] = str(exc)
        rows.append(row)

    if _json_or_report({"results": rows}, args) is not None:
        return 0
    changed = sum(1 for r in rows if r["changed"])
    for row in rows:
        if not row["changed"]:
            print(f"  [ ok   ] {row['name']}")
            continue
        flag = "FIXED" if row["renamed"] else "DRY"
        print(f"  [{flag:<5}] {row['name']} -> {row['new_name']}")
        if "error" in row:
            print(f"          !! {row['error']}")
    print(f"\n{changed} of {len(rows)} name(s) would change"
          + ("" if args.apply else " (dry run - add --apply to rename)"))
    return 0


# --------------------------------------------------------------------------- #
# 5. fileextract
# --------------------------------------------------------------------------- #
def _parser_extract() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge fileextract",
                                description="Extract URLs / mails / IPs.")
    p.add_argument("path")
    p.add_argument("--urls", action="store_true")
    p.add_argument("--emails", action="store_true")
    p.add_argument("--ips", action="store_true")
    p.add_argument("--all", action="store_true")
    p.add_argument("--unique", action="store_true", help="de-duplicate")
    p.add_argument("--count", action="store_true", help="counts only")
    p.add_argument("--json", action="store_true")
    p.add_argument("--out", metavar="FILE")
    return p


def extract_from_file(path: str, *, urls: bool = False, emails: bool = False,
                      ips: bool = False, unique: bool = True
                      ) -> Dict[str, List[str]]:
    """Pull URLs / e-mails / IPv4 addresses out of a text file."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    want_all = not (urls or emails or ips)
    found: Dict[str, List[str]] = {}
    if urls or want_all:
        found["urls"] = URL_RE.findall(text)
    if emails or want_all:
        found["emails"] = EMAIL_RE.findall(text)
    if ips or want_all:
        candidates = IPV4_RE.findall(text)
        found["ips"] = [c for c in candidates
                        if all(0 <= int(part) <= 255 for part in c.split("."))]
    if unique:
        for key, values in list(found.items()):
            seen: List[str] = []
            for value in values:
                if value not in seen:
                    seen.append(value)
            found[key] = seen
    return found


def cmd_extract(args: argparse.Namespace) -> int:
    try:
        found = extract_from_file(args.path, urls=args.urls,
                                  emails=args.emails, ips=args.ips,
                                  unique=args.unique)
    except OSError as exc:
        print(f"fileextract: {exc}", file=sys.stderr)
        return 1
    payload: Dict[str, object] = dict(found)
    payload["counts"] = {k: len(v) for k, v in found.items()}
    if _json_or_report(payload, args) is not None:
        return 0
    for key, values in found.items():
        print(f"{key} ({len(values)}):")
        if args.count:
            continue
        for value in values:
            print(f"  {value}")
    return 0


# --------------------------------------------------------------------------- #
# 6/7. encode / decode
# --------------------------------------------------------------------------- #
def _parser_codec(mode: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=f"fileforge file{mode}",
                                description=f"{mode.capitalize()} a file.")
    p.add_argument("path")
    p.add_argument("--base64", action="store_true")
    p.add_argument("--hex", action="store_true")
    p.add_argument("--url", action="store_true")
    p.add_argument("-o", "--out", metavar="FILE",
                   help="write here instead of stdout")
    p.add_argument("--max-bytes", type=int, default=4096,
                   help="how much to print to the terminal (default: 4096)")
    return p


def _pick_codec(args: argparse.Namespace) -> str:
    if args.base64:
        return "base64"
    if args.hex:
        return "hex"
    if args.url:
        return "url"
    return "base64"


def cmd_encode(args: argparse.Namespace) -> int:
    try:
        raw = Path(args.path).expanduser().read_bytes()
    except OSError as exc:
        print(f"fileencode: {exc}", file=sys.stderr)
        return 1
    codec = _pick_codec(args)
    if codec == "base64":
        data = base64.b64encode(raw)
    elif codec == "hex":
        data = binascii.hexlify(raw)
    else:
        from urllib.parse import quote
        data = quote(raw.decode("utf-8", "replace"), safe="").encode("ascii")
    return _emit_bytes(data, args, codec)


def cmd_decode(args: argparse.Namespace) -> int:
    try:
        raw = Path(args.path).expanduser().read_bytes()
    except OSError as exc:
        print(f"filedecode: {exc}", file=sys.stderr)
        return 1
    codec = _pick_codec(args)
    try:
        if codec == "base64":
            data = base64.b64decode(raw, validate=False)
        elif codec == "hex":
            data = binascii.unhexlify(re.sub(rb"\s+", b"", raw))
        else:
            from urllib.parse import unquote_to_bytes
            data = unquote_to_bytes(raw)
    except (binascii.Error, ValueError) as exc:
        print(f"filedecode: {codec} decode failed: {exc}", file=sys.stderr)
        return 1
    return _emit_bytes(data, args, codec)


def _emit_bytes(data: bytes, args: argparse.Namespace, codec: str) -> int:
    if args.out:
        Path(args.out).write_bytes(data)
        print(f"{len(data):,} bytes written to {args.out} [{codec}]")
        return 0
    chunk = data[:args.max_bytes]
    sys.stdout.write(chunk.decode("utf-8", "replace"))
    sys.stdout.write("\n")
    if len(data) > len(chunk):
        print(f"... {len(data) - len(chunk):,} more bytes "
              f"(use -o FILE to save)", file=sys.stderr)
    return 0


# --------------------------------------------------------------------------- #
# 8. filetrim
# --------------------------------------------------------------------------- #
def _parser_trim() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge filetrim",
                                description="Clean up a text file.")
    p.add_argument("path")
    p.add_argument("-o", "--out", metavar="FILE",
                   help="write here (default: stdout)")
    p.add_argument("--blank", action="store_true", help="drop blank lines")
    p.add_argument("--trailing", action="store_true",
                   help="strip trailing whitespace")
    p.add_argument("--bom", action="store_true", help="remove a UTF-8 BOM")
    p.add_argument("--crlf", action="store_true",
                   help="convert CRLF / CR line endings to LF")
    p.add_argument("--all", action="store_true")
    p.add_argument("--in-place", action="store_true",
                   help="rewrite the file itself (a .bak copy is kept)")
    return p


def trim_lines(text: str, *, blank: bool = False, trailing: bool = False,
               bom: bool = False, crlf: bool = False) -> Tuple[str, Dict[str, int]]:
    """Clean up ``text``; returns the new text and a per-rule hit counter."""
    hits = {"blank": 0, "trailing": 0, "bom": 0, "crlf": 0}
    out = text
    if bom and out.startswith("\ufeff"):
        out = out[1:]
        hits["bom"] = 1
    if crlf:
        before = out.count("\r\n") + out.count("\r")
        out = out.replace("\r\n", "\n").replace("\r", "\n")
        hits["crlf"] = before
    if trailing:
        lines = out.split("\n")
        new_lines = []
        for line in lines:
            stripped = line.rstrip()
            if stripped != line:
                hits["trailing"] += 1
            new_lines.append(stripped)
        out = "\n".join(new_lines)
    if blank:
        lines = out.split("\n")
        kept = [ln for ln in lines if ln.strip()]
        hits["blank"] = len(lines) - len(kept)
        out = "\n".join(kept)
    return out, hits


def cmd_trim(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser()
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"filetrim: {exc}", file=sys.stderr)
        return 1
    all_rules = args.all
    new, hits = trim_lines(text, blank=args.blank or all_rules,
                           trailing=args.trailing or all_rules,
                           bom=args.bom or all_rules,
                           crlf=args.crlf or all_rules)
    if args.in_place:
        backup = path.with_suffix(path.suffix + ".bak")
        try:
            shutil.copy2(path, backup)
            path.write_text(new, encoding="utf-8")
        except OSError as exc:
            print(f"filetrim: {exc}", file=sys.stderr)
            return 1
        print(f"rewrote {path} (backup: {backup.name})")
    elif args.out:
        Path(args.out).write_text(new, encoding="utf-8")
        print(f"written: {args.out}")
    else:
        sys.stdout.write(new)
    total = sum(hits.values())
    print(f"[filetrim] {total} change(s): " +
          ", ".join(f"{k}={v}" for k, v in hits.items()), file=sys.stderr)
    return 0


# --------------------------------------------------------------------------- #
# 9. filesort
# --------------------------------------------------------------------------- #
def _parser_sort() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge filesort",
                                description="Sort / de-duplicate lines.")
    p.add_argument("path")
    p.add_argument("-o", "--out", metavar="FILE")
    p.add_argument("--unique", action="store_true", help="drop duplicates")
    p.add_argument("--reverse", action="store_true")
    p.add_argument("--numeric", action="store_true")
    p.add_argument("--ignore-case", action="store_true")
    p.add_argument("--in-place", action="store_true")
    return p


def sort_lines(text: str, *, unique: bool = False, reverse: bool = False,
               numeric: bool = False, ignore_case: bool = False
               ) -> Tuple[str, Dict[str, int]]:
    lines = text.splitlines()
    original = len(lines)

    def key(line: str):
        if numeric:
            m = re.search(r"-?\d+(?:\.\d+)?", line)
            if m:
                return (0, float(m.group(0)), line.lower() if ignore_case else line)
        return (1, 0.0, line.lower() if ignore_case else line)

    lines.sort(key=key, reverse=reverse)
    if unique:
        seen = set()
        kept = []
        for line in lines:
            marker = line.lower() if ignore_case else line
            if marker in seen:
                continue
            seen.add(marker)
            kept.append(line)
        lines = kept
    return "\n".join(lines) + ("\n" if text.endswith("\n") else ""), {
        "in": original, "out": len(lines), "removed": original - len(lines)}


def cmd_sort(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser()
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"filesort: {exc}", file=sys.stderr)
        return 1
    new, stats = sort_lines(text, unique=args.unique, reverse=args.reverse,
                            numeric=args.numeric,
                            ignore_case=args.ignore_case)
    if args.in_place:
        backup = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup)
        path.write_text(new, encoding="utf-8")
        print(f"sorted {path} ({stats['in']} -> {stats['out']} lines, "
              f"backup: {backup.name})")
    elif args.out:
        Path(args.out).write_text(new, encoding="utf-8")
        print(f"written: {args.out} ({stats['in']} -> {stats['out']} lines)")
    else:
        sys.stdout.write(new)
    return 0


# --------------------------------------------------------------------------- #
# 10. filebackup
# --------------------------------------------------------------------------- #
def _parser_backup() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge filebackup",
                                description="Timestamped copy of a file.")
    p.add_argument("path")
    p.add_argument("--dest", help="where to put the copy (default: alongside)")
    p.add_argument("--suffix", default="bak",
                   help="suffix before the timestamp (default: bak)")
    p.add_argument("--keep", type=int, default=0, metavar="N",
                   help="delete older backups, keeping the newest N")
    p.add_argument("--json", action="store_true")
    return p


def cmd_backup(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser()
    if not path.exists():
        print(f"filebackup: no such path: {path}", file=sys.stderr)
        return 1
    stamp = time.strftime("%Y%m%d-%H%M%S")
    name = f"{path.name}.{args.suffix}-{stamp}"
    dest_dir = Path(args.dest).expanduser() if args.dest else path.parent
    target = dest_dir / name
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        if path.is_dir():
            shutil.copytree(path, target)
        else:
            shutil.copy2(path, target)
    except (OSError, shutil.Error) as exc:
        print(f"filebackup: {exc}", file=sys.stderr)
        return 1

    pruned: List[str] = []
    if args.keep > 0:
        prefix = f"{path.name}.{args.suffix}-"
        older = [p for p in dest_dir.iterdir()
                 if p.name.startswith(prefix) and p != target]
        older.sort(key=lambda p: p.name)
        for victim in older[:max(0, len(older) - args.keep + 1)]:
            try:
                if victim.is_dir():
                    shutil.rmtree(victim)
                else:
                    victim.unlink()
                pruned.append(victim.name)
            except OSError:
                continue

    payload = {"source": str(path), "backup": str(target),
               "size": target.stat().st_size if target.is_file() else None,
               "pruned": pruned}
    if args.json:
        import json
        print(_dump_json(payload))
        return 0
    print(f"backup: {target}")
    if pruned:
        print(f"pruned {len(pruned)} old backup(s): {', '.join(pruned)}")
    return 0


# --------------------------------------------------------------------------- #
# 11. filepreview
# --------------------------------------------------------------------------- #
def _parser_preview() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge filepreview",
                                description="Preview any file.")
    p.add_argument("path")
    p.add_argument("--lines", type=int, default=40, help="text lines (default 40)")
    p.add_argument("--bytes", type=int, default=0,
                   help="read at most this many bytes")
    p.add_argument("--encoding", default="utf-8")
    p.add_argument("--no-number", action="store_true")
    return p


def cmd_preview(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser()
    if not path.exists():
        print(f"filepreview: no such path: {path}", file=sys.stderr)
        return 1
    if path.is_dir():
        try:
            entries = sorted(os.scandir(path), key=lambda e: e.name)
        except OSError as exc:
            print(f"filepreview: {exc}", file=sys.stderr)
            return 1
        print(f"{path}  ({len(entries)} entries)")
        for entry in entries[:args.lines]:
            try:
                st = entry.stat(follow_symlinks=False)
                size = human_size(st.st_size)
            except OSError:
                size = "?"
            kind = "d" if entry.is_dir(follow_symlinks=False) else "-"
            print(f"  {kind} {size:>10}  {entry.name}")
        if len(entries) > args.lines:
            print(f"  ... {len(entries) - args.lines} more")
        return 0

    try:
        if is_binary(path):
            data = path.read_bytes()
            if args.bytes:
                data = data[:args.bytes]
            else:
                data = data[:args.lines * 16]
            for line in hexdump(data, width=16):
                print(line)
            print(f"(binary file, {human_size(path.stat().st_size)})",
                  file=sys.stderr)
            return 0
        raw = path.read_bytes()
        if args.bytes:
            raw = raw[:args.bytes]
        text = raw.decode(args.encoding, errors="replace")
    except OSError as exc:
        print(f"filepreview: {exc}", file=sys.stderr)
        return 1

    lines = text.splitlines()
    for index, line in enumerate(lines[:args.lines], 1):
        print(f"{'' if args.no_number else f'{index:>6}: '}{line}")
    if len(lines) > args.lines:
        print(f"... {len(lines) - args.lines} more lines")
    return 0


# --------------------------------------------------------------------------- #
# 12. filehex
# --------------------------------------------------------------------------- #
def _parser_hex() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge filehex",
                                description="Hex dump of a file.")
    p.add_argument("path")
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--length", type=int, default=512)
    p.add_argument("--width", type=int, default=16)
    p.add_argument("-o", "--out", metavar="FILE")
    return p


def hexdump(data: bytes, width: int = 16, base_offset: int = 0) -> List[str]:
    """Classic ``offset | hex | ascii`` dump as a list of lines."""
    out: List[str] = []
    for start in range(0, len(data), width):
        chunk = data[start:start + width]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        out.append(f"{base_offset + start:08x}  {hex_part:<{width * 3}}  "
                   f"|{ascii_part}|")
    return out


def cmd_hex(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser()
    try:
        with path.open("rb") as fh:
            fh.seek(max(0, args.offset))
            data = fh.read(max(1, args.length))
    except OSError as exc:
        print(f"filehex: {exc}", file=sys.stderr)
        return 1
    lines = hexdump(data, width=max(1, args.width), base_offset=max(0, args.offset))
    if args.out:
        Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"written: {args.out} ({len(lines)} lines)")
        return 0
    for line in lines:
        print(line)
    return 0


# --------------------------------------------------------------------------- #
# shared output helpers
# --------------------------------------------------------------------------- #
def _dump_json(obj) -> str:
    import json
    return json.dumps(obj, indent=2, ensure_ascii=False, default=str)


def _json_or_report(obj, args: argparse.Namespace) -> Optional[str]:
    """Write JSON when ``--json``/``--out`` is set; else return None."""
    if getattr(args, "json", False) or getattr(args, "out", None):
        text = _dump_json(obj)
        if getattr(args, "out", None):
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"written: {args.out}")
        else:
            print(text)
        return text
    return None


PARSERS: Dict[str, Callable[[], argparse.ArgumentParser]] = {
    "filemeta": _parser_meta,
    "filediff": _parser_diff,
    "filesanitize": _parser_sanitize,
    "filenorm": _parser_norm,
    "fileextract": _parser_extract,
    "fileencode": lambda: _parser_codec("encode"),
    "filedecode": lambda: _parser_codec("decode"),
    "filetrim": _parser_trim,
    "filesort": _parser_sort,
    "filebackup": _parser_backup,
    "filepreview": _parser_preview,
    "filehex": _parser_hex,
}

HANDLERS: Dict[str, Callable[[argparse.Namespace], int]] = {
    "filemeta": cmd_meta,
    "filediff": cmd_diff,
    "filesanitize": cmd_sanitize,
    "filenorm": cmd_norm,
    "fileextract": cmd_extract,
    "fileencode": cmd_encode,
    "filedecode": cmd_decode,
    "filetrim": cmd_trim,
    "filesort": cmd_sort,
    "filebackup": cmd_backup,
    "filepreview": cmd_preview,
    "filehex": cmd_hex,
}


def run(name: str, argv: Sequence[str]) -> int:
    parser = PARSERS[name]()
    try:
        args = parser.parse_args(list(argv))
    except SystemExit as exc:
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
        print(f"{APP}: filekit has no command {args[0]!r}", file=sys.stderr)
        return 2
    return run(name, args[1:])


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
