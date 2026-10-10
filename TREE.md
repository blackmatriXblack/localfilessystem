# fileforge — Live File-System Tree

Shows the real structure of your computer as a tree, **straight from disk**.
No cache, no index file, no background crawler: every run re-reads the volume
through `os.scandir`, and every GUI expansion is a fresh read.

Works on **Linux / Windows / macOS**, standard library only.

---

## Quick start

```bash
python fileforge.py computerui                 # <<< the whole computer, on screen
python fileforge.py computer -L 2              # whole machine as a text tree
python fileforge.py tree                       # current directory, depth 3
python fileforge.py tree C:\ -L 2              # drive structure, 2 levels
python fileforge.py tree . --du --stats        # aggregated dir sizes + totals
python fileforge.py drives                     # mount points / drives + free space
python fileforge.py treemap . --top 25         # terminal disk-usage chart
python fileforge.py treeui D:\ -L 4            # single-directory explorer window
```

---

## "This PC" — see the whole computer at once

`computerui` opens straight onto the machine: no folder picking, every drive
is already there.

```bash
python fileforge.py computerui          # window, auto-expands every drive
python fileforge.py computerui -L 3     # deeper auto-expansion
python fileforge.py computer -L 2       # same thing as text in the terminal
python fileforge.py computer --volumes  # just the drives + free space
python fileforge.py computer --files --limit 500 --full-path
```

### Window layout

| Tab | What it shows |
|---|---|
| **This PC (tree)** | Root is the computer; every volume is a child and is expanded automatically on start-up (background thread, rows appear as they are read) |
| **All files** | Flat table of every file on every volume — full path / size / type / modified; streams in live, `Stop` cancels |

| Control | Meaning |
|---|---|
| `Depth` | How many levels to auto-expand (1–16) |
| `Max/folder` | Cap on entries listed per directory (default 500, `0` = unlimited) |
| `Hidden` / `Dirs only` | Standard filters |
| `Filter` | Substring match on names |
| `Expand tree` / `Scan files` / `Stop` | Start or cancel a background scan |
| `Export` | Save the tree as text, or the file list as JSON |
| `F5` / `Ctrl+Q` | Refresh / quit |

Right-click works on both tabs: open, reveal in file manager, terminal here,
copy path/name, properties, SHA-256.

### Why "Max/folder" exists

A single folder can hold hundreds of thousands of entries. On this machine
`D:\documents` contains **303,676** entries and needs **185 s** just to
enumerate — one folder would stall the whole view. With `Max/folder` set, only
the first N entries of each folder are read and a
`+ N more entries (not listed)` marker is shown. Raise it (or set `0`) if you
really want everything.

Measured: whole machine, depth 2, `Max/folder 500` → **8,258 entries in 3.0 s**,
streamed into the window as they are found.

---

## Commands

| Command | What it does |
|---|---|
| `tree [PATH]` | Stream a tree to the terminal |
| `treeui [PATH]` | Open the live Tkinter tree explorer |
| `treemap [PATH]` | Terminal block map + ranked bar chart of disk usage |
| `drives` / `roots` | List mount points / drive letters with free space |

### `tree` options

| Option | Meaning |
|---|---|
| `-L, --max-depth N` | How many levels to descend (default 3) |
| `-a, --all` | Include dotfiles / hidden entries |
| `-d, --dirs-only` | Directories only |
| `-f, --files-only` | Files only |
| `--follow-links` | Follow symlinks / junctions (off by default, see *Safety*) |
| `--min-size 10M` / `--max-size 1G` | Size filter |
| `--newer 7d` / `--older 30d` | Modification-time filter |
| `--ext .py` | Extension filter (repeatable) |
| `--include '*.log'` / `--exclude 'node_modules'` | Glob filters (repeatable) |
| `--sort name\|size\|mtime\|none` | Sort order |
| `--reverse` | Reverse the sort |
| `-n, --limit N` | Stop after N entries |
| `--du` | Show aggregated directory sizes and file counts |
| `--stats` | Print a totals line at the end |
| `--time` | Show modification times |
| `--ascii` | Use ASCII branch characters (`|--`) instead of Unicode (`├──`) |
| `--no-color` | Disable ANSI colors |
| `--json FILE` | Export the tree as JSON |
| `--out FILE` | Write the tree text to a file |
| `--top-dirs N` | Print the N largest directories instead of a tree |

### Examples

```bash
python fileforge.py tree . -L 3 --dirs-only
python fileforge.py tree ~/Projects --ext .py --sort size --stats
python fileforge.py tree C:\ -L 2 --ascii --out C:\Temp\ctree.txt
python fileforge.py tree . -L 4 --json tree.json
python fileforge.py treemap . -L 3 --top 15 --mode bars
```

---

## `treeui` — the explorer window

| Feature | Detail |
|---|---|
| Lazy expansion | Only the branch you open is ever read from disk |
| Columns | Name / Size / Type / Modified (click headers to sort) |
| Live filter | Substring match on names, applied on refresh |
| Toggles | Hidden entries, directories-only, depth (1–32) |
| Right-click menu | Open, reveal in file manager, terminal here, copy path/name, properties, SHA-256, set as root, expand branch |
| Double click | Folder → expand/collapse; file → open with the default app |
| Export | Whole tree to `.txt` or `.json` (runs in a background thread) |
| Theme | Light / dark (View ▸ Toggle theme) |
| Keys | `F5` refresh, `Ctrl+O` pick root, `Ctrl+Q` quit |

---

## How "no cache" is guaranteed

* Nothing is written to disk. There is no index file, no SQLite store, no
  pickle, no temp file. The only persistent output is created when **you**
  explicitly pass `--json` or `--out`.
* `iter_tree()` is a generator: it yields a line the moment it is read, so
  memory stays proportional to tree *depth*, not tree *size*.
* `build_tree()` (used only for `--du`, `--json` and `treemap`) is the single
  exception — aggregation needs the whole subtree, so it materialises it.
* The GUI re-scans on every expansion and on every `F5`.

Measured on this machine, a depth-2 scan of `C:\` (553 entries, 401
directories) completes in **0.02 s**.

---

## Safety

* Symlinks, junctions and Windows reparse points are **skipped by default**.
  They frequently point at offline network locations and would otherwise
  block a scan for minutes. Use `--follow-links` only when you know the tree.
* Unreadable directories are reported inline as `<PermissionError: ...>`
  instead of aborting the scan, and counted in `--stats`.
* Depth is capped at 512 so a runaway `-L` can never overflow the stack.

---

## Library use

```python
from fileforge.treeview import Options, iter_tree, build_tree, dir_sizes, to_json

# streaming (constant memory)
for prefix, node, stats in iter_tree("D:/", Options(max_depth=2)):
    print(prefix + node.name)
print(stats.as_dict())

# aggregated (materialised)
tree = build_tree("D:/Projects", Options(max_depth=4))
print(tree.node.agg_size, tree.node.n_files)

for path, size, files in dir_sizes("D:/", Options(max_depth=3), top=10):
    print(path, size, files)
```

```python
from fileforge.treemap import collect, render_blocks, render_bars

top_level, largest = collect(".", Options(max_depth=3), top=20)
print("\n".join(render_blocks(top_level, color=False)))
print("\n".join(render_bars(largest, color=False)))
```

```python
from fileforge.treeui import run

run("D:/", max_depth=3)   # opens the window, blocks until closed
```

---

## New files added

```
src/fileforge/treeview.py       # live scanner + renderer + CLI (no cache)
src/fileforge/treeui.py         # Tkinter single-directory explorer window
src/fileforge/treemap.py        # terminal block map / bar chart
src/fileforge/computer.py       # whole-machine ("This PC") scanning engine
src/fileforge/computerview.py   # whole-machine explorer window (2 tabs)
tree_smoke.py                   # 54-check end-to-end test
computer_smoke.py               # 33-check end-to-end test
TREE.md                         # this document
```

`fileforge.py` gained a `src` path shim plus a dispatcher for
`tree` / `treeui` / `treemap` / `drives` / `computer` / `computerui`.
Nothing was removed.

## Testing

```bash
python tree_smoke.py
# TREE TOTAL: 54 passed, 0 failed
```

Requires `tkinter` only for the GUI section (the test skips it otherwise).
On Linux: `sudo apt install python3-tk`.
