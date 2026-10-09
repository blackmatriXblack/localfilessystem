"""
fileforge.utils
===============

Shared helpers used across the whole toolkit. Pure standard library so the
tool runs unchanged on Linux, Windows and macOS without any dependency.

Author : fileforge
License: MIT
"""

from __future__ import annotations

import fnmatch
import hashlib
import mimetypes
import os
import platform
import re
import shutil
import stat
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Tuple

# --------------------------------------------------------------------------- #
# Platform detection
# --------------------------------------------------------------------------- #

PLATFORM = platform.system()  # "Linux" | "Windows" | "Darwin"
IS_WINDOWS = PLATFORM == "Windows"
IS_MACOS = PLATFORM == "Darwin"
IS_LINUX = PLATFORM == "Linux"


def platform_name() -> str:
    """Human readable platform label."""
    friendly = {"Windows": "Windows", "Darwin": "macOS", "Linux": "Linux"}
    return friendly.get(PLATFORM, PLATFORM)


# --------------------------------------------------------------------------- #
# Output helpers (minimal black & white aware terminal writer)
# --------------------------------------------------------------------------- #

class _Style:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"


def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if not sys.stdout.isatty():
        return False
    if IS_WINDOWS:
        # Enable ANSI processing on modern Windows terminals.
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            return False
    return True


_COLOR = _supports_color()


def paint(text: str, *styles: str) -> str:
    """Wrap `text` with ANSI styles when the terminal supports color."""
    if not _COLOR or not styles:
        return text
    return "".join(styles) + text + _Style.RESET


def info(msg: str) -> None:
    print(msg)


def ok(msg: str) -> None:
    print(paint("[OK] ", _Style.GREEN, _Style.BOLD) + msg)


def warn(msg: str) -> None:
    print(paint("[WARN] ", _Style.YELLOW, _Style.BOLD) + msg)


def error(msg: str) -> None:
    print(paint("[ERROR] ", _Style.RED, _Style.BOLD) + msg, file=sys.stderr)


def heading(msg: str) -> None:
    print(paint(msg, _Style.BOLD, _Style.CYAN))


# --------------------------------------------------------------------------- #
# Error model
# --------------------------------------------------------------------------- #

class FileForgeError(Exception):
    """Base exception for every recoverable toolkit error."""


class PathError(FileForgeError):
    """Raised when a path is missing, invalid or unsafe."""


# --------------------------------------------------------------------------- #
# Human friendly formatting
# --------------------------------------------------------------------------- #

_UNITS = ["B", "KB", "MB", "GB", "TB", "PB", "EB"]


def human_size(num: float, precision: int = 2) -> str:
    """Convert a byte count into a compact human readable string."""
    if num < 0:
        return "-" + human_size(-num, precision)
    value = float(num)
    for unit in _UNITS:
        if value < 1024.0 or unit == _UNITS[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.{precision}f} {unit}"
        value /= 1024.0
    return f"{value:.{precision}f} {_UNITS[-1]}"


def human_time(ts: float, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format a POSIX timestamp in local time."""
    try:
        return time.strftime(fmt, time.localtime(ts))
    except (OSError, ValueError, OverflowError):
        return "-"


def human_duration(seconds: float) -> str:
    """Format a delta of seconds, e.g. '2d 3h 4m 5s'."""
    seconds = int(abs(seconds))
    parts: List[str] = []
    for label, size in (("d", 86400), ("h", 3600), ("m", 60), ("s", 1)):
        if seconds >= size or (label == "s" and not parts):
            qty, seconds = divmod(seconds, size)
            parts.append(f"{qty}{label}")
    return " ".join(parts)


# --------------------------------------------------------------------------- #
# Path helpers
# --------------------------------------------------------------------------- #

def resolve(path: str) -> Path:
    """Expand ~ and environment variables, then return an absolute Path."""
    expanded = os.path.expandvars(os.path.expanduser(str(path)))
    return Path(expanded).expanduser()


def ensure_exists(path: Path) -> Path:
    if not path.exists():
        raise PathError(f"Path does not exist: {path}")
    return path


def ensure_parent(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def unique_path(path: Path) -> Path:
    """Return `path`, or path-1, path-2 ... if it already exists."""
    if not path.exists():
        return path
    stem, suffix, parent = path.stem, path.suffix, path.parent
    i = 1
    while True:
        candidate = parent / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def role_of(path: Path) -> str:
    if path.is_symlink():
        return "link"
    if path.is_dir():
        return "dir"
    if path.is_file():
        return "file"
    return "other"


# --------------------------------------------------------------------------- #
# Walking / filtering
# --------------------------------------------------------------------------- #

@dataclass
class Entry:
    path: Path
    rel: str
    is_dir: bool
    is_link: bool
    size: int
    mtime: float
    mode: int
    ext: str


def iter_entries(
    root: Path,
    recursive: bool = True,
    include_hidden: bool = False,
    follow_symlinks: bool = False,
    max_depth: Optional[int] = None,
) -> Iterator[Entry]:
    """Yield :class:`Entry` objects under `root` (directories included)."""
    root = root if root.is_dir() else root.parent
    base_depth = len(root.parts)

    def _keep(p: Path) -> bool:
        if include_hidden:
            return True
        return not p.name.startswith(".")

    for dirpath, dirnames, filenames in os.walk(
        root, followlinks=follow_symlinks, onerror=lambda e: None
    ):
        d = Path(dirpath)
        if not include_hidden:
            dirnames[:] = [n for n in dirnames if not n.startswith(".")]
        depth = len(d.parts) - base_depth
        if max_depth is not None and depth >= max_depth:
            dirnames[:] = []

        names = sorted(dirnames) + sorted(filenames)
        for name in names:
            p = d / name
            try:
                st = p.lstat()
            except OSError:
                continue
            try:
                rel = str(p.relative_to(root))
            except ValueError:
                rel = str(p)
            yield Entry(
                path=p,
                rel=rel,
                is_dir=p.is_dir(),
                is_link=p.is_symlink(),
                size=st.st_size,
                mtime=st.st_mtime,
                mode=st.st_mode,
                ext=p.suffix.lower(),
            )
        if not recursive:
            break


# --------------------------------------------------------------------------- #
# Pattern matching
# --------------------------------------------------------------------------- #

def glob_match(name: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(name, pat) for pat in patterns)


def regex_search(pattern: str, text: str, ignore_case: bool = False) -> Optional[re.Match]:
    flags = re.IGNORECASE if ignore_case else 0
    try:
        return re.search(pattern, text, flags)
    except re.error as exc:
        raise FileForgeError(f"Invalid regular expression: {exc}") from exc


# --------------------------------------------------------------------------- #
# Hashing
# --------------------------------------------------------------------------- #

HASH_ALGOS = ("md5", "sha1", "sha224", "sha256", "sha384", "sha512", "blake2b", "blake2s")


def new_hasher(algorithm: str):
    algorithm = algorithm.lower()
    try:
        return hashlib.new(algorithm)
    except ValueError as exc:
        raise FileForgeError(f"Unsupported hash algorithm: {algorithm}") from exc


def hash_file(path: Path, algorithm: str = "sha256", chunk: int = 1 << 20) -> str:
    """Stream a file through a hash function and return the hex digest."""
    h = new_hasher(algorithm)
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def hash_bytes(data: bytes, algorithm: str = "sha256") -> str:
    h = new_hasher(algorithm)
    h.update(data)
    return h.hexdigest()


# --------------------------------------------------------------------------- #
# File type sniffing
# --------------------------------------------------------------------------- #

_MAGIC = [
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"BM", "image/bmp"),
    (b"RIFF", "audio/video (RIFF container)"),
    (b"%PDF-", "application/pdf"),
    (b"PK\x03\x04", "application/zip (or docx/xlsx/jar)"),
    (b"\x1f\x8b", "application/gzip"),
    (b"BZh", "application/x-bzip2"),
    (b"\xfd7zXZ\x00", "application/x-xz"),
    (b"7z\xbc\xaf\x27\x1c", "application/x-7z-compressed"),
    (b"Rar!\x1a\x07", "application/x-rar"),
    (b"\x7fELF", "application/x-executable (ELF)"),
    (b"MZ", "application/x-dosexec (PE)"),
    (b"\xca\xfe\xba\xbe", "application/java (class)"),
    (b"SQLite format 3\x00", "application/x-sqlite3"),
    (b"OggS", "audio/ogg"),
    (b"ID3", "audio/mpeg"),
    (b"\x00asm", "application/wasm"),
]


def sniff_type(path: Path, head: int = 4096) -> str:
    """Best-effort content based MIME detection with a name based fallback."""
    try:
        with path.open("rb") as fh:
            sample = fh.read(head)
    except OSError:
        return "unknown"
    for magic, label in _MAGIC:
        if sample.startswith(magic):
            return label
    # Text heuristic
    if sample:
        try:
            sample.decode("utf-8")
            return "text/plain (utf-8)"
        except UnicodeDecodeError:
            pass
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def is_binary(path: Path, head: int = 8192) -> bool:
    try:
        with path.open("rb") as fh:
            sample = fh.read(head)
    except OSError:
        return False
    if not sample:
        return False
    if b"\x00" in sample:
        return True
    try:
        sample.decode("utf-8")
        return False
    except UnicodeDecodeError:
        return True


# --------------------------------------------------------------------------- #
# Permissions helpers
# --------------------------------------------------------------------------- #

def mode_string(mode: int) -> str:
    """Return a chmod style string like 'drwxr-xr-x'."""
    return stat.filemode(mode)


def octal_mode(mode: int) -> str:
    return oct(stat.S_IMODE(mode))


# --------------------------------------------------------------------------- #
# Misc
# --------------------------------------------------------------------------- #

def total_size(paths: Iterable[Path]) -> int:
    return sum(p.stat().st_size for p in paths if p.is_file())


def free_space(path: Path) -> Tuple[int, int, int]:
    """Return (total, used, free) bytes for the volume containing `path`."""
    usage = shutil.disk_usage(str(path if path.exists() else path.parent))
    return usage.total, usage.used, usage.free


def safe_relpath(path: Path, start: Path) -> str:
    try:
        return str(path.relative_to(start))
    except ValueError:
        return str(path)
