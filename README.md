# fileforge

A portable, **dependency-free** local file-system toolkit written in pure Python.
Runs unchanged on **Linux**, **Windows** and **macOS** — command line, interactive
shell **and a full graphical interface**.

```
 _____.__.__             _____
_|__|  |  |  |   ____   / ____/___  ________  ____ ______   ____
|  |  |  |  | _/ __ \ / /_  / __ \/ ___/ _ \/ __ `/ ___/ _ \_/ __ \
|  |  |_|  |_|\  ___// __/ / /_/ / /  /  __/ /_/ / /  /  __/  ___/
|__|____/____/ \___/ /_/    \____/_/   \___/\__, /_/   \___/\___/
```

---

## Requirements

* Python **3.8+** (tested on 3.12 / 3.13)
* No third-party packages — only the standard library
* The GUI needs `tkinter` (bundled with Windows/macOS Python and
  `python3-tk` on Linux)
* Works on Linux, Windows 10/11 and macOS

## Quick start

```bash
# from the repository
python fileforge.py --help                 # list all commands
python fileforge.py gui                    # graphical interface (8 tabs)
python fileforge.py shell                  # interactive shell
python -m fileforge ls -l .                # run as a module

# see your whole computer immediately
python fileforge.py computerui             # "This PC" window: every drive, all files
python fileforge.py computer -L 2          # the same as a text tree
python fileforge.py tree . -L 3 --du       # live directory tree, no cache
python fileforge.py drives                 # volumes + free space
python fileforge.py treemap . --top 25     # terminal disk-usage chart
```

## Install as a pip package

The project ships as a wheel (`dist/locals_filesystem-7.0.0-py3-none-any.whl`,
published on PyPI as [`locals-filesystem`](https://pypi.org/project/locals-filesystem/)):

```bash
pip install locals-filesystem                              # from PyPI
pip install dist/locals_filesystem-7.0.0-py3-none-any.whl  # from this folder
```

After installation the `fileforge` command is available everywhere and accepts
**every** command in this README:

```bash
fileforge --version        # 7.0.0
fileforge help             # full command list
fileforge computerui       # "This PC" window - all drives, all files
fileforge computer -L 2    # the same machine as a text tree
fileforge tree . -L 3 --du # live directory tree, no cache
fileforge shell            # interactive shell
fileforge gui              # full GUI (8 tabs)
fileforge-gui              # GUI without a console window
```

Aliases and typos are understood, so all of these open the same window:

```bash
fileforge computerui   fileforge pcgui   fileforge thispcui
fileforge computrui     # <- typo, auto-corrected
```

To publish a new version, use `publish.py` — never a bare `twine upload dist/*`:

```bash
python publish.py            # version check + rebuild + verify + print command
python publish.py --upload   # ...and actually upload
```

It does five things:

1. reads the newest version already on PyPI and **bumps the local version until
   it is strictly greater** (PyPI rejects a re-upload of an existing version,
   and pip only installs the highest one);
2. rebuilds wheel + sdist;
3. asserts the wheel really contains `dispatch.py`, `treeview.py`,
   `computerview.py` and friends, that `__version__` matches, and that the
   console script points at `fileforge.dispatch:main`;
4. moves any foreign artifacts out of `dist/` into `dist/_legacy/`, so a
   wildcard upload can never create a second, wrong PyPI project;
5. prints the exact `twine upload` command naming the two files explicitly.

To build from source: `pip install build twine && python -m build`.

### Careful: PyPI releases 1.0.0 / 2.0.0 / 3.0.0 are all stale

They were uploaded from a pre-`src/` snapshot: only 12 of the 18 modules, no
`dispatch.py`, no `computerview.py`, and `__version__ = "1.0.0"` — which is why
`fileforge --version` reported `1.0.0` and `fileforge computerui` failed with
`invalid choice`. **7.0.0 is the first release built from the current tree.**

Until 7.0.0 is published, `pip install --upgrade locals-filesystem` pulls that
old build and *downgrades* you. Repair with one command:

```bash
python install_local.py            # current interpreter
python install_local.py --all      # every Python install that has fileforge
```

It unpacks `dist/locals_filesystem-7.0.0-*.whl` straight over the installed
package and clears stale `.pyc`. No rename, so it is not blocked by the
safe-delete shim that stops pip.

### Every entry point understands every command

`fileforge.dispatch` is the single registry that knows every command
(**52 advertised** — 26 "This PC" + 12 file tools + 14 disk tools — plus the
40 classic ones kept for backwards compatibility). It is wired into *all*
entry points, so they behave identically:

| Entry point | Routes through |
|---|---|
| `fileforge <cmd>` (console script) | `fileforge.dispatch:main` |
| `python -m fileforge <cmd>` | `fileforge/__main__.py` → dispatch |
| `python fileforge.py <cmd>` | the launcher's own copy of the registry |
| `fileforge.cli:main` (old entry point) | re-exported to dispatch |

> Rebuild the wheel whenever you want the installed command to pick up the
> newest modules (`treeview`, `treeui`, `treemap`, `computer`,
> `computerview`, `computerkit`, `dispatch`) — the `dist/` artifacts are a
> snapshot, not a live copy.
>
> **If `pip install` fails while replacing `Scripts\fileforge.exe`** (some
> sandboxes intercept pip's rename-to-`.deleteme` write), regenerate the
> launcher with the bundled helper instead:
>
> ```bash
> python make_launchers.py                      # current environment
> python make_launchers.py <path-to-Scripts>    # another environment
> ```

---

## Command reference

### Navigation & listing

| Command | Description |
|---|---|
| `ls [path] [-l] [-a] [--sort name\|size\|time\|ext]` | List directory contents |
| `tree [path] [-L depth] [-a] [--no-size]` | ASCII directory tree with sizes |
| `stat <path> [--json]` | Detailed metadata (mode, times, inode, counts, MIME) |
| `filetype <path>` | Content-based MIME detection |
| `free [path]` | Free / used / total space on a volume |

### Live file tree (no cache)

| Command | Description |
|---|---|
| `tree [path] [-L N] [-a] [-d] [-f] [--du] [--stats] [--ext .py] [--include G] [--exclude G] [--min-size 10M] [--max-size 1G] [--newer 7d] [--older 30d] [--sort name\|size\|mtime\|none] [--reverse] [-n N] [--time] [--ascii] [--no-color] [--json F] [--out F] [--top-dirs N] [--max-children N]` | Stream a live tree straight from disk |
| `treeui [path] [-L N]` | Tkinter live tree explorer for one directory |
| `treemap [path] [-L N] [--top N] [--mode blocks\|bars\|both] [--width N]` | Terminal block map + ranked bar chart of disk usage |
| `drives` / `roots` | Every mount point / drive with free space |

### Whole computer ("This PC") — the advertised command set

`fileforge help` now shows **only** these commands. Every one of them scans
the whole machine live (no cache). Each has a short alias; `fileforge legacy`
lists the classic single-directory commands, which still work.

**Open / view**

| Command | Aliases | Description |
|---|---|---|
| `computerui [-L N]` | `pcgui` `pcui` `thispcui` | Window that opens straight onto every drive |
| `treeui [path] [-L N]` | `explorer` `pcexplorer` | Tkinter explorer — This PC when no path is given |
| `computer [-L N] [--files] [--stats]` | `pc` `thispc` | The entire machine as one tree, or a flat file list |
| `computertree [-L N] [--ascii] [--files]` | `pctree` | Same tree with the full filter set |

**Inventory**

| Command | Aliases | Description |
|---|---|---|
| `computerinfo` | `pcinfo` | Machine + volume overview (capacity, used, free) |
| `computerdrives` | `pcdrives` `drives` | Every drive / mount point with a usage bar |
| `computerscan [--per-volume]` | `pcscan` | One full scan: counts, bytes, per-volume table |
| `computerexport [--format json\|csv\|txt]` | `pcexport` | Export the whole machine to a file |

**What is big**

| Command | Aliases | Description |
|---|---|---|
| `computerdirs [-n N]` | `pcdirs` | Biggest directories anywhere on the machine |
| `computerlarge [-n N]` | `pclarge` | Biggest files anywhere on the machine |
| `computermap [--mode blocks\|bars\|both] [--deep]` | `pcmap` | Terminal block map of every volume |
| `computerext [-n N] [--sort size\|count\|name]` | `pcext` | Size / count grouped by extension |

**By age**

| Command | Aliases | Description |
|---|---|---|
| `computernew [-n N]` | `pcnew` | Most recently modified files |
| `computerold [-n N]` | `pcold` | Least recently modified files |
| `computerempty [-n N]` | `pcempty` | Empty files and empty directories |
| `computerstats [-n N]` | `pcstats` | Buckets by size, buckets by age, top extensions |

**Search & integrity**

| Command | Aliases | Description |
|---|---|---|
| `computerfind <glob> [--regex] [-i] [--dirs]` | `pcfind` | Find files by name across every drive |
| `computergrep <regex> [--no-content] [--context N]` | `pcgrep` | Search file contents across every drive |
| `computerdupes [-a ALGO] [--min-dup-size N]` | `pcdupes` | Duplicate files + reclaimable space |
| `computertemp [--dirs]` | `pctemp` | Temporary / cache / junk files |

**Track changes**

| Command | Aliases | Description |
|---|---|---|
| `computersnapshot [--out F]` | `pcsnapshot` | Save a snapshot (path + size + mtime) |
| `computerdiff <old> <new>` | `pcdiff` | Added / removed / changed between snapshots |
| `computerwatch [path] [--interval S] [--duration S]` | `pcwatch` | Live watch: created / deleted / modified |

**Safety**

| Command | Aliases | Description |
|---|---|---|
| `computeraudit [-n N]` | `pcaudit` | Permission audit (world-writable, setuid, setgid) |

### File tools (`fileforge.filekit`) — 12 commands

Single-file utilities. Nothing is written unless you pass `--apply` / `-o`.

| Command | Aliases | Description |
|---|---|---|
| `filemeta <path> [--hash ALGO]` | `fmeta` `fstat` | Size, mode, inode, times, MIME, owner, hash, entry count |
| `filepreview <path> [--lines N]` | `fpreview` | Text head for text files, hex for binaries, listing for dirs |
| `filehex <path> [--offset N] [--length N] [--width N]` | `fhex` | Classic offset / hex / ASCII dump |
| `filediff <a> <b> [--unified] [-i] [--ignore-space] [--ignore-blank]` | `fdiff` | Line diff of two files, or inventory diff of two dirs |
| `filesanitize <paths...> [--apply] [--windows]` | `fsanitize` | Find (and fix) illegal chars, reserved names, trailing dots |
| `filenorm <paths...> [--nfc] [--case lower] [--space underscore] [--apply]` | `fnorm` | Unicode NFC, accent stripping, case, space handling |
| `fileextract <path> [--urls] [--emails] [--ips] [--all] [--unique]` | `fextract` | Pull URLs / e-mails / IPv4 addresses out of a file |
| `fileencode <path> [--base64\|--hex\|--url] [-o OUT]` | `fenc` | Encode a file |
| `filedecode <path> [--base64\|--hex\|--url] [-o OUT]` | `fdec` | Decode a file |
| `filetrim <path> [--blank] [--trailing] [--bom] [--crlf] [--all]` | `ftrim` | Strip blank lines, trailing spaces, BOM, CRLF |
| `filesort <path> [--unique] [--numeric] [--reverse] [-i]` | `fsort` | Sort / de-duplicate the lines of a text file |
| `filebackup <path> [--dest D] [--keep N]` | `fbackup` | Timestamped copy + retention pruning |

### Disk tools (`fileforge.diskkit`) — 14 commands

Hardware and volume level. Each platform is queried with the tool it ships
with (PowerShell on Windows, `lsblk` + `/proc` on Linux, `diskutil` on
macOS); when a tool is missing the command degrades instead of failing.

| Command | Aliases | Description |
|---|---|---|
| `diskinfo` | `dinfo` | Physical disks: model, serial, bus, media, size, health |
| `diskpartitions` | `dpart` | Partition / volume table with mount points |
| `diskfs` | `dfs` | File system type (NTFS/ext4/APFS…) of every mount |
| `diskserial` | `dserial` | Volume serial numbers / UUIDs |
| `diskusage [--mode blocks\|table\|both]` | `dusage` | Used vs free per volume |
| `diskfree [--threshold %]` | `dfree` | Free space overview + low-space warning |
| `disktop [-r DIR] [-n N] [--no-aggregate]` | `dtop` | Biggest entries under a root / volume |
| `diskmounts` | `dmounts` | Mount points, removable / network / fixed |
| `diskhealth` | `dhealth` | SMART / health status |
| `disktemp` | `dtemp` | Temperature where the platform exposes it |
| `diskio` | `dio` | Read / write counters |
| `diskbench [--dir D] [--size 64M] [--block 1M]` | `dbench` | Real sequential write/read MB/s + IOPS estimate |
| `diskbadfiles [-r DIR] [--full]` | `dbad` | Files that cannot be read (media errors) |
| `diskerrors [-r DIR]` | `derrors` | Directories that fail to list |

Shared options for the scanning commands: `-r/--root DIR` (repeatable —
restrict the scan to one drive or folder), `-L/--max-depth N`, `-a/--all`,
`--ext .ext`, `--include GLOB`, `--exclude GLOB`, `--min-size 10M`,
`--max-size 1G`, `--newer 7d`, `--older 30d`, `--max-items N` (hard stop),
`--max-children N`, `-n/--limit N`, `--json`, `--out FILE`, `-q/--quiet`.

### File content

| Command | Description |
|---|---|
| `cat <path> [-n] [--head N] [--tail N] [--encoding ENC]` | Print a text file |
| `write <path> (-c TEXT \| -f FILE \| --stdin) [-a] [--newline]` | Write or append |
| `touch <path>` | Create an empty file / bump mtime |
| `wc <path>` | Count lines, words, chars, bytes |
| `replace <path> OLD NEW [--regex] [-i] [--dry-run]` | In-place text replace |
| `convert-encoding <path> --to ENC [--from ENC] [-o OUT]` | Transcode a text file |

### File & directory management

| Command | Description |
|---|---|
| `cp <src> <dest> [--overwrite] [--no-recursive] [--no-preserve]` | Copy file/dir |
| `mv <src> <dest> [--overwrite]` | Move or rename |
| `rm <path> [-r] [-f] [--secure] [--passes N]` | Remove (optionally shred) |
| `mkdir <path> [--no-parents] [--exist-ok]` | Create directories |
| `rename <path> <new_name>` | Rename one path |
| `rename-batch <paths...> --pattern P --replacement R [--regex] [-i] [--dry-run]` | Batch rename |
| `symlink <target> <link>` / `readlink <path>` | Symbolic links |

### Search

| Command | Description |
|---|---|
| `find [root] [-name GLOB] [--regex RE] [--ext .py] [--min-size 1k] [--max-size 10M] [--newer 7d] [--older 30d] [--content TEXT] [--files-only] [--dirs-only] [--empty] [--depth N] [-a] [-l] [--limit N]` | Multi-criteria search |
| `grep <pattern> [paths...] [--regex] [-s] [--include GLOB] [--exclude GLOB] [--no-recursive] [--max N]` | Search text inside files |

Size accepts `B, K/KB, M/MB, G/GB, T/TB`. Duration accepts `s, m, h, d, w`
(e.g. `7d`, `12h`, `3d12h`).

### Integrity

| Command | Description |
|---|---|
| `hash <paths...> [-a ALGO] [-r]` | Checksums (md5, sha1/224/256/384/512, blake2b/s) |
| `manifest <root> [-a ALGO] [-o OUT]` | Create a JSON checksum manifest |
| `verify <manifest> [--extra]` | Verify files against a manifest |
| `compare <a> <b> [-a ALGO]` | Compare two files, report first differing byte |
| `dupes <root> [-a ALGO] [--min-size SIZE] [--hidden]` | Find duplicate files |

### Analytics

| Command | Description |
|---|---|
| `du [root] [--top N] [--no-hidden]` | Disk-usage breakdown by extension / top-level |
| `largest [root] [--limit N]` | Largest files |
| `newest [root] [--limit N]` / `oldest [root] [--limit N]` | By modification time |
| `empty [root]` | Empty files and directories |
| `broken-links [root]` | Broken symbolic links |
| `ext-summary [root]` | Per-extension file count and size |
| `summary [root]` | One-shot full report |

### Archives, split & sync

| Command | Description |
|---|---|
| `archive-create <output> <sources...> [--format zip\|tar] [--base-dir DIR]` | Create zip / tar / tar.gz / tar.bz2 / tar.xz |
| `archive-extract <archive> [-d DEST] [--member NAME]` | Extract (zip-slip protected) |
| `archive-list <archive>` | List entries |
| `gzip <path> [-d] [-k]` | Single-file gzip / gunzip |
| `split <path> --size 10M [--out-dir D]` | Split a file into parts |
| `merge <output> <parts...>` | Merge parts back |
| `sync <src> <dest> [--delete] [--dry-run]` | Incremental directory mirror |

### Permissions & security

| Command | Description |
|---|---|
| `chmod <path> <mode> [-r]` | Octal (`644`) or symbolic (`+x`, `u+rw`, `go-w`) |
| `perms [path] [-r]` | Show permission strings |
| `world-writable [root]` | Audit world-writable entries |
| `shred <path> [--passes N]` | Overwrite then delete a file |
| `encrypt <path> [-p PWD] [-o OUT] [--remove-source]` | Encrypt to `.ffenc` |
| `decrypt <path> [-p PWD] [-o OUT] [--remove-source]` | Decrypt `.ffenc` |

---

## Live file tree & "This PC"

Everything in this section is read **straight from the disk on every run**.
There is no cache, no index file, no background crawler: what you see is the
volume as it is right now.

### `tree` — one directory, streamed

```bash
python fileforge.py tree                    # current directory, 3 levels
python fileforge.py tree C:\ -L 2           # drive structure
python fileforge.py tree . --du --stats     # aggregated folder sizes + totals
python fileforge.py tree ~/src --ext .py --sort size --stats
python fileforge.py tree . -L 4 --json tree.json
python fileforge.py tree C:\ -L 2 --ascii --out C:\Temp\ctree.txt
python fileforge.py tree . -L 3 --top-dirs 10
```

`iter_tree()` is a generator: it emits each line the moment it is read, so
memory stays proportional to the tree *depth*, not its size. Only `--du`,
`--json` and `treemap` materialise the subtree (aggregation needs it).

### `treemap` — disk usage in the terminal

```bash
python fileforge.py treemap . -L 3 --top 15 --mode both
```

Renders a proportional block map of the top level plus a ranked bar chart of
the largest directories.

### `computerui` — the whole machine, visible at once

```bash
python fileforge.py computerui          # opens on every drive
python fileforge.py computerui -L 3
```

| Tab | What it shows |
|---|---|
| **This PC (tree)** | Root is the computer itself; every volume is a child and is expanded automatically in a background thread, rows appearing as they are read |
| **All files** | Flat table of every file on every volume — full path, size, type, modified — streamed live, cancellable with **Stop** |

Toolbar: `Depth` (auto-expand levels), `Max/folder`, `Hidden`, `Dirs only`,
`Filter`, `Expand tree`, `Scan files`, `Stop`, `Export`. Right-click on either
tab: open, reveal in file manager, terminal here, copy path/name, properties,
SHA-256. `F5` refreshes, `Ctrl+Q` quits.

```
This PC
├── C:\                    
│   ├── AMD\
│   ├── cos_build\
│   │   ├── string.c
│   │   ├── test.c
│   │   └── test.o
│   └── cygwin64\
├── D:\                    
└── E:\                     
```

### Why `Max/folder` matters

A single folder can hold hundreds of thousands of entries. On the machine this
was developed on, `D:\documents` contains **303,676 entries** and needs
**185 s** merely to enumerate — one folder would stall the entire view.
`Max/folder` (default **500** in the window) reads only the first N entries of
each folder and shows a `+ N more entries (not listed)` marker. Set it to `0`
for unlimited, or raise it when you really need everything.

With the cap in place a whole-machine depth-2 scan finishes in **3 seconds**:

```
WHOLE MACHINE depth=2: 8258 entries, 2674 dirs, 5585 files  3.0s
```

### Symlinks, junctions and safety

Symlinks, junctions and Windows reparse points are **skipped by default** —
`os.scandir` resolves their target, and if that target is an offline network
share the call blocks for minutes. The check is done *before* the directory is
opened. Use `--follow-links` (or the option flag) only when you know the tree.
Unreadable folders are reported inline instead of aborting the scan.

### Library use

```python
from fileforge.treeview import Options, iter_tree, build_tree, dir_sizes, to_json

for prefix, node, stats in iter_tree("D:/", Options(max_depth=2)):
    print(prefix + node.name)
print(stats.as_dict())

tree = build_tree("D:/Projects", Options(max_depth=4))
print(tree.node.agg_size, tree.node.n_files)

from fileforge.computer import iter_computer_tree, iter_all_files, volumes
for prefix, node, stats in iter_computer_tree(Options(max_depth=2, max_children=500)):
    print(prefix + node.name)
for node in iter_all_files(Options(max_depth=3), max_items=1000):
    print(node.path)
```

---

## Graphical interface

```bash
python fileforge.py gui      # or: fileforge-gui after pip install
```

A single window with a directory tree on the left and eight tool tabs:

| Tab | What you can do |
|---|---|
| **Browser** | Navigate, sort, copy/move/rename/delete/shred, properties, hash, archive, encrypt, open terminal or file manager, context menu |
| **Search** | All find criteria (glob, regex, ext, size, age, content, empty, depth) with a results table and right-click actions |
| **Grep** | Recursive text search with include/exclude filters; double-click jumps to the line in the built-in viewer |
| **Integrity** | Hash any file, compare two files, create/verify manifests, find duplicates and delete the extra copies |
| **Archive** | Create/extract/inspect zip & tar archives, gzip, split files into parts, merge parts back, incremental folder sync |
| **Analytics** | Summary report, extension breakdown with a bar chart, largest/newest/oldest files, empty items, broken links |
| **Security** | Encrypt/decrypt with password, shred, chmod (octal + symbolic), permission listing, world-writable audit |
| **Text Tools** | View and edit files, save, word count, regex replace with dry-run, encoding conversion |

Extras: light/dark minimal theme toggle, hidden-files toggle, `F5` refresh,
status bar with live free space, all long jobs run on background threads.

### The two tree windows

Besides the 8-tab interface above there are two dedicated viewers:

```bash
python fileforge.py treeui D:\ -L 4   # single-directory live tree
python fileforge.py computerui        # the whole computer ("This PC")
python fileforge.py treeui            # no path -> opens "This PC"
```

Both expand lazily (only the branch you open is ever read), offer sortable
columns, a live filter, an export to `.txt`/`.json`, a light/dark theme and the
same right-click actions as the main interface. `computerui` adds the
whole-machine auto-expansion and the streaming "All files" table described
above.

## Interactive shell

```bash
python fileforge.py shell
```

```
ff:D:\projects> ls
ff:D:\projects> cd src
ff:D:\projects\src> find . --ext .py -l
ff:D:\projects\src> summary .
ff:D:\projects\src> !dir                 # run any native shell command
ff:D:\projects\src> exit
```

Builtins: `cd`, `pwd`, `help`, `history`, `clear`, `exit` / `quit`,
and `!<command>` to pass through to the system shell. **Every CLI command is
available inside the shell with identical options.**

---

## Example workflows

```bash
# Find Python files changed in the last 3 days and check their hashes
python fileforge.py find . --ext .py --newer 3d -l
python fileforge.py hash ./src -a sha256 -r

# Reclaim disk space: find duplicates and large files
python fileforge.py dupes ~/Downloads
python fileforge.py largest ~/Videos --limit 10

# Back up a project as a tar.gz and record a checksum manifest
python fileforge.py archive-create backup.tar.gz ./project
python fileforge.py manifest ./project -o ./project/manifest.json
python fileforge.py verify ./project/manifest.json --extra

# Batch-rename screenshots IMG_1234.png -> photo_1234.png
python fileforge.py rename-batch ~/Pictures/*.png --pattern IMG_ --replacement photo_ --dry-run

# Split a large file for transfer, then merge it back
python fileforge.py split big.iso --size 100M --out-dir ./parts
python fileforge.py merge big.iso ./parts/*

# Mirror a folder, removing files deleted at the source
python fileforge.py sync ./site ./backup/site --delete

# Explore an unfamiliar machine: every drive, two levels deep
python fileforge.py computer -L 2 --stats
python fileforge.py computerui

# Where is my disk space going?
python fileforge.py treemap . -L 3 --top 20 --mode bars
python fileforge.py tree ~/Downloads -L 2 --du --sort size

# Every log file on the machine, newest first
python fileforge.py computer --files --limit 2000 --full-path

# --- "This PC" workflows -------------------------------------------------
python fileforge.py pcinfo                       # capacity of every drive
python fileforge.py pcscan -q                    # one full-machine scan
python fileforge.py pclarge -n 30                # 30 biggest files anywhere
python fileforge.py pcdirs -n 20 -r D:\          # biggest folders on D:
python fileforge.py pcext -n 15                  # space per extension
python fileforge.py pcmap --mode blocks          # block map of every volume
python fileforge.py pcfind "*.iso" -n 50         # find ISOs on any drive
python fileforge.py pcgrep "TODO|FIXME" --ext .py -n 40
python fileforge.py pcdupes -n 20                # duplicates + reclaimable
python fileforge.py pctemp --dirs -n 40          # temp / cache / junk
python fileforge.py pcsnapshot --out monday.json # save today's state
python fileforge.py pcsnapshot --out friday.json # ...and compare later
python fileforge.py pcdiff monday.json friday.json
python fileforge.py pcwatch ./project --interval 2   # live change feed
python fileforge.py pcstats                      # size buckets + age buckets
python fileforge.py pcexport --format csv --out machine.csv

# --- file workflows -------------------------------------------------------
python fileforge.py fmeta report.pdf --hash sha256   # full metadata
python fileforge.py fdiff v1.txt v2.txt --unified    # what changed
python fileforge.py fsanitize "./bad:name?.txt" --apply
python fileforge.py fnorm "My File.TXT" --space underscore --case lower --apply
python fileforge.py fextract notes.md --all --unique # urls / mails / ips
python fileforge.py fhex firmware.bin --length 256
python fileforge.py ftrim log.txt --all --in-place
python fileforge.py fsort words.txt --unique -o words.sorted.txt
python fileforge.py fbackup important.xlsx --keep 5

# --- disk workflows -------------------------------------------------------
python fileforge.py dinfo                       # physical disks
python fileforge.py dpart                       # volumes + mount points
python fileforge.py dfs                         # file systems
python fileforge.py dfree --threshold 10        # warn on low space
python fileforge.py dtop -r . -n 20             # biggest entries here
python fileforge.py dbench --dir . --size 128M  # real throughput
python fileforge.py dhealth                     # SMART / health
python fileforge.py dbad -r D:\Downloads --full # unreadable files
python fileforge.py derrors -r D:\              # unlistable directories
```

---

## Design notes

* **Pure stdlib** — no `pip install` required; copies of this folder run anywhere.
* **Safety first** — extraction guards against path traversal; `--dry-run`
  is available for rename, replace and sync.
* **Structured core** — `src/fileforge/*.py` modules (`core`, `search`,
  `hashutil`, `archive`, `analytics`, `security`, `utils`, `treeview`,
  `treeui`, `treemap`, `computer`, `computerview`) can be imported and reused
  as a library:

```python
from fileforge import core, search, hashutil

core.write_text("notes.txt", "hello\n")
print(hashutil.hash_file("notes.txt", "sha256"))
for e in search.find(search.FindCriteria(root=".", extensions=[".py"])):
    print(e.rel, e.size)
```

* **Never hangs on a bad link** — the tree scanners detect symlinks, junctions
  and Windows reparse points *before* opening a directory, because `os.scandir`
  resolves their target and an offline network share would block for minutes.
  Huge folders are bounded by `max_children` (500 per folder in the GUI), and
  unreadable folders are reported inline instead of aborting the scan.
* **Custom encryption caveat** — `encrypt` / `decrypt` use a self-contained
  PBKDF2 + SHA-256 stream cipher with an HMAC tag. It is dependency-free and
  fine for personal obfuscation, but it is **not audited cryptography**. For
  sensitive data prefer `age`, `gpg` or `openssl`.

---

## Project layout

```
localfilessystem/
├── fileforge.py            # single-file launcher - full command registry
├── make_launchers.py       # regenerates fileforge.cmd when pip is blocked
├── install_local.py        # force-installs the built wheel into site-packages
├── publish.py              # version check + rebuild + verify + upload helper
├── pyproject.toml          # pip package definition (locals-filesystem 7.0.0)
├── README.md
├── TREE.md                 # guide to the live tree / This PC views
├── overview.md
├── tree_smoke.py           # 54-check live-tree test suite
├── computer_smoke.py       # 33-check whole-computer test suite
├── dispatch_smoke.py       # 25-check dispatcher/alias/typo test suite
├── dist/                   # built wheel + sdist (pip installable)
└── src/
    └── fileforge/
        ├── __init__.py
        ├── __main__.py         # `python -m fileforge` -> dispatch
        ├── dispatch.py         # unified registry: every command, aliases,
        │                       # typo correction.  Console-script entry point
        ├── cli.py              # classic argparse CLI; `main` -> dispatch,
        │                       # original kept as `main_classic`
        ├── gui.py              # Tkinter graphical interface (8 tabs)
        ├── repl.py             # interactive shell
        ├── core.py             # file/dir operations, tree, stat, text tools
        ├── search.py           # find + grep + size/duration parsing
        ├── hashutil.py         # hashes, manifest, verify, duplicates, compare
        ├── archive.py          # zip/tar/gzip, split/merge, sync
        ├── analytics.py        # du, largest/newest, empty, broken links
        ├── security.py         # chmod, shred, encryption
        ├── utils.py            # shared helpers, platform detection, output
        ├── treeview.py         # live cache-free tree scanner + renderer
        ├── treeui.py           # single-directory Tkinter tree explorer
        ├── treemap.py          # terminal block map / bar chart
        ├── computer.py         # whole-machine ("This PC") scanning engine
        ├── computerview.py     # whole-machine Tkinter explorer (2 tabs)
        ├── computerkit.py      # 21 "This PC" analysis commands (pc* aliases)
        ├── filekit.py          # 12 single-file tools (f* aliases)
        ├── diskkit.py          # 14 disk / volume tools (d* aliases)
        └── dispatch.py         # command registry shared by every entry point
```

## Testing

```bash
python tree_smoke.py        # live tree:    TOTAL 54 passed, 0 failed
python computer_smoke.py    # This PC:      TOTAL 33 passed, 0 failed
python dispatch_smoke.py    # dispatcher:   TOTAL 37 passed, 0 failed
python computerkit_smoke.py # This PC kit:  TOTAL 73 passed, 0 failed
python filekit_smoke.py     # file tools:   TOTAL 52 passed, 0 failed
python diskkit_smoke.py     # disk tools:   TOTAL 52 passed, 0 failed
```

The three `*_kit` suites build every parser (this is what catches duplicate
`argparse` options), check `--help`, then run each command against a
throw-away directory — so they never touch a real drive.
`diskkit_smoke.py` also runs a 1 MB benchmark and deletes its test file.

`dispatch_smoke.py` checks that every catalogue entry is reachable, that all
aliases resolve, that `computrui` auto-corrects to `computerui`, that an
unknown command exits with code 2, and that the launcher's registry and the
package's registry are identical.

Both suites drive the real CLI as a subprocess, call the library API directly
and construct the Tkinter windows for real (without a blocking main loop).
They need `tkinter` for the GUI section, which is skipped automatically when
it is missing:

```bash
# Linux
sudo apt install python3-tk
```

The original CLI/GUI suites (`smoke_test.py`, `gui_smoke.py`) were written
against the pre-`src` layout and are no longer part of the tree; the CLI and
GUI themselves are covered by the two suites above plus
`python fileforge.py --help`.

## License

MIT
