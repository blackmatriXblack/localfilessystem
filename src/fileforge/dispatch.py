#!/usr/bin/env python3
"""
fileforge.dispatch - unified command registry and dispatcher
============================================================

One place that knows **every** command shipped by fileforge:

* the classic CLI commands implemented in ``fileforge.cli``
* the live file-tree commands (``fileforge.treeview``)
* the Tkinter tree explorer (``fileforge.treeui``)
* the terminal disk-usage chart (``fileforge.treemap``)
* the whole-computer / "This PC" engine and window
  (``fileforge.computer``, ``fileforge.computerview``)

It also understands aliases (``pc`` -> ``computer``) and gently corrects
typos (``computrui`` -> ``computerui``) instead of printing
"invalid choice".

This module is the console-script entry point::

    fileforge = fileforge.dispatch:main

``fileforge.py`` in the repository root carries the very same registry so the
launcher keeps working standalone.
"""

from __future__ import annotations

import difflib
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

APP = "fileforge"

# --------------------------------------------------------------------------
# Command catalogue.  (group, [(name, one-line help), ...])
# --------------------------------------------------------------------------
CATALOG: List[Tuple[str, List[Tuple[str, str]]]] = [
    ("Browse & inspect", [
        ("ls",              "List directory contents"),
        ("tree",            "Live directory tree (no cache, streaming)"),
        ("tree-classic",    "Original ASCII tree from the classic CLI"),
        ("stat",            "Detailed metadata (mode, times, inode, MIME)"),
        ("filetype",        "Content-based MIME detection"),
        ("free",            "Free / used / total space on a volume"),
        ("drives",          "List all drives / mount points + free space"),
    ]),
    ("Whole computer (\"This PC\")", [
        ("computer",        "Print the entire machine as one tree"),
        ("computerui",      "Open the This PC window (all drives)"),
        ("treeui",          "Tkinter tree explorer (This PC when no path)"),
    ]),
    ("Disk usage", [
        ("treemap",         "Terminal disk-usage block map / bar chart"),
        ("du",              "Directory size breakdown"),
        ("largest",         "Largest files"),
        ("newest",          "Most recently modified files"),
        ("oldest",          "Least recently modified files"),
        ("empty",           "Empty files and directories"),
        ("broken-links",    "Dangling symlinks"),
        ("ext-summary",     "Count / size grouped by extension"),
        ("summary",         "One-shot report for a directory"),
    ]),
    ("File content", [
        ("cat",             "Print a file"),
        ("write",           "Write / append text to a file"),
        ("touch",           "Create an empty file or update mtime"),
        ("wc",              "Line / word / byte count"),
        ("replace",         "Find & replace (plain or regex, --dry-run)"),
        ("convert-encoding", "Re-encode a text file"),
    ]),
    ("Manage", [
        ("cp",              "Copy files / directories"),
        ("mv",              "Move or rename"),
        ("rm",              "Remove files / directories"),
        ("mkdir",           "Create directories"),
        ("rename",          "Rename one path"),
        ("rename-batch",    "Bulk rename with a pattern"),
        ("symlink",         "Create a symbolic link"),
        ("readlink",        "Resolve a symbolic link"),
    ]),
    ("Search", [
        ("find",            "Multi-criteria file search"),
        ("grep",            "Recursive content search"),
    ]),
    ("Integrity", [
        ("hash",            "Checksum one or more files"),
        ("manifest",        "Write a JSON checksum manifest"),
        ("verify",          "Verify a tree against a manifest"),
        ("compare",         "Byte-compare two files"),
        ("dupes",           "Find duplicate files"),
    ]),
    ("Archive & sync", [
        ("archive-create",  "Create zip / tar / tar.gz / tar.bz2 / tar.xz"),
        ("archive-extract", "Extract an archive (zip-slip safe)"),
        ("archive-list",    "List archive contents"),
        ("gzip",            "gzip / gunzip a single file"),
        ("split",           "Split a file into chunks"),
        ("merge",           "Rejoin chunks"),
        ("sync",            "Incremental mirror of a directory"),
    ]),
    ("Security", [
        ("chmod",           "Change permissions (octal or symbolic)"),
        ("perms",           "List permissions"),
        ("world-writable",  "Audit world-writable paths"),
        ("shred",           "Secure delete (overwrite then unlink)"),
        ("encrypt",         "Encrypt a file with a passphrase"),
        ("decrypt",         "Decrypt a file"),
    ]),
    ("Applications", [
        ("gui",             "Full Tkinter GUI (8 tabs)"),
        ("shell",           "Interactive shell (cd/pwd/history/!cmd)"),
        ("help",            "Show this command list"),
    ]),
]

# Aliases -> canonical command name.
ALIASES: Dict[str, str] = {
    "tree-gui": "treeui",
    "explorer": "treeui",
    "pc": "computer",
    "thispc": "computer",
    "this-pc": "computer",
    "mycomputer": "computer",
    "pcgui": "computerui",
    "pcui": "computerui",
    "thispcui": "computerui",
    "this-pc-ui": "computerui",
    "computer-gui": "computerui",
    "roots": "drives",
    "mounts": "drives",
    "volumes": "drives",
    "map": "treemap",
    "diskmap": "treemap",
    "du-map": "treemap",
}

# Commands handled by the live-tree modules (everything else is classic CLI).
TREE_COMMANDS = {"tree", "treeui", "treemap", "drives", "computer", "computerui"}

# Commands implemented inside fileforge.cli (the classic 40+ command set).
CLASSIC_COMMANDS = {
    "ls", "find", "grep", "cat", "write", "touch", "cp", "mv", "rm", "mkdir",
    "rename", "rename-batch", "hash", "manifest", "verify", "compare", "dupes",
    "du", "largest", "newest", "oldest", "empty", "broken-links",
    "ext-summary", "summary", "archive-create", "archive-extract",
    "archive-list", "gzip", "split", "merge", "sync", "chmod", "perms",
    "world-writable", "shred", "encrypt", "decrypt", "wc", "replace",
    "convert-encoding", "symlink", "readlink", "stat", "filetype", "free",
    "shell", "gui",
}


def all_command_names() -> List[str]:
    """Every registered command name, canonical order."""
    names: List[str] = []
    for _group, entries in CATALOG:
        names.extend(name for name, _help in entries)
    return names


def _closest(word: str, candidates: Sequence[str]) -> Optional[str]:
    matches = difflib.get_close_matches(word, list(candidates), n=1, cutoff=0.7)
    return matches[0] if matches else None


# --------------------------------------------------------------------------
# Handlers
# --------------------------------------------------------------------------
def _classic(argv: List[str]) -> int:
    """Delegate to the classic argparse CLI (never back to ``cli.main``)."""
    from fileforge import cli as cli_mod
    handler = getattr(cli_mod, "main_classic", None) or cli_mod.main
    return handler(argv)


def _run_tree(rest: List[str]) -> int:
    from fileforge.treeview import main as tree_main
    return tree_main(rest)


def _run_treemap(rest: List[str]) -> int:
    from fileforge.treemap import main as treemap_main
    return treemap_main(rest)


def _run_treeui(rest: List[str]) -> int:
    """Path given -> folder explorer.  No path -> whole computer."""
    has_path = any(not a.startswith("-") for a in rest)
    if has_path:
        from fileforge.treeui import main as treeui_main
        return treeui_main(rest)
    from fileforge.computerview import main as pc_main
    return pc_main(rest)


def _run_computer(rest: List[str]) -> int:
    from fileforge.computer import main as computer_main
    return computer_main(rest)


def _run_computerui(rest: List[str]) -> int:
    from fileforge.computerview import main as pc_main
    return pc_main(rest)


def _run_drives() -> int:
    from fileforge.treeview import system_roots
    from fileforge.utils import free_space, human_size

    roots = system_roots()
    print(f"Mount points / drives on this machine ({len(roots)}):")
    for root in roots:
        try:
            total, _used, free = free_space(Path(root))
            print(f"  {root:<24} free {human_size(free):>10} "
                  f"of {human_size(total):>10}")
        except OSError:
            print(f"  {root:<24} (unavailable)")
    return 0


def _print_catalog(stream=None) -> None:
    out = stream or sys.stdout
    out.write(f"{APP} - portable local file-system toolkit\n")
    out.write("Usage: fileforge <command> [options]\n")
    out.write("       fileforge help                show this list\n")
    out.write("       fileforge <command> --help    options for one command\n\n")
    width = max(len(name) for _g, entries in CATALOG for name, _h in entries)
    for group, entries in CATALOG:
        out.write(f"{group}\n")
        for name, help_text in entries:
            extra = ""
            for alias, target in ALIASES.items():
                if target == name:
                    extra += f" /{alias}"
            out.write(f"  {name:<{width}}  {help_text}{extra}\n")
        out.write("\n")
    out.write("Tip: every command supports --help.  Typos are auto-corrected\n")
    out.write("     (e.g. `fileforge computrui` runs `computerui`).\n")


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------
def main(argv: Optional[Sequence[str]] = None) -> int:
    args: List[str] = list(sys.argv[1:] if argv is None else argv)

    if not args or args[0] in ("help", "commands"):
        _print_catalog()
        return 0
    if args[0] in ("--version", "-V"):
        from fileforge import __version__
        print(f"{APP} {__version__}")
        return 0

    cmd, rest = args[0], list(args[1:])
    cmd = ALIASES.get(cmd, cmd)

    try:
        if cmd == "tree-classic":
            return _classic(["tree"] + rest)
        if cmd == "tree":
            return _run_tree(rest)
        if cmd == "treeui":
            return _run_treeui(rest)
        if cmd == "treemap":
            return _run_treemap(rest)
        if cmd == "drives":
            return _run_drives()
        if cmd == "computer":
            return _run_computer(rest)
        if cmd == "computerui":
            return _run_computerui(rest)
        if cmd in CLASSIC_COMMANDS:
            return _classic([cmd] + rest)
    except ImportError as exc:
        print(f"{APP}: '{cmd}' needs the fileforge package ({exc})",
              file=sys.stderr)
        print(f"{APP}: on Linux install tkinter with: "
              f"sudo apt install python3-tk", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130

    # Unknown command: try to be helpful.
    known = sorted(set(all_command_names()) | set(ALIASES))
    guess = _closest(cmd, known)
    if guess:
        guess = ALIASES.get(guess, guess)
        ratio = difflib.SequenceMatcher(None, cmd, guess).ratio()
        if ratio >= 0.8:
            print(f"{APP}: interpreting '{cmd}' as '{guess}'", file=sys.stderr)
            return main([guess] + rest)
        print(f"{APP}: unknown command '{cmd}' (did you mean '{guess}'?)",
              file=sys.stderr)
    else:
        print(f"{APP}: unknown command '{cmd}'", file=sys.stderr)
    print(f"{APP}: run '{APP} help' to see all commands.", file=sys.stderr)
    return 2


def gui_main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point for ``fileforge-gui``: open the full Tkinter GUI."""
    args: List[str] = list(sys.argv[1:] if argv is None else argv)
    return main(["gui"] + args)


if __name__ == "__main__":
    sys.exit(main())
