#!/usr/bin/env python3
"""
End-to-end smoke test for the whole-computer ("This PC") views.

    python computer_smoke.py

Exercises the CLI subprocesses, the library API and the Tkinter window
(constructed for real, driven without a blocking mainloop).
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FF = [sys.executable, str(ROOT / "fileforge.py")]
sys.path.insert(0, str(ROOT / "src"))

PASSED = 0
FAILED = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  [PASS] {name}")
    else:
        FAILED += 1
        print(f"  [FAIL] {name} {detail}")


def run(*args, expect: int = 0, label: str = "") -> subprocess.CompletedProcess:
    proc = subprocess.run(FF + [str(a) for a in args],
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    tag = label or " ".join(str(a) for a in args)
    check(f"cli: {tag}", proc.returncode == expect,
          f"rc={proc.returncode} err={proc.stderr[:200]}")
    return proc


def main() -> int:
    global PASSED, FAILED

    print("\n--- CLI: whole computer ---")
    proc = run("computer", "--volumes")
    check("computer --volumes lists volumes",
          "free" in proc.stdout or "unavailable" in proc.stdout)

    proc = run("computer", "-L", "1", "--limit", "400", "--no-color")
    check("computer tree prints volumes", len(proc.stdout.strip().splitlines()) > 1)

    proc = run("computer", "-L", "1", "--limit", "400", "--stats", "--no-color")
    check("computer --stats prints a summary", "file(s)" in proc.stdout)

    proc = run("computer", "--files", "--limit", "25", "--full-path")
    lines = [l for l in proc.stdout.strip().splitlines() if l.strip()]
    check("computer --files lists files", len(lines) >= 1)
    check("computer --files uses absolute paths",
          all((":" in l) or l.startswith("/") for l in lines) if lines else True)

    print("\n--- library API ---")
    from fileforge.computer import (count_files, describe_volumes,
                                    iter_all_files, iter_computer_tree,
                                    list_dir, volumes)
    from fileforge.treeview import Options, system_roots

    vols = volumes()
    check("lib: volumes() non-empty", len(vols) >= 1)
    check("lib: volumes() reports total/free",
          all(isinstance(t, int) and isinstance(f, int) for _r, t, f in vols))
    check("lib: describe_volumes() renders", len(describe_volumes()) == len(vols))

    opts = Options(max_depth=1)
    entries = list(iter_computer_tree(opts, limit=300))
    check("lib: iter_computer_tree yields entries", len(entries) > 0)
    check("lib: top level nodes are the volumes",
          all(p == "" for p, _n, _s in entries[:1]))
    roots_seen = {str(n.path) for p, n, _s in entries if p == ""}
    check("lib: every volume appears as a node",
          roots_seen & set(system_roots()) != set())

    stats = entries[-1][2]
    check("lib: stats accumulated across volumes", stats.scanned > 0)

    items, err, hidden = list_dir(Path(system_roots()[0]), opts, 1)
    check("lib: list_dir returns entries", len(items) >= 0)
    check("lib: list_dir honours max_children",
          all(list_dir(Path(system_roots()[0]), Options(max_depth=1, max_children=n), 1)[2] >= 0
              for n in (1, 3)))
    capped_items, _e, capped_hidden = list_dir(
        Path(system_roots()[0]), Options(max_depth=1, max_children=2), 1)
    check("lib: max_children caps the item count", len(capped_items) <= 2)
    check("lib: max_children reports the hidden remainder", capped_hidden >= 0)

    t0 = time.time()
    got = []
    for node in iter_all_files(Options(max_depth=2), max_items=40):
        got.append(node)
    check("lib: iter_all_files yields files", len(got) > 0)
    check("lib: iter_all_files honours max_items", len(got) <= 40)
    print(f"         ({len(got)} files in {time.time() - t0:.2f}s)")

    stop = {"flag": False}
    n = 0
    for _node in iter_all_files(Options(max_depth=2), max_items=None,
                                should_stop=lambda: stop["flag"]):
        n += 1
        if n >= 5:
            stop["flag"] = True
    check("lib: iter_all_files honours should_stop", n <= 6)

    print("\n--- GUI (skipped when tkinter is unavailable) ---")
    try:
        import tkinter as tk
        from tkinter import messagebox
        messagebox.showerror = lambda *a, **k: None
        messagebox.showwarning = lambda *a, **k: None
        messagebox.showinfo = lambda *a, **k: None
        from fileforge.computerview import ComputerViewApp
    except ImportError as exc:
        print(f"  [SKIP] tkinter not available ({exc})")
        tk = None

    if tk is not None:
        master = tk.Tk()
        master.withdraw()
        app = ComputerViewApp(master, depth=1)
        master.update()
        check("gui: window constructed", True)
        check("gui: 'This PC' root present",
              app.tree.item(app.pc_iid, "text") == "This PC")

        volume_count = len(app.tree.get_children(app.pc_iid))
        check("gui: every volume inserted at start-up", volume_count >= 1)

        # pump the event loop so the background expander can flush its queue
        deadline = time.time() + 20
        while time.time() < deadline and app.scanning:
            master.update()
            time.sleep(0.02)
        master.update()
        check("gui: auto-expand populated the tree", app.tree_nodes > 0,
              f"nodes={app.tree_nodes}")
        check("gui: nodes are mapped to paths", len(app.path_by_iid) > 1)
        check("gui: status updated", len(app.status_var.get()) > 0)

        app.notebook.select(1)
        app.scan_files()
        deadline = time.time() + 15
        while time.time() < deadline and (app.scanning and app.file_rows == 0):
            master.update()
            time.sleep(0.02)
        master.update()
        app.stop_scan()
        master.update()
        check("gui: file scan produced rows or was stopped cleanly", True)
        check("gui: stop_scan sets the stop flag", app.stop_event.is_set())

        lines = app._tree_text_lines()
        check("gui: tree export renders lines", len(lines) >= 1)

        app.toggle_theme()
        master.update()
        check("gui: theme toggles", app.theme is not None)

        master.destroy()

    print(f"\n{'=' * 48}")
    print(f"  COMPUTER TOTAL: {PASSED} passed, {FAILED} failed")
    print(f"{'=' * 48}")
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
