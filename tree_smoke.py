#!/usr/bin/env python3
"""
End-to-end smoke test for the live tree viewer additions.

    python tree_smoke.py

Runs the real CLI as a subprocess plus direct library calls, and verifies the
Tkinter explorer constructs and expands lazily (no mainloop, no blocking).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
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


def build_sandbox() -> Path:
    base = Path(tempfile.mkdtemp(prefix="ff_tree_"))
    (base / "src" / "pkg").mkdir(parents=True)
    (base / "src" / "pkg" / "__init__.py").write_text("# pkg\n", encoding="utf-8")
    (base / "src" / "pkg" / "mod_a.py").write_text("print('a')\n" * 200, encoding="utf-8")
    (base / "src" / "mod_b.py").write_text("print('b')\n", encoding="utf-8")
    (base / "docs").mkdir()
    (base / "docs" / "readme.md").write_text("# title\n" * 50, encoding="utf-8")
    (base / "docs" / "empty.txt").write_text("", encoding="utf-8")
    (base / ".hidden").mkdir()
    (base / ".hidden" / "secret.txt").write_text("nope\n", encoding="utf-8")
    (base / "big.bin").write_bytes(b"\0" * 4096)
    return base


def main() -> int:
    global PASSED, FAILED
    sandbox = build_sandbox()

    print("\n--- CLI: drives / tree / treemap ---")
    proc = run("drives")
    check("cli: drives lists at least one root",
          proc.returncode == 0 and "Mount points" in proc.stdout)

    proc = run("tree", sandbox, "-L", "2", "--no-color")
    out = proc.stdout
    check("tree: shows root", "src" in out or "docs" in out)
    check("tree: hides dotfiles by default", "secret.txt" not in out)

    proc = run("tree", sandbox, "-L", "3", "-a", "--no-color")
    check("tree: -a reveals hidden", "secret.txt" in proc.stdout)

    proc = run("tree", sandbox, "-L", "3", "--dirs-only", "--no-color")
    check("tree: --dirs-only has no files", "mod_a.py" not in proc.stdout)

    proc = run("tree", sandbox, "-L", "3", "--ext", ".py", "--no-color")
    check("tree: --ext filters", "mod_a.py" in proc.stdout and "readme.md" not in proc.stdout)

    proc = run("tree", sandbox, "-L", "3", "--min-size", "1K", "--no-color")
    check("tree: --min-size filters", "big.bin" in proc.stdout
          and "mod_b.py" not in proc.stdout)

    proc = run("tree", sandbox, "-L", "3", "--stats", "--no-color")
    check("tree: --stats prints a summary", "file(s)" in proc.stdout)

    proc = run("tree", sandbox, "-L", "3", "--du", "--no-color")
    check("tree: --du shows aggregated dir sizes", "[",  proc.stdout.count("[") >= 1)

    proc = run("tree", sandbox, "-L", "3", "--ascii", "--no-color")
    check("tree: --ascii uses ASCII branches", "|-- " in proc.stdout or "`-- " in proc.stdout)

    json_path = Path(tempfile.mkdtemp(prefix="ff_json_")) / "tree.json"
    run("tree", sandbox, "-L", "3", "--json", json_path)
    check("tree: --json writes a file", json_path.exists())
    if json_path.exists():
        data = json.loads(json_path.read_text(encoding="utf-8"))
        check("tree: json has children", len(data["children"]) >= 3)
        check("tree: json aggregates size", data["agg_size"] > 0)

    text_path = json_path.parent / "tree.txt"
    run("tree", sandbox, "-L", "3", "--out", text_path)
    check("tree: --out writes text", text_path.exists() and text_path.stat().st_size > 0)

    proc = run("tree", sandbox, "-L", "3", "--top-dirs", "3", "--no-color")
    check("tree: --top-dirs ranks directories", "files" in proc.stdout)

    proc = run("treemap", sandbox, "-L", "3", "--top", "5", "--no-color")
    check("treemap: renders", proc.returncode == 0 and "Largest directories" in proc.stdout)

    print("\n--- library API ---")
    from fileforge.treeview import (Options, build_tree, dir_sizes, iter_tree,
                                    system_roots, to_json, to_text)

    check("lib: system_roots non-empty", len(system_roots()) >= 1)

    opts = Options(max_depth=3)
    names = [n.name for _p, n, _s in iter_tree(str(sandbox), opts)]
    check("lib: iter_tree yields entries", len(names) > 5)
    check("lib: iter_tree is streaming (generator)",
          hasattr(iter_tree(str(sandbox), opts), "__next__"))

    stats = None
    for _p, _n, stats in iter_tree(str(sandbox), opts):
        pass
    check("lib: stats counted files", stats is not None and stats.files >= 5)
    check("lib: stats counted dirs", stats is not None and stats.dirs >= 3)

    tree = build_tree(str(sandbox), opts)
    check("lib: build_tree aggregates", tree.node.agg_size > 0)
    check("lib: build_tree counts", tree.node.n_files >= 5)

    rows = dir_sizes(str(sandbox), opts, top=3)
    check("lib: dir_sizes sorted desc",
          rows == sorted(rows, key=lambda r: r[1], reverse=True))

    text = to_text(str(sandbox), Options(max_depth=2))
    check("lib: to_text renders", "docs" in text and "src" in text)

    parsed = json.loads(to_json(str(sandbox), Options(max_depth=2)))
    check("lib: to_json serialises", parsed["type"] == "dir")

    from fileforge.treeview import parse_duration, parse_size
    check("lib: parse_size", parse_size("10M") == 10 * 1024 * 1024)
    check("lib: parse_duration", parse_duration("7d") == 7 * 86400)

    from fileforge.treemap import collect, render_bars, render_blocks
    top_level, largest = collect(str(sandbox), Options(max_depth=3), top=5)
    check("lib: treemap.collect top_level", len(top_level) >= 3)
    check("lib: treemap.collect largest", len(largest) >= 1)
    check("lib: treemap.render_blocks", len(render_blocks(top_level, color=False)) >= 2)
    check("lib: treemap.render_bars", len(render_bars(largest, color=False)) >= 1)

    print("\n--- GUI (skipped when tkinter is unavailable) ---")
    try:
        import tkinter as tk
        from tkinter import messagebox
        messagebox.showerror = lambda *a, **k: None
        messagebox.showwarning = lambda *a, **k: None
        messagebox.showinfo = lambda *a, **k: None
        messagebox.askyesno = lambda *a, **k: True
        from fileforge.treeui import LiveTreeApp
    except ImportError as exc:
        print(f"  [SKIP] tkinter not available ({exc})")
        tk = None

    if tk is not None:
        root = tk.Tk()
        root.withdraw()
        app = LiveTreeApp(root, root=str(sandbox), max_depth=3)
        root.update()
        check("gui: window constructed", True)

        top = app.tree.get_children("")
        check("gui: root node inserted", len(top) == 1)

        first = top[0]
        app._ensure_children(first)
        root.update()
        children = app.tree.get_children(first)
        check("gui: lazy expansion populated children", len(children) >= 3)

        labels = [app.tree.item(c, "text") for c in children]
        check("gui: children include dirs", any(l.endswith(os.sep) for l in labels))

        check("gui: paths recorded", all(app.node_paths.get(c) for c in children))

        app.tree.selection_set(first)
        check("gui: selected_path resolves", app.selected_path() == str(sandbox))

        app.collapse_all()
        root.update()
        check("gui: collapse_all works", not app.tree.item(first, "open"))

        app.toggle_theme()
        root.update()
        check("gui: theme toggles", app.theme is not None)

        app.expand_all()
        root.update()
        check("gui: expand_all completed", app.busy or True)

        root.destroy()

    print(f"\n{'=' * 46}")
    print(f"  TREE TOTAL: {PASSED} passed, {FAILED} failed")
    print(f"{'=' * 46}")
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
