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
#
# The catalogue is now focused on the whole-computer ("This PC") workflow.
# The classic single-directory commands still work -- they are simply not
# advertised any more; `fileforge legacy` lists them.
# --------------------------------------------------------------------------
CATALOG: List[Tuple[str, List[Tuple[str, str]]]] = [
    ("This PC - open", [
        ("computerui",      "Open the This PC window (all drives, live)"),
        ("treeui",          "Tk tree explorer - This PC when no path is given"),
        ("computer",        "Print the whole machine as one tree"),
        ("computertree",    "Whole-machine tree with extra filters"),
    ]),
    ("This PC - inventory", [
        ("computerinfo",    "Machine + volume overview (capacity, used, free)"),
        ("computerdrives",  "Every drive / mount point with a usage bar"),
        ("computerscan",    "One full scan: counts, bytes, per-volume table"),
        ("computerexport",  "Export the whole machine to JSON / CSV / TXT"),
    ]),
    ("This PC - what is big", [
        ("computerdirs",    "Biggest directories anywhere on the machine"),
        ("computerlarge",   "Biggest files anywhere on the machine"),
        ("computermap",     "Terminal block map of every volume"),
        ("computerext",     "Size / count grouped by file extension"),
    ]),
    ("This PC - by age", [
        ("computernew",     "Most recently modified files"),
        ("computerold",     "Least recently modified files"),
        ("computerempty",   "Empty files and empty directories"),
        ("computerstats",   "One-shot statistical report (buckets, ages, top)"),
    ]),
    ("This PC - search & integrity", [
        ("computerfind",    "Find files by name / glob across every drive"),
        ("computergrep",    "Search file contents across every drive"),
        ("computerdupes",   "Duplicate files across every drive"),
        ("computertemp",    "Temporary / cache / junk files"),
    ]),
    ("This PC - track changes", [
        ("computersnapshot", "Save a snapshot (path + size + mtime)"),
        ("computerdiff",     "Diff two snapshots (added / removed / changed)"),
        ("computerwatch",    "Live watch: created / deleted / modified"),
    ]),
    ("This PC - safety", [
        ("computeraudit",   "Permission audit (world-writable, setuid, setgid)"),
    ]),
    ("Files - inspect", [
        ("filemeta",        "Complete metadata report for one path"),
        ("filepreview",     "Preview any file: text head or binary hex"),
        ("filehex",         "Hex dump with offset / length / width control"),
    ]),
    ("Files - compare & fix names", [
        ("filediff",        "Line diff of two files, or inventory diff of two dirs"),
        ("filesanitize",    "Find (and optionally fix) illegal / reserved names"),
        ("filenorm",        "Normalise names (Unicode NFC, case, spaces)"),
    ]),
    ("Files - content tools", [
        ("fileextract",     "Pull URLs / e-mails / IPv4 addresses out of a file"),
        ("fileencode",      "base64 / hex / url-encode a file"),
        ("filedecode",      "base64 / hex / url-decode a file"),
    ]),
    ("Files - housekeeping", [
        ("filetrim",        "Strip blank lines, trailing whitespace, BOM, CRLF"),
        ("filesort",        "Sort / de-duplicate the lines of a text file"),
        ("filebackup",      "Timestamped copy (name.bak-20260101-120000)"),
    ]),
    ("Disks - hardware", [
        ("diskinfo",        "Physical disks: model, serial, bus, media, size"),
        ("diskpartitions",  "Partition / volume table with mount points"),
        ("diskfs",          "File system type of every mount point"),
        ("diskserial",      "Volume serial numbers / UUIDs"),
    ]),
    ("Disks - space", [
        ("diskusage",       "Used vs free per volume, as a block map"),
        ("diskfree",        "Free space overview + low-space warning"),
        ("disktop",         "Biggest entries directly under a root / volume"),
        ("diskmounts",      "Mount points, removable and network drives"),
    ]),
    ("Disks - health", [
        ("diskhealth",      "Health / SMART status of every disk"),
        ("disktemp",        "Temperature where the platform exposes it"),
        ("diskio",          "Read / write counters"),
        ("diskbench",       "Real write / read throughput benchmark"),
    ]),
    ("Disks - integrity", [
        ("diskbadfiles",    "Walk a tree and list files that cannot be read"),
        ("diskerrors",      "Walk a tree and list directories that fail to list"),
    ]),
    ("Help", [
        ("help",            "Show this command list"),
        ("legacy",          "List the hidden classic (single-directory) commands"),
    ]),
]

# Aliases -> canonical command name.
ALIASES: Dict[str, str] = {
    # --- This PC window / tree -------------------------------------------
    "tree-gui": "treeui",
    "explorer": "treeui",
    "pcexplorer": "treeui",
    "pc": "computer",
    "thispc": "computer",
    "this-pc": "computer",
    "mycomputer": "computer",
    "pcgui": "computerui",
    "pcui": "computerui",
    "thispcui": "computerui",
    "this-pc-ui": "computerui",
    "computer-gui": "computerui",
    "pctree": "computertree",
    # --- inventory --------------------------------------------------------
    "pcinfo": "computerinfo",
    "pcsysinfo": "computerinfo",
    "pcdrives": "computerdrives",
    "pcvolumes": "computerdrives",
    "roots": "computerdrives",
    "mounts": "computerdrives",
    "drives": "computerdrives",
    "pcscan": "computerscan",
    "pcexport": "computerexport",
    # --- what is big ------------------------------------------------------
    "pcdirs": "computerdirs",
    "pcbigdirs": "computerdirs",
    "pclarge": "computerlarge",
    "pcbig": "computerlarge",
    "largest": "computerlarge",
    "pcmap": "computermap",
    "map": "treemap",
    "diskmap": "treemap",
    "du-map": "treemap",
    "pcext": "computerext",
    # --- by age -----------------------------------------------------------
    "pcnew": "computernew",
    "pcrecent": "computernew",
    "pcold": "computerold",
    "pcempty": "computerempty",
    "pcstats": "computerstats",
    # --- search & integrity ----------------------------------------------
    "pcfind": "computerfind",
    "pcgrep": "computergrep",
    "pcdupes": "computerdupes",
    "pcduplicates": "computerdupes",
    "pctemp": "computertemp",
    "pcjunk": "computertemp",
    # --- track changes ----------------------------------------------------
    "pcsnapshot": "computersnapshot",
    "pcdiff": "computerdiff",
    "pcwatch": "computerwatch",
    # --- safety -----------------------------------------------------------
    "pcaudit": "computeraudit",
    # --- file tools -------------------------------------------------------
    "fmeta": "filemeta",
    "fstat": "filemeta",
    "fpreview": "filepreview",
    "fcat": "filepreview",
    "fhex": "filehex",
    "hexdump": "filehex",
    "fdiff": "filediff",
    "fsanitize": "filesanitize",
    "fnorm": "filenorm",
    "fextract": "fileextract",
    "fenc": "fileencode",
    "fencode": "fileencode",
    "fdec": "filedecode",
    "fdecode": "filedecode",
    "ftrim": "filetrim",
    "fsort": "filesort",
    "fbackup": "filebackup",
    # --- disk tools -------------------------------------------------------
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

# Commands implemented by fileforge.filekit (single-file tools).
FILEKIT_COMMANDS = {
    "filemeta", "filediff", "filesanitize", "filenorm", "fileextract",
    "fileencode", "filedecode", "filetrim", "filesort", "filebackup",
    "filepreview", "filehex",
}

# Commands implemented by fileforge.diskkit (disk / volume tools).
DISKKIT_COMMANDS = {
    "diskinfo", "diskpartitions", "diskfs", "diskusage", "diskfree",
    "diskio", "diskhealth", "disktemp", "diskbench", "diskserial",
    "diskbadfiles", "diskerrors", "disktop", "diskmounts",
}

# Commands implemented by fileforge.computerkit (the "This PC" analysis set).
COMPUTERKIT_COMMANDS = {
    "computerinfo", "computerdrives", "computerscan", "computertree",
    "computerdirs", "computerlarge", "computermap", "computerext",
    "computernew", "computerold", "computerempty", "computerstats",
    "computerfind", "computergrep", "computerdupes", "computertemp",
    "computerexport", "computersnapshot", "computerdiff", "computerwatch",
    "computeraudit",
}

# Commands handled by the live-tree modules (everything else is classic CLI).
TREE_COMMANDS = {"tree", "treeui", "treemap", "drives", "computer", "computerui"}

# Commands implemented inside fileforge.cli (the classic 40+ command set).
# They remain fully functional, they are just no longer advertised in `help`.
CLASSIC_COMMANDS = {
    "ls", "find", "grep", "cat", "write", "touch", "cp", "mv", "rm", "mkdir",
    "rename", "rename-batch", "hash", "manifest", "verify", "compare", "dupes",
    "du", "largest", "newest", "oldest", "empty", "broken-links",
    "ext-summary", "summary", "archive-create", "archive-extract",
    "archive-list", "gzip", "split", "merge", "sync", "chmod", "perms",
    "world-writable", "shred", "encrypt", "decrypt", "wc", "replace",
    "convert-encoding", "symlink", "readlink", "stat", "filetype", "free",
    "shell",
}

# AdvertisedThis-PC commands that are not part of the classic CLI.
LEGACY_CATALOG: List[Tuple[str, List[Tuple[str, str]]]] = [
    ("Browse & inspect", [
        ("ls", "List directory contents"),
        ("tree", "Live directory tree for one root"),
        ("stat", "Detailed metadata (mode, times, inode, MIME)"),
        ("filetype", "Content-based MIME detection"),
        ("free", "Free / used / total space on a volume"),
    ]),
    ("Disk usage", [
        ("du", "Directory size breakdown"),
        ("summary", "One-shot report for a directory"),
        ("broken-links", "Dangling symlinks"),
    ]),
    ("File content", [
        ("cat", "Print a file"),
        ("write", "Write / append text to a file"),
        ("touch", "Create an empty file or update mtime"),
        ("wc", "Line / word / byte count"),
        ("replace", "Find & replace (plain or regex, --dry-run)"),
        ("convert-encoding", "Re-encode a text file"),
    ]),
    ("Manage", [
        ("cp", "Copy files / directories"),
        ("mv", "Move or rename"),
        ("rm", "Remove files / directories"),
        ("mkdir", "Create directories"),
        ("rename", "Rename one path"),
        ("rename-batch", "Bulk rename with a pattern"),
        ("symlink", "Create a symbolic link"),
        ("readlink", "Resolve a symbolic link"),
    ]),
    ("Search", [("find", "Multi-criteria file search"),
                ("grep", "Recursive content search")]),
    ("Integrity", [
        ("hash", "Checksum one or more files"),
        ("manifest", "Write a JSON checksum manifest"),
        ("verify", "Verify a tree against a manifest"),
        ("compare", "Byte-compare two files"),
        ("dupes", "Find duplicate files in one tree"),
    ]),
    ("Archive & sync", [
        ("archive-create", "Create zip / tar / tar.gz / tar.bz2 / tar.xz"),
        ("archive-extract", "Extract an archive (zip-slip safe)"),
        ("archive-list", "List archive contents"),
        ("gzip", "gzip / gunzip a single file"),
        ("split", "Split a file into chunks"),
        ("merge", "Rejoin chunks"),
        ("sync", "Incremental mirror of a directory"),
    ]),
    ("Security", [
        ("chmod", "Change permissions (octal or symbolic)"),
        ("perms", "List permissions"),
        ("shred", "Secure delete (overwrite then unlink)"),
        ("encrypt", "Encrypt a file with a passphrase"),
        ("decrypt", "Decrypt a file"),
    ]),
    ("Applications", [("shell", "Interactive shell (cd/pwd/history/!cmd)")]),
]


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


def _run_computerkit(cmd: str, rest: List[str]) -> int:
    """Forward to the "This PC" analysis commands in fileforge.computerkit."""
    from fileforge.computerkit import run as kit_run
    return kit_run(cmd, rest)


def _run_filekit(cmd: str, rest: List[str]) -> int:
    """Forward to the single-file tools in fileforge.filekit."""
    from fileforge.filekit import run as kit_run
    return kit_run(cmd, rest)


def _run_diskkit(cmd: str, rest: List[str]) -> int:
    """Forward to the disk / volume tools in fileforge.diskkit."""
    from fileforge.diskkit import run as kit_run
    return kit_run(cmd, rest)


def _print_catalog(stream=None, catalog=None) -> None:
    out = stream or sys.stdout
    table = catalog or CATALOG
    out.write(f"{APP} - portable local file-system toolkit (This PC edition)\n")
    out.write("Usage: fileforge <command> [options]\n")
    out.write("       fileforge help                show this list\n")
    out.write("       fileforge computerui          open the This PC window\n")
    out.write("       fileforge <command> --help    options for one command\n\n")
    width = max(len(name) for _g, entries in table for name, _h in entries)
    for group, entries in table:
        out.write(f"{group}\n")
        for name, help_text in entries:
            extra = ""
            for alias, target in ALIASES.items():
                if target == name:
                    extra += f" /{alias}"
            out.write(f"  {name:<{width}}  {help_text}{extra}\n")
        out.write("\n")
    if catalog is None:
        out.write("Tip: every command supports --help.  Typos are auto-corrected\n")
        out.write("     (e.g. `fileforge computrui` runs `computerui`).\n")
        out.write("     The classic single-directory commands (ls, find, hash,\n")
        out.write("     cp, ...) still work - `fileforge legacy` lists them.\n")


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
    if args[0] in ("legacy", "classic"):
        _print_catalog(catalog=LEGACY_CATALOG)
        return 0

    cmd, rest = args[0], list(args[1:])
    cmd = ALIASES.get(cmd, cmd)

    try:
        if cmd in COMPUTERKIT_COMMANDS:
            return _run_computerkit(cmd, rest)
        if cmd in FILEKIT_COMMANDS:
            return _run_filekit(cmd, rest)
        if cmd in DISKKIT_COMMANDS:
            return _run_diskkit(cmd, rest)
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
    """Entry point for ``fileforge-gui``: open the This PC window."""
    args: List[str] = list(sys.argv[1:] if argv is None else argv)
    return main(["computerui"] + args)


if __name__ == "__main__":
    sys.exit(main())
