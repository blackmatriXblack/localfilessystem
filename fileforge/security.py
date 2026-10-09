"""
fileforge.security
==================

Permission inspection / modification, ownership-friendly helpers, secure
deletion (overwrite), and a self-contained authenticated encryption helper.

IMPORTANT
---------
The `encrypt_file` / `decrypt_file` helpers implement a *custom* PBKDF2 +
SHA-256 based stream cipher with an HMAC-SHA256 tag. This is dependency-free
and fine for obfuscation / personal use, but it is NOT audited cryptography.
For sensitive data prefer a dedicated tool such as `age`, `gpg`, or `openssl`.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from . import utils
from .utils import PathError, ensure_parent, resolve

MAGIC = b"FFENC1"
SALT_LEN = 16
ITERATIONS = 200_000
BLOCK = 32
TAG_LEN = 32


# --------------------------------------------------------------------------- #
# Permissions
# --------------------------------------------------------------------------- #

def chmod(path: str, mode: str, recursive: bool = False) -> int:
    """
    Change permission bits.

    `mode` accepts octal strings ('644', '0755') or symbolic forms such as
    '+x', '-w', 'u+rw', 'go-w'.
    """
    p = resolve(path)
    utils.ensure_exists(p)

    targets = [p]
    if recursive and p.is_dir():
        targets += [e.path for e in utils.iter_entries(p, recursive=True, include_hidden=True)]

    changed = 0
    for t in targets:
        current = stat.S_IMODE(t.lstat().st_mode)
        new = _apply_mode(current, mode)
        if new != current:
            os.chmod(t, new)
            changed += 1
    return changed


def _apply_mode(current: int, mode: str) -> int:
    mode = mode.strip()
    if not mode:
        raise PathError("Empty mode")
    # Octal form
    if all(c in "01234567" for c in mode) and len(mode) in (3, 4):
        return int(mode, 8)
    # Symbolic form: [ugoa]*[+-=][rwxX]*
    import re

    total = current
    for clause in mode.split(","):
        m = re.fullmatch(r"([ugoa]*)([+\-=])([rwxX]*)", clause)
        if not m:
            raise PathError(f"Unsupported symbolic mode: {mode!r}")
        who, op, perms = m.groups()
        who = who or "a"
        who_mask = 0
        if "a" in who or "u" in who:
            who_mask |= 0o700
        if "a" in who or "g" in who:
            who_mask |= 0o070
        if "a" in who or "o" in who:
            who_mask |= 0o007

        bit_mask = 0
        if "r" in perms:
            bit_mask |= 0o444
        if "w" in perms:
            bit_mask |= 0o222
        if "x" in perms or "X" in perms:
            bit_mask |= 0o111
        bit_mask &= who_mask

        if op == "+":
            total |= bit_mask
        elif op == "-":
            total &= ~bit_mask
        else:  # '='
            total = (total & ~who_mask) | bit_mask
    return total & 0o7777


@dataclass
class PermEntry:
    path: Path
    mode: str
    octal: str
    type: str


def list_permissions(path: str, recursive: bool = False) -> List[PermEntry]:
    p = resolve(path)
    utils.ensure_exists(p)
    entries = [p]
    if recursive and p.is_dir():
        entries += [e.path for e in utils.iter_entries(p, recursive=True, include_hidden=True)]
    out: List[PermEntry] = []
    for t in entries:
        try:
            st = t.lstat()
        except OSError:
            continue
        out.append(PermEntry(t, utils.mode_string(st.st_mode),
                             utils.octal_mode(st.st_mode), utils.role_of(t)))
    return out


def find_world_writable(root: str) -> List[Path]:
    """Return files/dirs writable by 'others' — useful for a security audit."""
    base = resolve(root)
    utils.ensure_exists(base)
    hits: List[Path] = []
    for e in utils.iter_entries(base, recursive=True, include_hidden=True):
        try:
            mode = e.path.lstat().st_mode
        except OSError:
            continue
        if mode & stat.S_IWOTH and not e.path.is_symlink():
            hits.append(e.path)
    return hits


# --------------------------------------------------------------------------- #
# Secure delete
# --------------------------------------------------------------------------- #

def secure_delete(path: str, passes: int = 3) -> int:
    """
    Overwrite a file's contents before unlinking (best effort; on SSDs and
    copy-on-write / journaling filesystems physical erasure is not guaranteed).
    Returns the number of bytes overwritten.
    """
    p = resolve(path)
    utils.ensure_exists(p)
    if p.is_dir():
        raise PathError("secure_delete only works on files; use remove for dirs.")
    size = p.stat().st_size
    written = 0
    with p.open("r+b") as fh:
        for i in range(max(1, passes)):
            fh.seek(0)
            pattern = bytes([(i * 0x5A + 0xFF) & 0xFF]) * (1 << 16)
            remaining = size
            while remaining > 0:
                block = pattern[: min(len(pattern), remaining)]
                fh.write(block)
                remaining -= len(block)
                written += len(block)
            fh.flush()
            os.fsync(fh.fileno())
    os.chmod(p, 0o600)
    p.unlink()
    return written


# --------------------------------------------------------------------------- #
# Encryption (custom, dependency free)
# --------------------------------------------------------------------------- #

def _derive(password: str, salt: bytes, length: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt,
                               ITERATIONS, dklen=length)


def _keystream_xor(data: bytes, key: bytes, nonce: bytes) -> bytes:
    """XOR `data` with a SHA-256 counter keystream."""
    out = bytearray(len(data))
    counter = 0
    off = 0
    n = len(data)
    while off < n:
        block = hashlib.sha256(key + nonce + counter.to_bytes(8, "big")).digest()
        chunk = min(len(block), n - off)
        for i in range(chunk):
            out[off + i] = data[off + i] ^ block[i]
        off += chunk
        counter += 1
    return bytes(out)


def encrypt_bytes(data: bytes, password: str) -> bytes:
    salt = secrets.token_bytes(SALT_LEN)
    nonce = secrets.token_bytes(SALT_LEN)
    material = _derive(password, salt, 64)
    enc_key, mac_key = material[:32], material[32:]
    cipher = _keystream_xor(data, enc_key, nonce)
    header = MAGIC + salt + nonce + ITERATIONS.to_bytes(4, "big")
    tag = hmac.new(mac_key, header + cipher, hashlib.sha256).digest()
    return header + tag + cipher


def decrypt_bytes(blob: bytes, password: str) -> bytes:
    if not blob.startswith(MAGIC):
        raise PathError("Not a fileforge encrypted payload")
    pos = len(MAGIC)
    salt = blob[pos:pos + SALT_LEN]; pos += SALT_LEN
    nonce = blob[pos:pos + SALT_LEN]; pos += SALT_LEN
    iterations = int.from_bytes(blob[pos:pos + 4], "big"); pos += 4
    tag = blob[pos:pos + TAG_LEN]; pos += TAG_LEN
    cipher = blob[pos:]
    material = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt,
                                   iterations, dklen=64)
    enc_key, mac_key = material[:32], material[32:]
    header = MAGIC + salt + nonce + iterations.to_bytes(4, "big")
    expected = hmac.new(mac_key, header + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, tag):
        raise PathError("Decryption failed: wrong password or corrupted file")
    return _keystream_xor(cipher, enc_key, nonce)


def encrypt_file(path: str, password: str, out: Optional[str] = None,
                 remove_source: bool = False) -> Path:
    src = resolve(path)
    utils.ensure_exists(src)
    if src.is_dir():
        raise PathError("encrypt_file expects a single file")
    blob = encrypt_bytes(src.read_bytes(), password)
    dst = ensure_parent(resolve(out)) if out else src.with_suffix(src.suffix + ".ffenc")
    dst.write_bytes(blob)
    if remove_source:
        secure_delete(src)
    return dst


def decrypt_file(path: str, password: str, out: Optional[str] = None,
                 remove_source: bool = False) -> Path:
    src = resolve(path)
    utils.ensure_exists(src)
    plain = decrypt_bytes(src.read_bytes(), password)
    if out:
        dst = ensure_parent(resolve(out))
    elif src.suffix == ".ffenc":
        dst = src.with_suffix("")
    else:
        dst = src.with_name(src.name + ".dec")
    dst.write_bytes(plain)
    if remove_source:
        secure_delete(src)
    return dst
