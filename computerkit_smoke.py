#!/usr/bin/env python3
"""End-to-end checks for fileforge.computerkit (the "This PC" commands).

Every command is exercised against a throw-away directory so the suite never
touches a real drive.  Each check builds the real argparse parser (this is
what catches duplicate-option mistakes) and runs the real handler.
"""

from __future__ import annotations

import io
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from fileforge import computerkit  # noqa: E402

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
    """Run one computerkit command, capturing stdout."""
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        rc = computerkit.run(name, argv)
    except SystemExit as exc:  # argparse --help
        rc = int(exc.code or 0)
    finally:
        sys.stdout = old
    return rc, buf.getvalue()


def build_fixture() -> Path:
    """A small directory tree: duplicates, an empty file, an empty folder."""
    base = Path(tempfile.mkdtemp(prefix="ff-kit-"))
    (base / "alpha").mkdir()
    (base / "beta").mkdir()
    (base / "gamma").mkdir()
    (base / "empty").mkdir()
    (base / "alpha" / "one.txt").write_text("hello world\n" * 100, encoding="utf-8")
    (base / "alpha" / "two.txt").write_text("hello world\n" * 100, encoding="utf-8")
    (base / "beta" / "big.bin").write_bytes(b"\0" * 5000)
    (base / "beta" / "empty.txt").write_text("", encoding="utf-8")
    (base / "gamma" / "note.tmp").write_bytes(b"junk" * 10)
    (base / "gamma" / "code.py").write_text(
        "def main():\n    print('hi')\n", encoding="utf-8")
    return base


def main() -> int:
    print("== registry ==")
    kit = set(computerkit.HANDLERS)
    check("21 This PC commands registered", len(kit) == 21, str(len(kit)))
    check("parsers match handlers", set(computerkit.PARSERS) == kit)
    # computerui / computer / treeui live in the dispatcher, not here.
    delegated = {"computerui", "computer", "treeui"}
    check("every alias points at a real command",
          all(t in kit or t in delegated for t in computerkit.ALIASES.values()),
          str({t: v for t, v in computerkit.ALIASES.items()
               if v not in kit and v not in delegated}))
    check("every command is documented in SPEC",
          kit.issubset(set(computerkit.command_names())),
          str(kit - set(computerkit.command_names())))

    print("== parsers build (no duplicate options) ==")
    for name in sorted(computerkit.PARSERS):
        try:
            parser = computerkit.PARSERS[name]()
            check(f"{name} parser builds", parser is not None)
        except Exception as exc:  # noqa: BLE001 - argparse raises on conflicts
            check(f"{name} parser builds", False, repr(exc))

    print("== --help works for every command ==")
    for name in sorted(kit):
        rc, out = run(name, ["--help"])
        check(f"{name} --help", rc == 0 and "usage" in out.lower(),
              out[:80])

    base = build_fixture()
    root = ["-r", str(base), "-q", "--max-items", "5000", "-a"]
    try:
        print("== inventory ==")
        rc, out = run("computerscan", root)
        check("computerscan runs", rc == 0, out[:120])
        check("computerscan counted files", "files:" in out, out[:200])

        rc, out = run("computerinfo", ["--json"])
        check("computerinfo json", rc == 0 and '"volumes"' in out, out[:120])

        rc, out = run("computerdrives", [])
        check("computerdrives lists drives",
              rc == 0 and "free of" in out, out[:120])

        rc, out = run("computerexport",
                      root + ["--format", "json", "--out",
                              str(base / "export.json")])
        check("computerexport json", rc == 0 and (base / "export.json").is_file(),
              out[:120])

        rc, out = run("computerexport",
                      root + ["--format", "csv", "--out",
                              str(base / "export.csv")])
        check("computerexport csv", rc == 0 and (base / "export.csv").is_file(),
              out[:120])

        print("== what is big ==")
        rc, out = run("computerlarge", root + ["-n", "3"])
        check("computerlarge finds the biggest file",
              rc == 0 and "big.bin" in out, out[:200])

        rc, out = run("computerdirs", root + ["-n", "5"])
        check("computerdirs ranks directories",
              rc == 0 and "alpha" in out, out[:200])

        rc, out = run("computerext", root + ["-n", "5"])
        check("computerext groups by extension",
              rc == 0 and ".txt" in out, out[:200])

        rc, out = run("computermap", ["-r", str(base), "--no-color"])
        check("computermap renders", rc == 0 and "Ranked usage" in out,
              out[:120])

        print("== by age ==")
        rc, out = run("computernew", root + ["-n", "2"])
        check("computernew lists recent files", rc == 0 and "Largest" not in out,
              out[:120])
        rc, out = run("computerold", root + ["-n", "2"])
        check("computerold lists oldest files", rc == 0 and str(base) in out,
              out[:120])
        rc, out = run("computerempty", root + ["-n", "5"])
        check("computerempty finds the empty file",
              rc == 0 and "empty.txt" in out, out[:300])
        check("computerempty finds the empty dir", "empty" in out, out[:300])
        rc, out = run("computerstats", root + ["-n", "3"])
        check("computerstats reports buckets",
              rc == 0 and "by size:" in out and "by age" in out, out[:200])

        print("== search & integrity ==")
        rc, out = run("computerfind", ["*.txt"] + root + ["-n", "5"])
        check("computerfind matches names",
              rc == 0 and "one.txt" in out, out[:200])

        rc, out = run("computergrep", ["print"] + root + ["-n", "5"])
        check("computergrep finds content",
              rc == 0 and "code.py" in out, out[:300])

        rc, out = run("computerdupes", root + ["-n", "5"])
        check("computerdupes finds the duplicate pair",
              rc == 0 and "one.txt" in out and "two.txt" in out, out[:300])

        rc, out = run("computertemp", root + ["-n", "5"])
        check("computertemp flags the .tmp file",
              rc == 0 and "note.tmp" in out, out[:300])

        print("== track changes ==")
        snap1 = str(base / "snap1.json")
        snap2 = str(base / "snap2.json")
        rc, out = run("computersnapshot", root + ["--out", snap1])
        check("computersnapshot writes a file",
              rc == 0 and Path(snap1).is_file(), out[:120])
        (base / "alpha" / "three.txt").write_text("brand new\n", encoding="utf-8")
        (base / "beta" / "big.bin").write_bytes(b"\0" * 6000)
        (base / "gamma" / "note.tmp").unlink()
        time.sleep(0.01)
        rc, out = run("computersnapshot", root + ["--out", snap2])
        check("second snapshot written", rc == 0 and Path(snap2).is_file(),
              out[:120])
        rc, out = run("computerdiff", [snap1, snap2, "-n", "5"])
        check("computerdiff reports the new file",
              rc == 0 and "three.txt" in out, out[:300])
        check("computerdiff reports the removal", "note.tmp" in out, out[:300])
        check("computerdiff reports the change", "big.bin" in out, out[:300])

        rc, out = run("computerwatch",
                      [str(base), "--interval", "0.5", "--duration", "0.6",
                       "--max-items", "200", "-q"])
        check("computerwatch runs", rc == 0, out[:120])

        print("== safety ==")
        rc, out = run("computeraudit", root + ["-n", "5"])
        check("computeraudit runs", rc == 0 and "audit:" in out, out[:200])

        print("== whole-machine tree ==")
        rc, out = run("computertree", ["-r", str(base), "-L", "2", "--no-size"])
        check("computertree prints a tree",
              rc == 0 and "alpha" in out and "beta" in out, out[:200])
    finally:
        shutil.rmtree(base, ignore_errors=True)

    print()
    print("=" * 46)
    print(f"  COMPUTERKIT TOTAL: {PASSED} passed, {FAILED} failed")
    print("=" * 46)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
