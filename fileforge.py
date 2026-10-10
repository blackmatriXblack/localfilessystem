#!/usr/bin/env python3
"""
fileforge - single-file launcher (complete command registry)
============================================================

Runs the portable file-system toolkit from the repository root.

    python fileforge.py <command> [options]
    python fileforge.py help               # list every command
    python fileforge.py computerui         # "This PC" window (all drives)
    python fileforge.py shell
    python fileforge.py --help

Every command shipped by the toolkit is registered here:

  * the classic CLI commands (fileforge.cli)      - ls / find / grep / hash ...
  * the live file tree      (fileforge.treeview)  - tree / drives
  * the Tkinter explorer    (fileforge.treeui)    - treeui
  * the disk-usage chart    (fileforge.treemap)   - treemap
  * the whole-computer view (fileforge.computer,
                             fileforge.computerview) - computer / computerui

Aliases (pc, thispc, pcgui, explorer, ...) and typo correction
("computrui" -> "computerui") are handled as well.

Works on Linux, Windows and macOS with no third-party dependencies.
"""

from __future__ import annotations

import difflib
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

APP = "fileforge"


# ==========================================================================
# Command catalogue: (group, [(name, one-line help), ...])
# ==========================================================================
# The catalogue now focuses on the whole-computer ("This PC") workflow.
# The classic single-directory commands keep working, they are just not
# advertised any more -- `python fileforge.py legacy` lists them.
CATALOG = [
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
ALIASES = {
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
    "pcinfo": "computerinfo",
    "pcsysinfo": "computerinfo",
    "pcdrives": "computerdrives",
    "pcvolumes": "computerdrives",
    "roots": "computerdrives",
    "mounts": "computerdrives",
    "drives": "computerdrives",
    "pcscan": "computerscan",
    "pcexport": "computerexport",
    "pcdirs": "computerdirs",
    "pcbigdirs": "computerdirs",
    "pclarge": "computerlarge",
    "pcbig": "computerlarge",
    "pcmap": "computermap",
    "map": "treemap",
    "diskmap": "treemap",
    "du-map": "treemap",
    "pcext": "computerext",
    "pcnew": "computernew",
    "pcrecent": "computernew",
    "pcold": "computerold",
    "pcempty": "computerempty",
    "pcstats": "computerstats",
    "pcfind": "computerfind",
    "pcgrep": "computergrep",
    "pcdupes": "computerdupes",
    "pcduplicates": "computerdupes",
    "pctemp": "computertemp",
    "pcjunk": "computertemp",
    "pcsnapshot": "computersnapshot",
    "pcdiff": "computerdiff",
    "pcwatch": "computerwatch",
    "pcaudit": "computeraudit",
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

# Commands implemented inside fileforge.cli (the classic 40+ command set).
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

# Kept for backwards compatibility with earlier revisions of this launcher.
TREE_COMMANDS = {"tree", "treeui", "tree-gui", "treemap", "drives", "roots",
                 "computer", "pc", "thispc", "computerui", "pcgui"}

# The classic commands are still reachable, just not advertised in `help`.
LEGACY_CATALOG = [
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


def _all_names():
    names = []
    for _group, entries in CATALOG:
        names.extend(name for name, _help in entries)
    return names


def _bootstrap() -> int:
    try:
        from fileforge.cli import main
    except ImportError as exc:  # pragma: no cover
        print(f"fileforge: failed to import package: {exc}", file=sys.stderr)
        return 1
    return main(sys.argv[1:])


# --------------------------------------------------------------------------
# Live-tree / whole-computer handlers
# --------------------------------------------------------------------------
def _classic(argv) -> int:
    """Delegate to the classic argparse CLI (never back to ``cli.main``)."""
    from fileforge import cli as cli_mod
    handler = getattr(cli_mod, "main_classic", None) or cli_mod.main
    return handler(argv)


def _run_tree(rest) -> int:
    from fileforge.treeview import main as tree_main
    return tree_main(rest)


def _run_treemap(rest) -> int:
    from fileforge.treemap import main as treemap_main
    return treemap_main(rest)


def _run_treeui(rest) -> int:
    """Path given -> folder explorer.  No path -> whole computer."""
    if any(not a.startswith("-") for a in rest):
        from fileforge.treeui import main as treeui_main
        return treeui_main(rest)
    from fileforge.computerview import main as pc_main
    return pc_main(rest)


def _run_computer(rest) -> int:
    from fileforge.computer import main as computer_main
    return computer_main(rest)


def _run_computerui(rest) -> int:
    from fileforge.computerview import main as pc_main
    return pc_main(rest)


def _run_computerkit(cmd, rest) -> int:
    """Forward to the "This PC" analysis commands in fileforge.computerkit."""
    from fileforge.computerkit import run as kit_run
    return kit_run(cmd, rest)


def _run_filekit(cmd, rest) -> int:
    """Forward to the single-file tools in fileforge.filekit."""
    from fileforge.filekit import run as kit_run
    return kit_run(cmd, rest)


def _run_diskkit(cmd, rest) -> int:
    """Forward to the disk / volume tools in fileforge.diskkit."""
    from fileforge.diskkit import run as kit_run
    return kit_run(cmd, rest)


def _show_roots() -> int:
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


def _print_catalog(stream=None, catalog=None) -> None:
    out = stream or sys.stdout
    table = catalog or CATALOG
    out.write(f"{APP} - portable local file-system toolkit (This PC edition)\n")
    out.write("Usage: python fileforge.py <command> [options]\n")
    out.write("       python fileforge.py help              show this list\n")
    out.write("       python fileforge.py computerui        open This PC\n")
    out.write("       python fileforge.py <command> --help  "
              "options for one command\n\n")
    width = max(len(n) for _g, entries in table for n, _h in entries)
    for group, entries in table:
        out.write(f"{group}\n")
        for name, help_text in entries:
            extra = "".join(f" /{a}" for a, t in ALIASES.items() if t == name)
            out.write(f"  {name:<{width}}  {help_text}{extra}\n")
        out.write("\n")
    if catalog is None:
        out.write("Tip: every command supports --help.  Typos are auto-corrected\n")
        out.write("     (e.g. `computrui` runs `computerui`).\n")
        out.write("     Classic commands (ls, find, hash, cp, ...) still work:\n")
        out.write("     `python fileforge.py legacy` lists them.\n")


def _dispatch(args) -> int:
    """Full dispatcher.  Returns an exit code."""
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
        if cmd in ("-h", "--help"):
            _print_catalog()
            return 0
        if cmd == "tree-classic":
            return _classic(["tree"] + rest)
        if cmd == "tree":
            return _run_tree(rest)
        if cmd == "treeui":
            return _run_treeui(rest)
        if cmd == "treemap":
            return _run_treemap(rest)
        if cmd == "drives":
            return _show_roots()
        if cmd == "computer":
            return _run_computer(rest)
        if cmd == "computerui":
            return _run_computerui(rest)
        if cmd in CLASSIC_COMMANDS:
            return _classic([cmd] + rest)
    except ImportError as exc:
        print(f"{APP}: '{cmd}' needs the fileforge package ({exc})",
              file=sys.stderr)
        print(f"{APP}: GUI commands need tkinter "
              f"(Linux: sudo apt install python3-tk)", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130

    # Unknown command - suggest and, when obvious, just run it.
    known = sorted(set(_all_names()) | set(ALIASES))
    matches = difflib.get_close_matches(cmd, known, n=1, cutoff=0.7)
    if matches:
        guess = ALIASES.get(matches[0], matches[0])
        if difflib.SequenceMatcher(None, cmd, guess).ratio() >= 0.8:
            print(f"{APP}: interpreting '{cmd}' as '{guess}'", file=sys.stderr)
            return _dispatch([guess] + rest)
        print(f"{APP}: unknown command '{cmd}' (did you mean '{guess}'?)",
              file=sys.stderr)
    else:
        print(f"{APP}: unknown command '{cmd}'", file=sys.stderr)
    print(f"{APP}: run '{APP} help' to see all commands.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_dispatch(sys.argv[1:]))
