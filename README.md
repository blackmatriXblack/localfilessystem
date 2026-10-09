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
python fileforge.py gui                    # graphical interface
python fileforge.py shell                  # interactive shell
python -m fileforge ls -l .                # run as a module
```

## Install as a pip package

The project ships as a wheel (`dist/fileforge_toolkit-1.0.0-py3-none-any.whl`):

```bash
pip install dist/fileforge_toolkit-1.0.0-py3-none-any.whl
```

After installation two commands are available everywhere:

```bash
fileforge --version        # CLI (all 40+ commands)
fileforge shell            # interactive shell
fileforge-gui              # graphical interface (no console window)
fileforge gui              # GUI via the CLI entry point
```

To publish to PyPI (once you own the name):

```bash
python -m build            # rebuild dist/
twine upload dist/*
```

To build from source: `pip install build && python -m build`.

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
```

---

## Design notes

* **Pure stdlib** — no `pip install` required; copies of this folder run anywhere.
* **Safety first** — extraction guards against path traversal; `--dry-run`
  is available for rename, replace and sync.
* **Structured core** — `fileforge/*.py` modules (`core`, `search`, `hashutil`,
  `archive`, `analytics`, `security`, `utils`) can be imported and reused as a
  library:

```python
from fileforge import core, search, hashutil

core.write_text("notes.txt", "hello\n")
print(hashutil.hash_file("notes.txt", "sha256"))
for e in search.find(search.FindCriteria(root=".", extensions=[".py"])):
    print(e.rel, e.size)
```

* **Custom encryption caveat** — `encrypt` / `decrypt` use a self-contained
  PBKDF2 + SHA-256 stream cipher with an HMAC tag. It is dependency-free and
  fine for personal obfuscation, but it is **not audited cryptography**. For
  sensitive data prefer `age`, `gpg` or `openssl`.

---

## Project layout

```
localfilessystem/
├── fileforge.py            # single-file launcher
├── README.md
└── fileforge/
    ├── __init__.py
    ├── __main__.py         # enables `python -m fileforge`
    ├── cli.py              # argparse dispatcher + all command impls
    ├── gui.py              # Tkinter graphical interface
    ├── repl.py             # interactive shell
    ├── core.py             # file/dir operations, tree, stat, text tools
    ├── search.py           # find + grep + size/duration parsing
    ├── hashutil.py         # hashes, manifest, verify, duplicates, compare
    ├── archive.py          # zip/tar/gzip, split/merge, sync
    ├── analytics.py        # du, largest/newest, empty, broken links
    ├── security.py         # chmod, shred, encryption
    └── utils.py            # shared helpers, platform detection, output
```

## Testing

```bash
python smoke_test.py        # CLI:  TOTAL 56 passed, 0 failed
python gui_smoke.py         # GUI:  TOTAL 17 passed, 0 failed (needs tkinter)
```

## License

MIT
