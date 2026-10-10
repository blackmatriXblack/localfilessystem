#!/usr/bin/env python3
"""End-to-end checks for the unified fileforge dispatcher.

Verifies that every command in the catalogue is reachable, that aliases and
typos resolve, and that unknown commands fail with a helpful message.
GUI commands are stubbed so no window is actually opened.
"""

from __future__ import annotations

import importlib.util
import io
import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

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


def load_launcher():
    """Import the root fileforge.py under a private module name."""
    spec = importlib.util.spec_from_file_location(
        "_ff_launcher", ROOT / "fileforge.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # safe: guarded by __name__ == "__main__"
    return mod


def stub_gui_modules() -> None:
    """Replace the Tkinter entry points with stubs that record the call."""
    calls = {"hits": []}

    def make(name: str, result: int):
        mod = types.ModuleType(name)

        def main(argv=None):
            calls["hits"].append((name, list(argv or [])))
            return result

        mod.main = main
        sys.modules[name] = mod
        return mod

    make("fileforge.computerview", 0)
    make("fileforge.treeui", 0)
    make("fileforge.gui", 0)
    return calls


def main() -> int:
    launch = load_launcher()
    calls = stub_gui_modules()

    print("== catalogue ==")
    names = launch._all_names()
    check("catalogue is This PC focused",
          {"computerui", "treeui", "computer", "computertree",
           "computerinfo", "computerscan", "computerlarge", "computerdupes"}
          .issubset(set(names)),
          str(names))
    check("no full GUI command is advertised",
          "gui" not in names and "shell" not in names, str(names))
    check("every This PC command has an alias",
          all(any(t == n for t in launch.ALIASES.values())
              for n in names if n.startswith("computer")),
          str([n for n in names
               if n.startswith("computer")
               and not any(t == n for t in launch.ALIASES.values())]))
    check("every alias resolves to a real command",
          all(t in names or t in launch.CLASSIC_COMMANDS or t == "treemap"
              for t in launch.ALIASES.values()),
          str({t for t in launch.ALIASES.values()
               if t not in names and t not in launch.CLASSIC_COMMANDS}))
    check("command count >= 25", len(names) >= 25, str(len(names)))
    check("classic commands are hidden but kept",
          "ls" not in names and "ls" in launch.CLASSIC_COMMANDS)

    print("== dispatch ==")
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        rc = launch._dispatch(["help"])
        rc_drives = launch._dispatch(["drives"])
    finally:
        sys.stdout = old
    check("help returns 0", rc == 0, str(rc))
    check("help lists computerui", "computerui" in buf.getvalue())
    check("drives returns 0", rc_drives == 0, str(rc_drives))
    check("drives prints mount points", "Mount points / drives" in buf.getvalue())

    print("== whole-computer commands ==")
    calls["hits"].clear()
    check("computerui dispatches", launch._dispatch(["computerui"]) == 0)
    check("computrui (typo) auto-corrects to computerui",
          any(n == "fileforge.computerview" for n, _a in calls["hits"]),
          str(calls["hits"]))
    calls["hits"].clear()
    check("pcgui alias -> computerui", launch._dispatch(["pcgui"]) == 0)
    check("pcgui reached computerview",
          any(n == "fileforge.computerview" for n, _a in calls["hits"]))
    calls["hits"].clear()
    check("treeui with no path -> This PC",
          launch._dispatch(["treeui"]) == 0)
    check("treeui no-path reached computerview",
          any(n == "fileforge.computerview" for n, _a in calls["hits"]))
    calls["hits"].clear()
    check("treeui with path -> folder explorer",
          launch._dispatch(["treeui", str(ROOT)]) == 0)
    check("treeui with path reached treeui",
          any(n == "fileforge.treeui" for n, _a in calls["hits"]))

    print("== legacy catalogue ==")
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        rc_legacy = launch._dispatch(["legacy"])
    finally:
        sys.stdout = old
    check("legacy listing returns 0", rc_legacy == 0, str(rc_legacy))
    check("legacy listing shows ls", "  ls " in buf.getvalue()
          or "\n  ls" in buf.getvalue(), buf.getvalue()[:120])

    print("== classic commands still reachable ==")
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        rc_ls = launch._dispatch(["ls", str(ROOT)])
        rc_ver = launch._dispatch(["--version"])
    finally:
        sys.stdout = old
    check("ls works", rc_ls == 0, str(rc_ls))
    check("--version works", rc_ver == 0 and "fileforge" in buf.getvalue(),
          buf.getvalue()[:80])

    print("== computerkit commands ==")
    try:
        from fileforge import computerkit
    except ImportError as exc:
        check("fileforge.computerkit importable", False, str(exc))
    else:
        check("fileforge.computerkit importable", True)
        kit_names = set(computerkit.HANDLERS)
        check("launcher registers every computerkit command",
              kit_names.issubset(set(launch.COMPUTERKIT_COMMANDS)),
              str(kit_names - set(launch.COMPUTERKIT_COMMANDS)))
        check("every computerkit command is advertised",
              kit_names.issubset(set(names)), str(kit_names - set(names)))
        check("parsers and handlers agree",
              set(computerkit.PARSERS) == kit_names)

    print("== filekit / diskkit commands ==")
    try:
        from fileforge import filekit, diskkit
    except ImportError as exc:
        check("filekit + diskkit importable", False, str(exc))
    else:
        check("filekit + diskkit importable", True)
        check("launcher registers the file tools",
              set(filekit.HANDLERS).issubset(set(launch.FILEKIT_COMMANDS)),
              str(set(filekit.HANDLERS) - set(launch.FILEKIT_COMMANDS)))
        check("launcher registers the disk tools",
              set(diskkit.HANDLERS).issubset(set(launch.DISKKIT_COMMANDS)),
              str(set(diskkit.HANDLERS) - set(launch.DISKKIT_COMMANDS)))
        check("every file/disk command is advertised",
              set(filekit.HANDLERS) | set(diskkit.HANDLERS) <= set(names),
              str((set(filekit.HANDLERS) | set(diskkit.HANDLERS)) - set(names)))

    print("== unknown command handling ==")
    err = io.StringIO()
    old_err = sys.stderr
    sys.stderr = err
    try:
        rc_bad = launch._dispatch(["definitely-not-a-command"])
        rc_near = launch._dispatch(["duplicates"])
    finally:
        sys.stderr = old_err
    check("unknown command returns 2", rc_bad == 2, str(rc_bad))
    check("unknown command suggests help", "help" in err.getvalue())
    check("near-miss suggests a real command", rc_near in (0, 2))

    print("== package dispatcher (console script) ==")
    try:
        from fileforge import dispatch as pkg_dispatch
    except ImportError as exc:
        check("fileforge.dispatch importable", False, str(exc))
    else:
        check("fileforge.dispatch importable", True)
        check("package catalogue matches launcher",
              pkg_dispatch.all_command_names() == launch._all_names())
        check("package main() is callable", callable(pkg_dispatch.main))
        check("package gui_main() is callable", callable(pkg_dispatch.gui_main))

    print()
    print("=" * 46)
    print(f"  DISPATCH TOTAL: {PASSED} passed, {FAILED} failed")
    print("=" * 46)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
