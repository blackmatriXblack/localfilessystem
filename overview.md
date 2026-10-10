# fileforge — "This PC" + file & disk tools (7.0.0)

**Command count: 52 advertised** = 26 "This PC" + 12 file tools + 14 disk
tools (plus 40 classic commands kept working but hidden behind
`fileforge legacy`).

Portable, dependency-free local file-system toolkit for Linux / Windows /
macOS. This revision refocuses the command surface on the **whole computer**
("This PC") workflow: `fileforge help` now lists only This PC commands, the
full GUI command is gone, and 21 new machine-wide analysis commands were
added. Rebuilt as **locals-filesystem 7.0.0** (wheel + sdist).

## What changed

### 1. Command catalogue slimmed down to "This PC"

* `fileforge help` shows **26 commands**, all of them whole-computer.
* The full Tkinter GUI command (`gui`) was **removed**; `fileforge-gui`
  (`fileforge.dispatch:gui_main`) now opens the **This PC window**.
* The 40 classic single-directory commands (`ls`, `find`, `hash`, `cp`, …)
  still work — they are just no longer advertised. `fileforge legacy`
  prints them.

### 2. New module: `src/fileforge/computerkit.py` (21 commands)

| Command | Alias | What it answers |
|---|---|---|
| `computerinfo` | `pcinfo` | Capacity / used / free per volume |
| `computerdrives` | `pcdrives` `drives` | Every mount point with a usage bar |
| `computerscan` | `pcscan` | One full scan: counts, bytes, per-volume table |
| `computertree` | `pctree` | Whole machine as a tree (full filter set) |
| `computerdirs` | `pcdirs` | Biggest directories anywhere |
| `computerlarge` | `pclarge` | Biggest files anywhere |
| `computermap` | `pcmap` | Terminal block map of every volume |
| `computerext` | `pcext` | Size / count grouped by extension |
| `computernew` | `pcnew` | Most recently modified files |
| `computerold` | `pcold` | Least recently modified files |
| `computerempty` | `pcempty` | Empty files and empty directories |
| `computerstats` | `pcstats` | Size buckets, age buckets, top extensions |
| `computerfind` | `pcfind` | Find by name / glob / regex on every drive |
| `computergrep` | `pcgrep` | Search file contents on every drive |
| `computerdupes` | `pcdupes` | Duplicates + reclaimable space |
| `computertemp` | `pctemp` | Temp / cache / junk files |
| `computerexport` | `pcexport` | Export to JSON / CSV / TXT |
| `computersnapshot` | `pcsnapshot` | Save path + size + mtime state |
| `computerdiff` | `pcdiff` | Added / removed / changed between snapshots |
| `computerwatch` | `pcwatch` | Live create / delete / modify feed |
| `computeraudit` | `pcaudit` | World-writable, setuid, setgid audit |

Shared options: `-r/--root DIR` (restrict to one drive — repeatable),
`-L/--max-depth`, `-a/--all`, `--ext`, `--include`, `--exclude`,
`--min-size`, `--max-size`, `--newer`, `--older`, `--max-items` (hard stop),
`--max-children`, `-n/--limit`, `--json`, `--out`, `-q/--quiet`.

Every command reads the disk live: no cache, no index, no daemon.

### 2b. New module `src/fileforge/filekit.py` (12 file commands)

`filemeta` `filepreview` `filehex` `filediff` `filesanitize` `filenorm`
`fileextract` `fileencode` `filedecode` `filetrim` `filesort` `filebackup`
(aliases `fmeta` `fpreview` `fhex` `fdiff` `fsanitize` `fnorm` `fextract`
`fenc` `fdec` `ftrim` `fsort` `fbackup`). Nothing is written unless you pass
`--apply` / `-o` / `--in-place`; `--in-place` keeps a `.bak` copy.

### 2c. New module `src/fileforge/diskkit.py` (14 disk commands)

`diskinfo` `diskpartitions` `diskfs` `diskusage` `diskfree` `disktop`
`diskmounts` `diskhealth` `disktemp` `diskio` `diskbench` `diskserial`
`diskbadfiles` `diskerrors` (aliases `dinfo` `dpart` `dfs` `dusage` `dfree`
`dtop` `dmounts` `dhealth` `dtemp` `dio` `dbench` `dserial` `dbad`
`derrors`).

Platform probes are best-effort and degrade instead of failing:
Windows → PowerShell (`Get-PhysicalDisk`, `Get-Volume`, `Get-CimInstance
Win32_LogicalDisk`, `Get-Counter`, `GetDriveTypeW`); Linux → `lsblk`, `df`,
`/proc/diskstats`, `blkid`, `smartctl`; macOS → `diskutil`, `iostat`,
`smartctl`. On this machine `diskinfo` reports both physical disks
(NVMe SSD + SATA HDD) with model, serial, media, bus, size and health.

### 3. Files touched

| File | Change |
|---|---|
| `src/fileforge/computerkit.py` | **new** — 21 commands + library API |
| `src/fileforge/filekit.py` | **new** — 12 single-file tools |
| `src/fileforge/diskkit.py` | **new** — 14 disk / volume tools |
| `src/fileforge/dispatch.py` | new catalogue, new aliases, `COMPUTERKIT_COMMANDS` / `FILEKIT_COMMANDS` / `DISKKIT_COMMANDS`, `legacy` command, `gui_main` → This PC |
| `fileforge.py` | same registry + forwarding (launcher stays standalone) |
| `publish.py` | requires `computerkit`/`filekit`/`diskkit`, checks 21 modules |
| `computerkit_smoke.py` | **new** — 73 checks against a throw-away tree |
| `filekit_smoke.py` | **new** — 52 checks (incl. base64/hex round-trip) |
| `diskkit_smoke.py` | **new** — 52 checks (incl. a 1 MB benchmark) |
| `dispatch_smoke.py` | assertions updated for the This PC + kit catalogue |
| `README.md` | "This PC" + file tools + disk tools reference + workflows |
| `dist/locals_filesystem-7.0.0-*` | rebuilt wheel (134.0 KB) + sdist (161.8 KB) |

## Verification

| Suite | Result |
|---|---|
| `computerkit_smoke.py` | **73 passed, 0 failed** |
| `filekit_smoke.py` | **52 passed, 0 failed** |
| `diskkit_smoke.py` | **52 passed, 0 failed** |
| `dispatch_smoke.py` | **37 passed, 0 failed** |
| `tree_smoke.py` | **54 passed, 0 failed** |
| `computer_smoke.py` | **33 passed, 0 failed** |
| Wheel inspection | 21 modules, `__version__ = 7.0.0`, entry `fileforge.dispatch:main` → **OK to upload** |
| Wheel unpack + run | `dfree` and `fmeta` run straight from the unpacked wheel |

## Bugs found & fixed during this pass

1. **`files_only` broke directory descent** — `iter_all_files` pushes
   directory nodes to walk them; filtering directories out made `pcempty`
   find nothing. It now filters after the walk.
2. **`--out` / `--min-size` declared twice** — `argparse.ArgumentError` on
   `pcexport`, `pcsnapshot`, `pcdupes`. `_add_common` gained an `out` flag and
   the duplicate finder uses `--min-dup-size`.
3. **Windows permission audit false positives** — every file on NTFS reports
   `0o666`, so all files looked world-writable. Mode-bit checks now run on
   POSIX only.
4. **`filediff` printed the whole file for identical inputs** — `difflib.ndiff`
   echoes every line; the command now short-circuits with "files are
   identical".

## Upload

```bash
python -m twine upload dist/locals_filesystem-7.0.0-py3-none-any.whl \
                      dist/locals_filesystem-7.0.0.tar.gz
pip install --upgrade --no-cache-dir locals-filesystem
fileforge --version      # -> 7.0.0
fileforge help           # -> This PC command list
fileforge computerui     # -> This PC window
```

If `pip` cannot replace `Scripts\fileforge.exe`, run `python make_launchers.py`
or `python install_local.py` instead.
