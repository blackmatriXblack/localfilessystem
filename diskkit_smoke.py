#!/usr/bin/env python3
"""End-to-end checks for fileforge.diskkit (disk / volume tools).

Hardware probes are platform dependent, so the assertions only require that
each command runs, returns 0 and reports something sensible.  The walking
commands (`disktop`, `diskbadfiles`, `diskerrors`) are exercised against a
throw-away directory, and `diskbench` writes a tiny file.
"""

from __future__ import annotations

import io
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from fileforge import diskkit  # noqa: E402

PASSED = 0
FAILED = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print(f"  PASS  {label}")
    else:
        FAILED += 1
        print(f"  FAIL  {label}" + (f"  <- {detail}" if detail else ""))


def run(name: str, argv: list[str]) -> tuple[int, str]:
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        rc = diskkit.run(name, argv)
    except SystemExit as exc:
        rc = int(exc.code or 0)
    finally:
        sys.stdout = old
    return rc, buf.getvalue()


def main() -> int:
    print("== registry ==")
    kit = set(diskkit.HANDLERS)
    check("14 disk commands registered", len(kit) == 14, str(len(kit)))
    check("parsers match handlers", set(diskkit.PARSERS) == kit)
    check("every alias points at a real command",
          all(t in kit for t in diskkit.ALIASES.values()),
          str({t: v for t, v in diskkit.ALIASES.items() if v not in kit}))
    check("every command documented in SPEC",
          kit.issubset(set(diskkit.command_names())),
          str(kit - set(diskkit.command_names())))

    print("== parsers build ==")
    for name in sorted(diskkit.PARSERS):
        try:
            check(f"{name} parser builds", diskkit.PARSERS[name]() is not None)
        except Exception as exc:  # noqa: BLE001
            check(f"{name} parser builds", False, repr(exc))

    print("== --help ==")
    for name in sorted(kit):
        rc, out = run(name, ["--help"])
        check(f"{name} --help", rc == 0 and "usage" in out.lower(), out[:80])

    print("== hardware probes ==")
    for name, needle in (("diskinfo", "Physical disks"),
                         ("diskpartitions", "Volumes"),
                         ("diskfs", "File systems"),
                         ("diskusage", "volume"),
                         ("diskfree", "Free space"),
                         ("diskmounts", "Mount points"),
                         ("diskserial", "Volume identifiers"),
                         ("diskhealth", "Disk health"),
                         ("disktemp", ""),
                         ("diskio", "")):
        rc, out = run(name, ["--json"] if name in (
            "diskinfo", "diskpartitions", "diskfs", "diskusage", "diskfree",
            "diskmounts", "diskserial", "diskhealth") else [])
        check(f"{name} runs", rc == 0, out[:120])

    rc, out = run("diskfree", [])
    check("diskfree reports a total", rc == 0 and "Free space" in out, out[:120])
    rc, out = run("diskusage", ["--mode", "table"])
    check("diskusage table mode prints rows", rc == 0 and "use" in out,
          out[:200])
    rc, out = run("diskusage", ["--mode", "blocks"])
    check("diskusage blocks mode renders", rc == 0 and "█" in out, out[:120])
    rc, out = run("diskmounts", [])
    check("diskmounts lists at least one mount",
          rc == 0 and out.count("free of") >= 1, out[:200])

    print("== benchmark (tiny) ==")
    tmp = Path(tempfile.mkdtemp(prefix="ff-diskkit-"))
    try:
        rc, out = run("diskbench", ["--dir", str(tmp), "--size", "1M",
                                    "--block", "256K", "--iops-count", "50"])
        check("diskbench writes and reads", rc == 0 and "MB/s" in out, out[:200])
        leftovers = list(tmp.glob("ff-bench-*"))
        check("diskbench deletes its test file", not leftovers, str(leftovers))

        print("== walking commands ==")
        (tmp / "big").mkdir()
        (tmp / "small").mkdir()
        (tmp / "big" / "payload.bin").write_bytes(b"\0" * 4000)
        (tmp / "small" / "tiny.txt").write_text("hi\n", encoding="utf-8")
        (tmp / "root.txt").write_text("root\n", encoding="utf-8")

        rc, out = run("disktop", ["-r", str(tmp), "-n", "5", "-q"])
        check("disktop ranks the big folder first",
              rc == 0 and "big" in out.splitlines()[1], out[:200])

        rc, out = run("diskbadfiles", ["-r", str(tmp), "-q", "-n", "5"])
        check("diskbadfiles scans without false positives",
              rc == 0 and "0 unreadable" in out, out[:200])

        rc, out = run("diskerrors", ["-r", str(tmp), "-q", "-n", "5"])
        check("diskerrors reports no failures",
              rc == 0 and "0 unlistable" in out, out[:200])

        rc, out = run("disktop", ["-r", str(tmp), "--no-aggregate", "-n", "3"])
        check("disktop --no-aggregate works", rc == 0 and "root.txt" in out,
              out[:200])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print("=" * 46)
    print(f"  DISKKIT TOTAL: {PASSED} passed, {FAILED} failed")
    print("=" * 46)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
