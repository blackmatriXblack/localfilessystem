#!/usr/bin/env python3
"""
fileforge.diskkit
=================

**Disk and volume tools**: the hardware underneath the file system.

Everything is best-effort: each platform is queried with the tool it ships
with (PowerShell on Windows, ``lsblk``/``/proc`` on Linux, ``diskutil`` on
macOS). When a tool is missing the command degrades to what the standard
library can answer instead of failing.

Commands
--------
    diskinfo       physical disks: model, serial, bus, media, size, health
    diskpartitions partition / volume table with mount points
    diskfs         file system type of every mount point
    diskusage      used vs free per volume, as a block map
    diskfree       free space overview + low-space warning
    diskio         read / write counters (Linux + best effort elsewhere)
    diskhealth     health / SMART status of every disk
    disktemp       temperature where the platform exposes it
    diskbench      real write / read throughput benchmark
    diskserial     volume serial numbers / UUIDs
    diskbadfiles   walk a tree and list files that cannot be read
    diskerrors     walk a tree and list directories that cannot be listed
    disktop        biggest entries directly under a root / every volume
    diskmounts     mount points, removable and network drives

Aliases: ``dinfo``, ``dpart``, ``dfs``, ``dusage``, ``dfree``, ``dio``,
``dhealth``, ``dtemp``, ``dbench``, ``dserial``, ``dbad``, ``derrors``,
``dtop``, ``dmounts``.

Command line
------------
    fileforge diskinfo
    fileforge diskfree --threshold 10
    fileforge diskbench --dir D:\\ --size 128M
    fileforge dtop -r . -n 15
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

try:  # package import
    from .treeview import Options, _list_dir, human_size, system_roots
    from .utils import free_space, human_time, platform_name
    from .treemap import BLOCK, PALETTE, render_blocks
    IS_WINDOWS = os.name == "nt"
except ImportError:  # pragma: no cover - direct script execution fallback
    from treeview import Options, _list_dir, human_size, system_roots  # type: ignore
    from utils import free_space, human_time, platform_name  # type: ignore
    from treemap import BLOCK, PALETTE, render_blocks  # type: ignore
    IS_WINDOWS = os.name == "nt"

APP = "fileforge"

#: Seconds we let an external tool run before giving up.
TOOL_TIMEOUT = 20


# --------------------------------------------------------------------------- #
# Command specification
# --------------------------------------------------------------------------- #
SPEC: List[Tuple[str, List[Tuple[str, str]]]] = [
    ("Disks - hardware", [
        ("diskinfo",      "Physical disks: model, serial, bus, media, size"),
        ("diskpartitions", "Partition / volume table with mount points"),
        ("diskfs",        "File system type of every mount point"),
        ("diskserial",    "Volume serial numbers / UUIDs"),
    ]),
    ("Disks - space", [
        ("diskusage",  "Used vs free per volume, as a block map"),
        ("diskfree",   "Free space overview + low-space warning"),
        ("disktop",    "Biggest entries directly under a root / volume"),
        ("diskmounts", "Mount points, removable and network drives"),
    ]),
    ("Disks - health", [
        ("diskhealth",  "Health / SMART status of every disk"),
        ("disktemp",    "Temperature where the platform exposes it"),
        ("diskio",      "Read / write counters"),
        ("diskbench",   "Real write / read throughput benchmark"),
    ]),
    ("Disks - integrity", [
        ("diskbadfiles", "Walk a tree and list files that cannot be read"),
        ("diskerrors",   "Walk a tree and list directories that fail to list"),
    ]),
]

ALIASES: Dict[str, str] = {
    "dinfo": "diskinfo",
    "dpart": "diskpartitions",
    "dpartitions": "diskpartitions",
    "dfs": "diskfs",
    "dusage": "diskusage",
    "dfree": "diskfree",
    "dio": "diskio",
    "dhealth": "diskhealth",
    "dtemp": "disktemp",
    "dbench": "diskbench",
    "dserial": "diskserial",
    "dbad": "diskbadfiles",
    "dbadfiles": "diskbadfiles",
    "derrors": "diskerrors",
    "dtop": "disktop",
    "dmounts": "diskmounts",
}


def command_names() -> List[str]:
    return [name for _group, entries in SPEC for name, _help in entries]


# --------------------------------------------------------------------------- #
# Platform probes
# --------------------------------------------------------------------------- #
def _which(name: str) -> Optional[str]:
    return shutil.which(name)


def _run(argv: Sequence[str], timeout: int = TOOL_TIMEOUT) -> Optional[str]:
    try:
        proc = subprocess.run(list(argv), stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, timeout=timeout,
                              check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", "replace")


def _ps(script: str, timeout: int = TOOL_TIMEOUT) -> Optional[str]:
    """Run a PowerShell snippet and return its stdout (Windows only)."""
    exe = _which("powershell") or _which("pwsh")
    if not exe:
        return None
    return _run([exe, "-NoProfile", "-NonInteractive",
                 "-ExecutionPolicy", "Bypass", "-Command", script], timeout)


def _ps_json(script: str, timeout: int = TOOL_TIMEOUT) -> Any:
    text = _ps(script, timeout)
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _as_list(value: Any) -> List[Dict[str, Any]]:
    """PowerShell returns a bare object for single results - normalise it."""
    if value is None:
        return []
    if isinstance(value, list):
        return [v for v in value if isinstance(v, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------- #
# Data sources
# --------------------------------------------------------------------------- #
def physical_disks() -> List[Dict[str, Any]]:
    """Best-effort inventory of the physical disks in this machine."""
    rows: List[Dict[str, Any]] = []

    if IS_WINDOWS:
        data = _ps_json(
            "@(Get-PhysicalDisk | Select-Object DeviceId,FriendlyName,"
            "SerialNumber,MediaType,BusType,Size,HealthStatus,"
            "OperationalStatus,SpindleSpeed) | ConvertTo-Json -Depth 3")
        for row in _as_list(data):
            rows.append({
                "id": row.get("DeviceId"),
                "model": (row.get("FriendlyName") or "").strip(),
                "serial": (row.get("SerialNumber") or "").strip(),
                "media": row.get("MediaType"),
                "bus": row.get("BusType"),
                "size": _int(row.get("Size")),
                "health": row.get("HealthStatus"),
                "status": row.get("OperationalStatus"),
            })
        if rows:
            return rows

    lsblk = _which("lsblk")
    if lsblk:
        text = _run([lsblk, "-d", "-J", "-o",
                     "NAME,SIZE,TYPE,MODEL,SERIAL,ROTA,TRAN,VENDOR"])
        if text:
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                data = None
            for dev in (data or {}).get("blockdevices", []):
                rows.append({
                    "id": dev.get("name"),
                    "model": (dev.get("model") or "").strip(),
                    "serial": (dev.get("serial") or "").strip(),
                    "media": "HDD" if str(dev.get("rota")) == "1" else "SSD",
                    "bus": dev.get("tran"),
                    "size": _parse_human(dev.get("size")),
                    "health": None,
                    "status": None,
                })
            if rows:
                return rows

    diskutil = _which("diskutil")
    if diskutil:
        import plistlib
        raw = subprocess.run([diskutil, "list", "-plist"],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             timeout=TOOL_TIMEOUT, check=False).stdout
        try:
            data = plistlib.loads(raw)
        except Exception:  # noqa: BLE001 - plistlib raises several types
            data = None
        for disk in (data or {}).get("AllDisksAndPartitions", []):
            rows.append({
                "id": disk.get("DeviceIdentifier"),
                "model": disk.get("DeviceIdentifier"),
                "serial": "",
                "media": "SSD" if "SSD" in str(disk.get("Content", "")).upper()
                         else disk.get("Content"),
                "bus": None,
                "size": _int(disk.get("Size")),
                "health": None,
                "status": None,
            })
        if rows:
            return rows

    # Last resort: describe what the standard library can see.
    for root in system_roots():
        try:
            total, _used, _free = free_space(Path(root))
        except OSError:
            continue
        rows.append({"id": root, "model": "volume", "serial": "", "media": None,
                     "bus": None, "size": total, "health": None, "status": None})
    return rows


def _parse_human(value: Any) -> int:
    """``lsblk`` prints sizes like '512G' / '1.8T'."""
    text = str(value or "").strip()
    units = {"B": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3,
             "T": 1024 ** 4, "P": 1024 ** 5}
    if text and text[-1] in units:
        try:
            return int(float(text[:-1]) * units[text[-1]])
        except ValueError:
            return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def volumes_fs() -> List[Dict[str, Any]]:
    """Every mount point with its file system type where discoverable."""
    rows: List[Dict[str, Any]] = []
    fs_types: Dict[str, str] = {}

    if IS_WINDOWS:
        data = _ps_json("@(Get-Volume | Select-Object DriveLetter,"
                        "FileSystemLabel,FileSystem,DriveType,HealthStatus,"
                        "Size,SizeRemaining) | ConvertTo-Json -Depth 3")
        for row in _as_list(data):
            letter = (row.get("DriveLetter") or "").strip()
            if not letter:
                continue
            root = f"{letter}:\\"
            fs_types[root] = row.get("FileSystem") or ""
            total = _int(row.get("Size"))
            free = _int(row.get("SizeRemaining"))
            rows.append({
                "mount": root,
                "label": row.get("FileSystemLabel") or "",
                "fstype": row.get("FileSystem") or "",
                "drive_type": row.get("DriveType"),
                "health": row.get("HealthStatus"),
                "total": total,
                "free": free,
                "used": max(0, total - free),
            })
        if rows:
            return rows

    df = _which("df")
    if df:
        text = _run([df, "-PTk"]) or _run([df, "-Pk"]) or ""
        for line in text.splitlines()[1:]:
            parts = line.split()
            if len(parts) < 6:
                continue
            mount = parts[-1]
            try:
                total = int(parts[1]) * 1024
                used = int(parts[2]) * 1024
                free = int(parts[3]) * 1024
            except ValueError:
                continue
            fstype = parts[0] if len(parts) >= 7 else ""
            rows.append({"mount": mount, "label": "", "fstype": fstype,
                         "drive_type": None, "health": None, "total": total,
                         "free": free, "used": used})

    for root in system_roots():
        if any(r["mount"] == root for r in rows):
            continue
        try:
            total, _used, free = free_space(Path(root))
        except OSError:
            continue
        rows.append({"mount": root, "label": "", "fstype": "", "drive_type": None,
                     "health": None, "total": total, "free": free,
                     "used": max(0, total - free)})
    return rows


def volume_serials() -> List[Dict[str, Any]]:
    """Volume serial numbers (Windows) / UUIDs (POSIX)."""
    rows: List[Dict[str, Any]] = []

    if IS_WINDOWS:
        data = _ps_json("@(Get-CimInstance Win32_LogicalDisk | "
                        "Select-Object DeviceID,VolumeName,VolumeSerialNumber,"
                        "FileSystem,DriveType,Size,FreeSpace) | "
                        "ConvertTo-Json -Depth 3")
        for row in _as_list(data):
            rows.append({
                "mount": (row.get("DeviceID") or "").strip() + "\\",
                "label": row.get("VolumeName") or "",
                "serial": row.get("VolumeSerialNumber") or "",
                "fstype": row.get("FileSystem") or "",
                "drive_type": row.get("DriveType"),
            })
        if rows:
            return rows

    blkid = _which("blkid")
    if blkid:
        text = _run([blkid, "-s", "UUID", "-s", "LABEL", "-o", "export"])
        current: Dict[str, str] = {}
        for line in (text or "").splitlines():
            if not line.strip():
                if current:
                    rows.append(current)
                current = {}
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                current[key.lower()] = value
        if current:
            rows.append(current)
        rows = [{"mount": r.get("devname", ""), "label": r.get("label", ""),
                 "serial": r.get("uuid", ""), "fstype": r.get("type", ""),
                 "drive_type": None} for r in rows]
        if rows:
            return rows

    diskutil = _which("diskutil")
    if diskutil:
        text = _run([diskutil, "list"]) or ""
        for line in text.splitlines():
            if line.startswith("/dev/") and "(" in line:
                device = line.split()[0]
                rows.append({"mount": device, "label": "", "serial": "",
                             "fstype": "", "drive_type": None})
    if not rows:
        for root in system_roots():
            rows.append({"mount": root, "label": "", "serial": "",
                         "fstype": "", "drive_type": None})
    return rows


def io_counters() -> List[Dict[str, Any]]:
    """Per-device I/O counters (Linux reads /proc/diskstats)."""
    rows: List[Dict[str, Any]] = []
    stats_path = Path("/proc/diskstats")
    if stats_path.is_file():
        try:
            for line in stats_path.read_text(encoding="utf-8",
                                             errors="replace").splitlines():
                parts = line.split()
                if len(parts) < 14:
                    continue
                name = parts[2]
                reads = _int(parts[3])
                read_sectors = _int(parts[5])
                writes = _int(parts[7])
                write_sectors = _int(parts[11])
                if reads or writes:
                    rows.append({
                        "device": name,
                        "reads": reads,
                        "read_bytes": read_sectors * 512,
                        "writes": writes,
                        "write_bytes": write_sectors * 512,
                    })
        except OSError:
            pass
        return rows

    if IS_WINDOWS:
        data = _ps_json(
            "@(Get-Counter '\\PhysicalDisk(*)\\Disk Read Bytes/sec' "
            "-ErrorAction SilentlyContinue | "
            "Select-Object -ExpandProperty CounterSamples | "
            "Select-Object InstanceName,CookedValue | ConvertTo-Json)")
        for row in _as_list(data):
            rows.append({"device": row.get("InstanceName"),
                         "read_bytes_per_sec": row.get("CookedValue")})
        if rows:
            return rows

    iostat = _which("iostat")
    if iostat:
        text = _run([iostat, "-d"]) or ""
        for line in text.splitlines()[2:]:
            parts = line.split()
            if len(parts) >= 3:
                rows.append({"device": parts[0], "raw": " ".join(parts[1:])})
    return rows


def smart_report() -> Dict[str, Any]:
    """SMART / health information, when the platform exposes it."""
    out: Dict[str, Any] = {"method": None, "disks": []}

    smartctl = _which("smartctl")
    if smartctl:
        scan = _run([smartctl, "--scan"]) or ""
        devices = [line.split()[0] for line in scan.splitlines() if line.strip()]
        out["method"] = "smartctl"
        for device in devices:
            info = _run([smartctl, "-H", "-A", device], timeout=30) or ""
            health = "UNKNOWN"
            temperature = None
            for line in info.splitlines():
                if "SMART overall-health" in line or "SMART Health Status" in line:
                    health = line.split(":")[-1].strip()
                if "Temperature_Celsius" in line or "Temperature:" in line:
                    parts = line.split()
                    for part in reversed(parts):
                        if part.isdigit():
                            temperature = int(part)
                            break
            out["disks"].append({"device": device, "health": health,
                                 "temperature_c": temperature})
        return out

    if IS_WINDOWS:
        data = _ps_json("@(Get-PhysicalDisk | Select-Object FriendlyName,"
                        "HealthStatus,OperationalStatus,SerialNumber,"
                        "MediaType,Size) | ConvertTo-Json -Depth 3")
        out["method"] = "PowerShell Get-PhysicalDisk"
        for row in _as_list(data):
            out["disks"].append({
                "device": (row.get("FriendlyName") or "").strip(),
                "health": row.get("HealthStatus"),
                "status": row.get("OperationalStatus"),
                "serial": (row.get("SerialNumber") or "").strip(),
                "media": row.get("MediaType"),
                "temperature_c": None,
            })
        return out

    diskutil = _which("diskutil")
    if diskutil:
        text = _run([diskutil, "list"]) or ""
        out["method"] = "diskutil (SMART not exposed without smartctl)"
        for line in text.splitlines():
            if line.startswith("/dev/disk"):
                device = line.split()[0]
                verified = "unknown"
                info = _run([diskutil, "info", device]) or ""
                for sub in info.splitlines():
                    if "SMART Status" in sub:
                        verified = sub.split(":")[-1].strip()
                out["disks"].append({"device": device, "health": verified,
                                     "temperature_c": None})
        return out

    out["method"] = "unavailable"
    return out


# --------------------------------------------------------------------------- #
# Common options
# --------------------------------------------------------------------------- #
def _add_common(p: argparse.ArgumentParser, limit: Optional[int] = None) -> None:
    p.add_argument("--json", action="store_true", help="emit JSON")
    p.add_argument("--out", metavar="FILE", help="write JSON / report here")
    p.add_argument("--no-color", action="store_true")
    p.add_argument("-q", "--quiet", action="store_true")
    if limit is not None:
        p.add_argument("-n", "--limit", type=int, default=limit,
                       help=f"rows to print (default: {limit})")


def _emit(obj: Any, args: argparse.Namespace) -> Optional[str]:
    if getattr(args, "json", False) or getattr(args, "out", None):
        text = json.dumps(obj, indent=2, ensure_ascii=False, default=str)
        if getattr(args, "out", None):
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"written: {args.out}")
        else:
            print(text)
        return text
    return None


def _bar(percent: float, width: int = 30, color: bool = True) -> str:
    filled = int(round(min(max(percent, 0.0), 100.0) / 100.0 * width))
    bar = "#" * filled + "." * (width - filled)
    if not color:
        return bar
    return f"\033[36m{bar}\033[0m"


# --------------------------------------------------------------------------- #
# 1. diskinfo
# --------------------------------------------------------------------------- #
def _parser_info() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge diskinfo",
                                description="Physical disks in this machine.")
    _add_common(p)
    return p


def cmd_info(args: argparse.Namespace) -> int:
    disks = physical_disks()
    payload = {"platform": platform_name(), "disks": disks}
    if _emit(payload, args):
        return 0
    print(f"Physical disks ({platform_name()}) - {len(disks)} found:")
    for disk in disks:
        print(f"\n  {disk.get('id')}  {disk.get('model') or '(unknown model)'}")
        if disk.get("media"):
            print(f"    media      {disk['media']}")
        if disk.get("bus"):
            print(f"    bus        {disk['bus']}")
        if disk.get("size"):
            print(f"    size       {human_size(disk['size'])}")
        if disk.get("serial"):
            print(f"    serial     {disk['serial']}")
        if disk.get("health"):
            print(f"    health     {disk['health']}")
        if disk.get("status"):
            print(f"    status     {disk['status']}")
    return 0


# --------------------------------------------------------------------------- #
# 2. diskpartitions
# --------------------------------------------------------------------------- #
def _parser_partitions() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge diskpartitions",
                                description="Partition / volume table.")
    _add_common(p)
    return p


def cmd_partitions(args: argparse.Namespace) -> int:
    volumes = volumes_fs()
    if _emit({"volumes": volumes}, args):
        return 0
    print(f"Volumes / partitions ({len(volumes)}):")
    print(f"  {'mount':<26}{'fstype':<10}{'size':>12}{'used':>12}{'free':>12}")
    for row in volumes:
        total = row.get("total") or 0
        used = row.get("used") or 0
        free = row.get("free") or 0
        print(f"  {row['mount']:<26}{(row.get('fstype') or '-'):<10}"
              f"{human_size(total):>12}{human_size(used):>12}"
              f"{human_size(free):>12}")
    return 0


# --------------------------------------------------------------------------- #
# 3. diskfs
# --------------------------------------------------------------------------- #
def _parser_fs() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge diskfs",
                                description="File system of every mount point.")
    _add_common(p)
    return p


def cmd_fs(args: argparse.Namespace) -> int:
    volumes = volumes_fs()
    if _emit({"volumes": volumes}, args):
        return 0
    print("File systems:")
    for row in volumes:
        fstype = row.get("fstype") or "unknown"
        label = f" ({row['label']})" if row.get("label") else ""
        extra = ""
        if row.get("health"):
            extra = f"   health: {row['health']}"
        if row.get("drive_type") is not None:
            extra += f"   type: {row['drive_type']}"
        print(f"  {row['mount']:<26}{fstype:<12}{label}{extra}")
    return 0


# --------------------------------------------------------------------------- #
# 4. diskusage
# --------------------------------------------------------------------------- #
def _parser_usage() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge diskusage",
                                description="Used vs free per volume.")
    p.add_argument("--width", type=int, default=76)
    p.add_argument("--mode", choices=["blocks", "table", "both"], default="both")
    _add_common(p)
    return p


def cmd_usage(args: argparse.Namespace) -> int:
    volumes = volumes_fs()
    rows: List[Tuple[str, int]] = [(v["mount"], v.get("used") or 0)
                                   for v in volumes if v.get("total")]
    rows.sort(key=lambda r: r[1], reverse=True)
    payload = {"volumes": volumes,
               "total_used": sum(r[1] for r in rows),
               "total_capacity": sum(v.get("total") or 0 for v in volumes)}
    if _emit(payload, args):
        return 0

    if args.mode in ("blocks", "both"):
        print(f"\nUsed space per volume "
              f"({human_size(sum(r[1] for r in rows))} of "
              f"{human_size(sum(v.get('total') or 0 for v in volumes))}):")
        for line in render_blocks(rows, width=args.width,
                                  color=not args.no_color):
            print(line)
    if args.mode in ("table", "both"):
        print(f"  {'mount':<26}{'used':>12}{'free':>12}{'capacity':>12}   use")
        for row in volumes:
            total = row.get("total") or 0
            used = row.get("used") or 0
            free = row.get("free") or 0
            pct = (used * 100.0 / total) if total else 0
            print(f"  {row['mount']:<26}{human_size(used):>12}"
                  f"{human_size(free):>12}{human_size(total):>12}"
                  f"   {_bar(pct, 20, not args.no_color)} {pct:5.1f}%")
    return 0


# --------------------------------------------------------------------------- #
# 5. diskfree
# --------------------------------------------------------------------------- #
def _parser_free() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge diskfree",
                                description="Free space + low-space warning.")
    p.add_argument("--threshold", type=float, default=10.0,
                   help="warn when free space is below this percent "
                        "(default: 10)")
    _add_common(p)
    return p


def cmd_free(args: argparse.Namespace) -> int:
    volumes = volumes_fs()
    warnings = []
    for row in volumes:
        total = row.get("total") or 0
        free = row.get("free") or 0
        pct = (free * 100.0 / total) if total else None
        row["percent_free"] = round(pct, 2) if pct is not None else None
        if pct is not None and pct < args.threshold:
            warnings.append(row["mount"])
    payload = {"volumes": volumes, "threshold_percent": args.threshold,
               "low": warnings}
    if _emit(payload, args):
        return 0

    total_free = sum(v.get("free") or 0 for v in volumes)
    total_cap = sum(v.get("total") or 0 for v in volumes)
    print(f"Free space: {human_size(total_free)} of {human_size(total_cap)}")
    for row in volumes:
        total = row.get("total") or 0
        free = row.get("free") or 0
        pct = row["percent_free"]
        mark = "  LOW" if pct is not None and pct < args.threshold else ""
        shown = f"{pct:5.1f}%" if pct is not None else "   n/a"
        print(f"  {row['mount']:<26}{human_size(free):>12} free of "
              f"{human_size(total):>12}  ({shown}){mark}")
    if warnings:
        print(f"\nWARNING: below {args.threshold}% free: "
              f"{', '.join(warnings)}")
    else:
        print(f"\nno volume is below {args.threshold}% free")
    return 0


# --------------------------------------------------------------------------- #
# 6. diskio
# --------------------------------------------------------------------------- #
def _parser_io() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge diskio",
                                description="Disk I/O counters.")
    _add_common(p, limit=20)
    return p


def cmd_io(args: argparse.Namespace) -> int:
    rows = io_counters()
    if _emit({"counters": rows}, args):
        return 0
    if not rows:
        print("diskio: no I/O counters available on this platform. "
              "Use `fileforge diskbench` to measure throughput directly.")
        return 0
    print(f"I/O counters ({len(rows)} devices):")
    for row in rows[:max(1, args.limit)]:
        if "read_bytes" in row:
            print(f"  {row['device']:<16} reads {row['reads']:>12,}  "
                  f"{human_size(row['read_bytes']):>12}   "
                  f"writes {row['writes']:>12,}  "
                  f"{human_size(row['write_bytes']):>12}")
        else:
            detail = "  ".join(f"{k}={v}" for k, v in row.items()
                               if k != "device")
            print(f"  {row['device']:<16} {detail}")
    return 0


# --------------------------------------------------------------------------- #
# 7. diskhealth
# --------------------------------------------------------------------------- #
def _parser_health() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge diskhealth",
                                description="SMART / health status.")
    _add_common(p)
    return p


def cmd_health(args: argparse.Namespace) -> int:
    report = smart_report()
    if _emit(report, args):
        return 0
    print(f"Disk health (method: {report['method']}):")
    if not report["disks"]:
        print("  no disk reported - install smartctl for real SMART data")
        return 0
    for disk in report["disks"]:
        line = f"  {disk.get('device'):<24}"
        if disk.get("health"):
            line += f" {disk['health']}"
        if disk.get("status"):
            line += f" / {disk['status']}"
        if disk.get("temperature_c"):
            line += f"  {disk['temperature_c']} C"
        print(line)
    return 0


# --------------------------------------------------------------------------- #
# 8. disktemp
# --------------------------------------------------------------------------- #
def _parser_temp() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge disktemp",
                                description="Disk temperature, if available.")
    _add_common(p)
    return p


def cmd_temp(args: argparse.Namespace) -> int:
    report = smart_report()
    temps = [d for d in report["disks"] if d.get("temperature_c") is not None]
    if _emit({"method": report["method"], "temperatures": temps}, args):
        return 0
    if not temps:
        print("disktemp: this platform does not expose disk temperature "
              "(needs smartctl, or a sensor tool on Windows).")
        return 0
    for disk in temps:
        print(f"  {disk['device']:<24} {disk['temperature_c']} C")
    return 0


# --------------------------------------------------------------------------- #
# 9. diskbench
# --------------------------------------------------------------------------- #
def _parser_bench() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge diskbench",
                                description="Measure real disk throughput.")
    p.add_argument("--dir", help="where to write the test file "
                                 "(default: the system temp dir)")
    p.add_argument("--size", default="64M",
                   help="total bytes to write (default: 64M)")
    p.add_argument("--block", default="1M", help="block size (default: 1M)")
    p.add_argument("--iops-block", default="4K",
                   help="block size for the small-IO test (default: 4K)")
    p.add_argument("--iops-count", type=int, default=2000,
                   help="small writes for the IOPS estimate (default: 2000)")
    p.add_argument("--no-iops", action="store_true",
                   help="skip the small-block test")
    p.add_argument("--keep", action="store_true",
                   help="do not delete the test file")
    p.add_argument("--json", action="store_true")
    p.add_argument("--out", metavar="FILE")
    p.add_argument("-q", "--quiet", action="store_true")
    return p


def _to_bytes(text: str) -> int:
    raw = str(text).strip().lower().replace(" ", "")
    units = {"b": 1, "k": 1024, "kb": 1024, "m": 1024 ** 2, "mb": 1024 ** 2,
             "g": 1024 ** 3, "gb": 1024 ** 3, "t": 1024 ** 4, "tb": 1024 ** 4}
    for suffix in sorted(units, key=len, reverse=True):
        if raw.endswith(suffix):
            try:
                return int(float(raw[: -len(suffix)]) * units[suffix])
            except ValueError:
                return 0
    try:
        return int(float(raw))
    except ValueError:
        return 0


def benchmark(directory: str, total: int, block: int,
              iops_block: int = 4096, iops_count: int = 2000,
              do_iops: bool = True) -> Dict[str, Any]:
    """Write, read and (optionally) small-block test in ``directory``."""
    target = Path(directory) / f"ff-bench-{os.getpid()}-{int(time.time())}.tmp"
    payload_block = os.urandom(block)

    written = 0
    start = time.time()
    with target.open("wb") as fh:
        while written < total:
            fh.write(payload_block)
            written += len(payload_block)
        fh.flush()
        os.fsync(fh.fileno())
    write_sec = max(time.time() - start, 1e-6)

    read = 0
    start = time.time()
    with target.open("rb") as fh:
        while True:
            chunk = fh.read(block)
            if not chunk:
                break
            read += len(chunk)
    read_sec = max(time.time() - start, 1e-6)

    iops = None
    if do_iops:
        small = os.urandom(iops_block)
        start = time.time()
        with target.open("r+b") as fh:
            for index in range(iops_count):
                fh.seek((index * iops_block) % max(written, iops_block))
                fh.write(small)
            fh.flush()
            os.fsync(fh.fileno())
        iops_sec = max(time.time() - start, 1e-6)
        iops = {"writes": iops_count, "block": iops_block,
                "seconds": round(iops_sec, 3),
                "iops": round(iops_count / iops_sec, 1)}

    size = target.stat().st_size
    result = {
        "dir": str(directory),
        "file": str(target),
        "size": size,
        "block": block,
        "write_mb_s": round(written / (1 << 20) / write_sec, 2),
        "write_seconds": round(write_sec, 3),
        "read_mb_s": round(read / (1 << 20) / read_sec, 2),
        "read_seconds": round(read_sec, 3),
        "iops": iops,
    }
    return result


def cmd_bench(args: argparse.Namespace) -> int:
    directory = Path(args.dir).expanduser() if args.dir \
        else Path(tempfile.gettempdir())
    if not directory.is_dir():
        print(f"diskbench: no such directory: {directory}", file=sys.stderr)
        return 1
    total = _to_bytes(args.size)
    block = _to_bytes(args.block)
    if total <= 0 or block <= 0:
        print("diskbench: --size and --block must be positive", file=sys.stderr)
        return 2

    try:
        result = benchmark(str(directory), total, block,
                           iops_block=_to_bytes(args.iops_block) or 4096,
                           iops_count=args.iops_count,
                           do_iops=not args.no_iops)
    except OSError as exc:
        print(f"diskbench: {exc}", file=sys.stderr)
        return 1

    if not args.keep:
        try:
            Path(result["file"]).unlink()
        except OSError:
            pass
        result["file_removed"] = True

    if _emit(result, args):
        return 0
    print(f"diskbench in {directory} "
          f"({human_size(result['size'])}, block {human_size(block)}):")
    print(f"  sequential write   {result['write_mb_s']:>10.2f} MB/s"
          f"   ({result['write_seconds']}s)")
    print(f"  sequential read    {result['read_mb_s']:>10.2f} MB/s"
          f"   ({result['read_seconds']}s, may include page cache)")
    if result.get("iops"):
        print(f"  random {human_size(result['iops']['block'])} write  "
              f"{result['iops']['iops']:>10.1f} IOPS")
    return 0


# --------------------------------------------------------------------------- #
# 10. diskserial
# --------------------------------------------------------------------------- #
def _parser_serial() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge diskserial",
                                description="Volume serial numbers / UUIDs.")
    _add_common(p)
    return p


def cmd_serial(args: argparse.Namespace) -> int:
    rows = volume_serials()
    if _emit({"volumes": rows}, args):
        return 0
    print("Volume identifiers:")
    for row in rows:
        print(f"  {row.get('mount',''):<26}"
              f"{(row.get('serial') or '-'):<40}"
              f"{(row.get('fstype') or ''):<10}{row.get('label') or ''}")
    return 0


# --------------------------------------------------------------------------- #
# 11. diskbadfiles
# --------------------------------------------------------------------------- #
def _parser_bad() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge diskbadfiles",
                                description="Files that cannot be read.")
    p.add_argument("-r", "--root", action="append", default=[],
                   help="root to scan (repeatable; default: current dir)")
    p.add_argument("-a", "--all", action="store_true", help="include hidden")
    p.add_argument("--max-items", type=int, default=20000)
    p.add_argument("--full", action="store_true",
                   help="read every byte instead of the first block")
    p.add_argument("-n", "--limit", type=int, default=50)
    p.add_argument("--json", action="store_true")
    p.add_argument("--out", metavar="FILE")
    p.add_argument("-q", "--quiet", action="store_true")
    return p


def cmd_bad(args: argparse.Namespace) -> int:
    roots = [str(Path(r).expanduser()) for r in args.root] or [str(Path.cwd())]
    opts = Options(max_depth=64, include_hidden=args.all)
    started = time.time()
    bad: List[Dict[str, Any]] = []
    checked = 0
    for root in roots:
        stack: List[Tuple[Path, int]] = [(Path(root), 0)]
        while stack:
            path, depth = stack.pop()
            if depth >= 64:
                continue
            items, error, _hidden = _list_dir(path, opts, depth + 1)
            if error:
                bad.append({"path": str(path), "kind": "directory",
                            "error": error})
            for node in items:
                if node.is_dir:
                    stack.append((node.path, depth + 1))
                    continue
                checked += 1
                try:
                    with node.path.open("rb") as fh:
                        if args.full:
                            while fh.read(1 << 20):
                                pass
                        else:
                            fh.read(4096)
                except OSError as exc:
                    bad.append({"path": str(node.path), "kind": "file",
                                "error": f"{type(exc).__name__}: {exc}"})
                if not args.quiet and checked % 500 == 0:
                    sys.stderr.write(f"\r  checked {checked:,} files...")
                    sys.stderr.flush()
                if len(bad) >= args.limit:
                    break
            if len(bad) >= args.limit:
                break
    if not args.quiet:
        sys.stderr.write("\r" + " " * 50 + "\r")
        sys.stderr.flush()

    payload = {"checked": checked, "bad": bad[:args.limit],
               "bad_count": len(bad), "elapsed_sec": round(time.time() - started, 3)}
    if _emit(payload, args):
        return 0
    print(f"diskbadfiles: {checked:,} files checked in "
          f"{payload['elapsed_sec']}s, {len(bad)} unreadable")
    for row in bad[:args.limit]:
        print(f"  [{row['kind']}] {row['path']}\n      {row['error']}")
    return 0


# --------------------------------------------------------------------------- #
# 12. diskerrors
# --------------------------------------------------------------------------- #
def _parser_errors() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge diskerrors",
                                description="Directories that fail to list.")
    p.add_argument("-r", "--root", action="append", default=[])
    p.add_argument("-a", "--all", action="store_true")
    p.add_argument("--max-dirs", type=int, default=20000)
    p.add_argument("-n", "--limit", type=int, default=50)
    p.add_argument("--json", action="store_true")
    p.add_argument("--out", metavar="FILE")
    p.add_argument("-q", "--quiet", action="store_true")
    return p


def cmd_errors(args: argparse.Namespace) -> int:
    roots = [str(Path(r).expanduser()) for r in args.root] or [str(Path.cwd())]
    opts = Options(max_depth=64, include_hidden=args.all)
    started = time.time()
    failures: List[Dict[str, Any]] = []
    seen = 0
    for root in roots:
        stack: List[Tuple[Path, int]] = [(Path(root), 0)]
        while stack:
            path, depth = stack.pop()
            if depth >= 64:
                continue
            items, error, _hidden = _list_dir(path, opts, depth + 1)
            seen += 1
            if error:
                failures.append({"path": str(path), "error": error})
            for node in items:
                if node.is_dir:
                    stack.append((node.path, depth + 1))
            if seen >= args.max_dirs or len(failures) >= args.limit:
                break
    payload = {"scanned_dirs": seen, "failures": failures[:args.limit],
               "failure_count": len(failures),
               "elapsed_sec": round(time.time() - started, 3)}
    if _emit(payload, args):
        return 0
    print(f"diskerrors: {seen:,} directories scanned, "
          f"{len(failures)} unlistable ({payload['elapsed_sec']}s)")
    for row in failures[:args.limit]:
        print(f"  {row['path']}\n      {row['error']}")
    return 0


# --------------------------------------------------------------------------- #
# 13. disktop
# --------------------------------------------------------------------------- #
def _parser_top() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge disktop",
                                description="Biggest entries under a root.")
    p.add_argument("-r", "--root", action="append", default=[],
                   help="root(s); default: the current directory")
    p.add_argument("-n", "--limit", type=int, default=20)
    p.add_argument("-a", "--all", action="store_true")
    p.add_argument("--max-items", type=int, default=200000)
    p.add_argument("--no-aggregate", action="store_true",
                   help="report the entry size only (fast, no recursion)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--out", metavar="FILE")
    p.add_argument("-q", "--quiet", action="store_true")
    return p


def cmd_top(args: argparse.Namespace) -> int:
    roots = [str(Path(r).expanduser()) for r in args.root] or [str(Path.cwd())]
    opts = Options(max_depth=64, include_hidden=args.all)
    started = time.time()
    rows: List[Tuple[str, int, int]] = []

    for root in roots:
        base = Path(root)
        items, error, _hidden = _list_dir(base, opts, 1)
        if error:
            print(f"disktop: {error}", file=sys.stderr)
            continue
        if args.no_aggregate:
            for node in items:
                rows.append((str(node.path), node.size,
                             1 if not node.is_dir else 0))
            continue
        for node in items:
            if not node.is_dir:
                rows.append((str(node.path), node.size, 1))
                continue
            total = 0
            count = 0
            stack: List[Tuple[Path, int]] = [(node.path, 1)]
            produced = 0
            while stack:
                path, depth = stack.pop()
                if depth >= 64:
                    continue
                children, _err, _hidden = _list_dir(path, opts, depth + 1)
                for child in children:
                    if child.is_dir:
                        stack.append((child.path, depth + 1))
                    else:
                        total += child.size
                        count += 1
                        produced += 1
                        if produced >= args.max_items:
                            stack.clear()
                            break
            rows.append((str(node.path), total, count))
    rows.sort(key=lambda r: r[1], reverse=True)
    rows = rows[:max(1, args.limit)]

    payload = {"roots": roots,
               "rows": [{"path": p, "size": s, "files": f} for p, s, f in rows],
               "elapsed_sec": round(time.time() - started, 3)}
    if _emit(payload, args):
        return 0
    print(f"Biggest entries ({time.time() - started:.2f}s):")
    for path, size, count in rows:
        print(f"{human_size(size):>12}  {count:>8,} f   {path}")
    return 0


# --------------------------------------------------------------------------- #
# 14. diskmounts
# --------------------------------------------------------------------------- #
def _parser_mounts() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fileforge diskmounts",
                                description="Mount points and drive types.")
    _add_common(p)
    return p


def cmd_mounts(args: argparse.Namespace) -> int:
    rows: List[Dict[str, Any]] = []
    for root in system_roots():
        entry: Dict[str, Any] = {"mount": root, "kind": None,
                                 "total": 0, "free": 0}
        try:
            total, _used, free = free_space(Path(root))
            entry["total"] = total
            entry["free"] = free
        except OSError:
            entry["error"] = "unavailable"
        if IS_WINDOWS:
            try:
                import ctypes
                kind = ctypes.windll.kernel32.GetDriveTypeW(root[:3])
                entry["kind"] = {0: "unknown", 1: "no-root", 2: "removable",
                                 3: "fixed", 4: "network", 5: "cdrom",
                                 6: "ramdisk"}.get(kind, "unknown")
            except Exception:  # noqa: BLE001 - ctypes is not always usable
                entry["kind"] = None
        else:
            entry["kind"] = "network" if root.startswith(("/net", "/mnt/remote")) \
                else ("removable" if "/media" in root or "/Volumes" in root
                      else "fixed")
        rows.append(entry)

    if _emit({"mounts": rows}, args):
        return 0
    print(f"Mount points ({len(rows)}):")
    for row in rows:
        kind = row.get("kind") or "-"
        if row.get("error"):
            print(f"  {row['mount']:<26}{kind:<12}{row['error']}")
        else:
            print(f"  {row['mount']:<26}{kind:<12}"
                  f"{human_size(row['free']):>12} free of "
                  f"{human_size(row['total']):>12}")
    return 0


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
PARSERS: Dict[str, Callable[[], argparse.ArgumentParser]] = {
    "diskinfo": _parser_info,
    "diskpartitions": _parser_partitions,
    "diskfs": _parser_fs,
    "diskusage": _parser_usage,
    "diskfree": _parser_free,
    "diskio": _parser_io,
    "diskhealth": _parser_health,
    "disktemp": _parser_temp,
    "diskbench": _parser_bench,
    "diskserial": _parser_serial,
    "diskbadfiles": _parser_bad,
    "diskerrors": _parser_errors,
    "disktop": _parser_top,
    "diskmounts": _parser_mounts,
}

HANDLERS: Dict[str, Callable[[argparse.Namespace], int]] = {
    "diskinfo": cmd_info,
    "diskpartitions": cmd_partitions,
    "diskfs": cmd_fs,
    "diskusage": cmd_usage,
    "diskfree": cmd_free,
    "diskio": cmd_io,
    "diskhealth": cmd_health,
    "disktemp": cmd_temp,
    "diskbench": cmd_bench,
    "diskserial": cmd_serial,
    "diskbadfiles": cmd_bad,
    "diskerrors": cmd_errors,
    "disktop": cmd_top,
    "diskmounts": cmd_mounts,
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
        print(f"{APP}: diskkit has no command {args[0]!r}", file=sys.stderr)
        return 2
    return run(name, args[1:])


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
