#!/usr/bin/env python3
"""End-to-end checks for fileforge.filekit (single-file tools).

Runs against a throw-away directory: every parser is built (this is what
catches duplicate argparse options), `--help` is exercised, then each command
is run for real and its output asserted.
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

from fileforge import filekit  # noqa: E402

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
        rc = filekit.run(name, argv)
    except SystemExit as exc:
        rc = int(exc.code or 0)
    finally:
        sys.stdout = old
    return rc, buf.getvalue()


def main() -> int:
    print("== registry ==")
    kit = set(filekit.HANDLERS)
    check("12 file commands registered", len(kit) == 12, str(len(kit)))
    check("parsers match handlers", set(filekit.PARSERS) == kit)
    check("every alias points at a real command",
          all(t in kit for t in filekit.ALIASES.values()),
          str({t: v for t, v in filekit.ALIASES.items() if v not in kit}))
    check("every command documented in SPEC",
          kit.issubset(set(filekit.command_names())),
          str(kit - set(filekit.command_names())))

    print("== parsers build ==")
    for name in sorted(filekit.PARSERS):
        try:
            check(f"{name} parser builds", filekit.PARSERS[name]() is not None)
        except Exception as exc:  # noqa: BLE001
            check(f"{name} parser builds", False, repr(exc))

    print("== --help ==")
    for name in sorted(kit):
        rc, out = run(name, ["--help"])
        check(f"{name} --help", rc == 0 and "usage" in out.lower(), out[:80])

    base = Path(tempfile.mkdtemp(prefix="ff-filekit-"))
    try:
        text = base / "notes.txt"
        text.write_text("b\na\nc\na\n\n  spaced  \n"
                        "http://x.com/a me@example.com 10.0.0.1\n",
                        encoding="utf-8")
        (base / "sub").mkdir()
        (base / "sub" / "inner.txt").write_text("inner\n", encoding="utf-8")
        binary = base / "data.bin"
        binary.write_bytes(bytes(range(0, 48)))

        print("== filemeta ==")
        rc, out = run("filemeta", [str(text), "--hash", "sha256"])
        check("filemeta reports type", rc == 0 and "file" in out, out[:120])
        check("filemeta includes a sha256", len([l for l in out.splitlines()
                                                 if "hash" in l]) >= 1, out[:200])
        rc, out = run("filemeta", [str(base), "--json"])
        check("filemeta json works for a dir",
              rc == 0 and '"type": "directory"' in out, out[:160])

        print("== filepreview ==")
        rc, out = run("filepreview", [str(text), "--lines", "3"])
        check("preview shows numbered lines", rc == 0 and "1:" in out, out[:120])
        rc, out = run("filepreview", [str(binary)])
        check("preview hexes a binary", rc == 0 and "00000000" in out, out[:120])
        rc, out = run("filepreview", [str(base)])
        check("preview lists a directory", rc == 0 and "sub" in out, out[:120])

        print("== filehex ==")
        rc, out = run("filehex", [str(binary), "--length", "32", "--width", "8"])
        check("hexdump has 4 rows", rc == 0 and len(out.strip().splitlines()) == 4,
              out[:200])
        rc, out = run("filehex", [str(binary), "--offset", "16", "--length", "8"])
        check("hexdump honours the offset",
              rc == 0 and out.startswith("00000010"), out[:80])

        print("== filediff ==")
        other = base / "other.txt"
        other.write_text("b\na\nX\na\n", encoding="utf-8")
        rc, out = run("filediff", [str(text), str(other), "--unified"])
        check("diff finds the change", rc == 0 and "-c" in out and "+X" in out,
              out[:200])
        rc, out = run("filediff", [str(text), str(text)])
        check("identical files report as identical",
              rc == 0 and "identical" in out, out[:120])
        rc, out = run("filediff", [str(base), str(base / "sub")])
        check("dir inventory diff runs", rc == 0 and "only in A" in out,
              out[:200])

        print("== name tools ==")
        rc, out = run("filesanitize", ["bad:name?.txt", "ok.txt", "--windows"])
        check("sanitize flags the illegal name",
              rc == 0 and "illegal" in out and "ok.txt" in out, out[:300])
        rc, out = run("filenorm", ["My File Name.TXT", "--space",
                                   "underscore", "--case", "lower"])
        check("norm proposes a new name",
              rc == 0 and "my_file_name.txt" in out, out[:200])

        print("== content tools ==")
        rc, out = run("fileextract", [str(text), "--all"])
        check("extract finds the url", "http://x.com/a" in out, out[:200])
        check("extract finds the mail", "me@example.com" in out, out[:200])
        check("extract finds the ip", "10.0.0.1" in out, out[:200])

        enc_out = base / "enc.txt"
        rc, out = run("fileencode", [str(binary), "--hex", "-o", str(enc_out)])
        check("encode writes a file", rc == 0 and enc_out.is_file(), out[:120])
        dec_out = base / "dec.bin"
        rc, out = run("filedecode", [str(enc_out), "--hex", "-o", str(dec_out)])
        check("decode round-trips",
              rc == 0 and dec_out.read_bytes() == binary.read_bytes(), out[:120])

        print("== housekeeping ==")
        rc, out = run("filetrim", [str(text), "--all", "-o",
                                   str(base / "trim.txt")])
        trimmed = (base / "trim.txt").read_text(encoding="utf-8")
        check("trim drops blank lines", rc == 0 and "\n\n" not in trimmed,
              trimmed[:120])
        check("trim strips trailing spaces",
              "spaced" in trimmed and "  spaced  " not in trimmed, trimmed[:120])

        rc, out = run("filesort", [str(text), "--unique", "-o",
                                   str(base / "sorted.txt")])
        lines = (base / "sorted.txt").read_text(encoding="utf-8").splitlines()
        letters = [ln for ln in lines if ln.strip() in ("a", "b", "c")]
        check("sort orders the lines", rc == 0 and letters == ["a", "b", "c"],
              str(lines[:6]))
        check("sort --unique drops the duplicate",
              len([ln for ln in lines if ln.strip() == "a"]) == 1, str(lines))

        rc, out = run("filebackup", [str(text), "--keep", "2"])
        backups = list(base.glob("notes.txt.bak-*"))
        check("backup creates a timestamped copy",
              rc == 0 and len(backups) == 1, out[:120])
        rc, out = run("filebackup", [str(text), "--keep", "1"])
        check("backup prunes when --keep is set",
              rc == 0 and len(list(base.glob("notes.txt.bak-*"))) == 1,
              out[:160])
    finally:
        shutil.rmtree(base, ignore_errors=True)

    print()
    print("=" * 46)
    print(f"  FILEKIT TOTAL: {PASSED} passed, {FAILED} failed")
    print("=" * 46)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
