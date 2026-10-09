#!/usr/bin/env python3
"""
fileforge - single-file launcher
================================

Runs the portable file-system toolkit from the repository root.

    python fileforge.py <command> [options]
    python fileforge.py shell
    python fileforge.py --help

Works on Linux, Windows and macOS with no third-party dependencies.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Make the package importable no matter where the script is invoked from.
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# --- added: the package also lives under ./src (setuptools src-layout) ----
SRC = HERE / "src"
if SRC.is_dir() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Best effort: force UTF-8 output on Windows terminals.
if os.name == "nt":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass


def _bootstrap() -> int:
    try:
        from fileforge.cli import main
    except ImportError as exc:  # pragma: no cover
        print(f"fileforge: failed to import package: {exc}", file=sys.stderr)
        return 1
    return main(sys.argv[1:])


# --- added: live file-system tree commands --------------------------------
# Handled before the classic CLI; everything else still falls through to the
# original _bootstrap() so no existing behaviour is lost.
#
#   python fileforge.py tree . -L 2 --du --stats
#   python fileforge.py treeui D:\
#   python fileforge.py treemap . --top 25
#   python fileforge.py drives
#   python fileforge.py computer -L 2          # whole machine as a tree
#   python fileforge.py computerui             # "This PC" window
TREE_COMMANDS = {"tree", "treeui", "tree-gui", "treemap", "drives", "roots",
                 "computer", "pc", "thispc", "computerui", "pcgui"}


def _show_roots() -> int:
    from fileforge.treeview import system_roots
    from fileforge.utils import free_space, human_size

    roots = system_roots()
    print(f"Mount points / drives on this machine ({len(roots)}):")
    for root in roots:
        try:
            total, _used, free = free_space(Path(root))
            print(f"  {root:<24} free {human_size(free):>10} of {human_size(total):>10}")
        except OSError:
            print(f"  {root:<24} (unavailable)")
    return 0


def _tree_dispatch(argv):
    """Return an exit code for tree commands, or None to fall through."""
    if not argv or argv[0] not in TREE_COMMANDS:
        return None
    cmd, rest = argv[0], list(argv[1:])
    try:
        if cmd == "tree":
            from fileforge.treeview import main as tree_main
            return tree_main(rest)
        if cmd in ("treeui", "tree-gui"):
            # No path given -> show the whole computer ("This PC").
            if not rest:
                from fileforge.computerview import main as pc_main
                return pc_main(rest)
            from fileforge.treeui import main as treeui_main
            return treeui_main(rest)
        if cmd == "treemap":
            from fileforge.treemap import main as treemap_main
            return treemap_main(rest)
        if cmd in ("drives", "roots"):
            return _show_roots()
        if cmd in ("computer", "pc", "thispc"):
            from fileforge.computer import main as computer_main
            return computer_main(rest)
        if cmd in ("computerui", "pcgui"):
            from fileforge.computerview import main as pc_main
            return pc_main(rest)
    except ImportError as exc:  # pragma: no cover
        print(f"fileforge: {cmd} needs the fileforge package ({exc})", file=sys.stderr)
        return 1
    return None


if __name__ == "__main__":
    _handled = _tree_dispatch(sys.argv[1:])
    if _handled is None:
        sys.exit(_bootstrap())
    sys.exit(_handled)
