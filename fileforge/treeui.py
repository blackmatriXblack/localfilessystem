#!/usr/bin/env python3
"""
fileforge.treeui
================

A **live** Tkinter file-system tree explorer.

Philosophy
----------
Every node is read from disk the moment it is expanded - there is no cache,
no index file and no background crawler. What you see is the volume as it
is right now. Reparse points / junctions / symlinks are skipped so a broken
network mount can never freeze the window.

Features
--------
* Lazy expansion - only the opened branch is ever scanned
* Columns: Name / Size / Type / Modified, sortable
* Live name filter (substring, case-insensitive)
* Depth limit, hidden entries, directories-only toggles
* Right-click menu: open, reveal in file manager, terminal here, copy path,
  copy name, properties, hash, expand branch, collapse all
* Export the current tree to ``.txt`` or ``.json`` (background thread)
* Light / dark theme
* Cross platform: Linux, Windows and macOS (requires ``tkinter``)

Run it
------
    python fileforge.py treeui
    python fileforge.py treeui D:\\ -L 2
    python -m fileforge.treeui
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

try:  # package import
    from .treeview import Node, Options, build_tree, to_dict, _list_dir
    from .utils import human_size, human_time
except ImportError:  # pragma: no cover - direct script execution fallback
    from treeview import Node, Options, build_tree, to_dict, _list_dir  # type: ignore
    from utils import human_size, human_time  # type: ignore

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError as _exc:  # pragma: no cover
    raise SystemExit(
        "treeui requires tkinter. On Linux install it with: "
        "sudo apt install python3-tk   (or the equivalent for your distro)"
    ) from _exc


APP_TITLE = "fileforge - Live File Tree"
IS_WINDOWS = os.name == "nt"
IS_MACOS = platform.system() == "Darwin"

LIGHT = {
    "bg": "#f5f5f5", "fg": "#1b1b1b", "tree_bg": "#ffffff", "tree_fg": "#1b1b1b",
    "sel": "#cce4ff", "accent": "#0b5cad",
}
DARK = {
    "bg": "#1e1e1e", "fg": "#e6e6e6", "tree_bg": "#252526", "tree_fg": "#e6e6e6",
    "sel": "#094771", "accent": "#4daafc",
}

#: Safety cap for "expand all" so a huge volume cannot lock the UI.
EXPAND_ALL_CAP = 20000


# --------------------------------------------------------------------------- #
# Platform actions
# --------------------------------------------------------------------------- #


def open_path(path: str) -> None:
    """Open a file or folder with the operating system's default handler."""
    try:
        if IS_WINDOWS:
            os.startfile(path)  # type: ignore[attr-defined]
        elif IS_MACOS:
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except OSError as exc:
        messagebox.showerror(APP_TITLE, f"Cannot open {path}:\n{exc}")


def reveal_path(path: str) -> None:
    """Select/reveal the entry in the native file manager."""
    try:
        if IS_WINDOWS:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        elif IS_MACOS:
            subprocess.Popen(["open", "-R", path])
        else:
            target = path if os.path.isdir(path) else os.path.dirname(path)
            subprocess.Popen(["xdg-open", target])
    except OSError as exc:
        messagebox.showerror(APP_TITLE, str(exc))


def terminal_here(path: str) -> None:
    """Open a terminal/shell in the given directory."""
    directory = path if os.path.isdir(path) else os.path.dirname(path)
    try:
        if IS_WINDOWS:
            subprocess.Popen(["cmd", "/k", "cd", "/d", directory],
                             creationflags=subprocess.CREATE_NEW_CONSOLE)  # type: ignore[attr-defined]
        elif IS_MACOS:
            subprocess.Popen(["open", "-a", "Terminal", directory])
        else:
            for term in ("x-terminal-emulator", "gnome-terminal", "konsole",
                         "xfce4-terminal", "xterm"):
                try:
                    subprocess.Popen([term, "--working-directory", directory])
                    return
                except OSError:
                    continue
            messagebox.showinfo(APP_TITLE, "No supported terminal emulator found.")
    except OSError as exc:
        messagebox.showerror(APP_TITLE, str(exc))


def kind_of(node: Node) -> str:
    if node.is_dir:
        return "Directory"
    ext = os.path.splitext(node.name)[1].lower()
    return (ext.lstrip(".").upper() + " file") if ext else "File"


# --------------------------------------------------------------------------- #
# Application
# --------------------------------------------------------------------------- #


class LiveTreeApp:
    """Main window of the live tree explorer."""

    def __init__(self, master: "tk.Tk", root: str = ".", max_depth: int = 3) -> None:
        self.master = master
        self.root_path = str(Path(root).expanduser().resolve())
        self.max_depth = max_depth
        self.theme = LIGHT
        self.jobs: "queue.Queue" = queue.Queue()
        self.busy = False

        self.show_hidden = tk.BooleanVar(value=False)
        self.dirs_only = tk.BooleanVar(value=False)
        self.depth_var = tk.IntVar(value=max_depth)
        self.filter_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Ready")

        self.node_paths: Dict[str, str] = {}
        self.node_isdir: Dict[str, bool] = {}

        master.title(APP_TITLE)
        master.geometry("1100x700")
        self._build_style()
        self._build_menu()
        self._build_toolbar(master)
        self._build_tree(master)
        self._build_status(master)
        self._build_context_menu()
        self._bind_keys()
        self._apply_theme()
        self.load_root(self.root_path)

    # -- construction ------------------------------------------------------ #

    def _build_style(self) -> None:
        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.master)
        self.master.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open root...", command=self.browse_root,
                              accelerator="Ctrl+O")
        file_menu.add_command(label="Refresh", command=self.refresh,
                              accelerator="F5")
        file_menu.add_separator()
        file_menu.add_command(label="Export tree to text...",
                              command=lambda: self.export("txt"))
        file_menu.add_command(label="Export tree to JSON...",
                              command=lambda: self.export("json"))
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.master.destroy,
                              accelerator="Ctrl+Q")
        menubar.add_cascade(label="File", menu=file_menu)

        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_checkbutton(label="Show hidden entries",
                                  variable=self.show_hidden, command=self.refresh)
        view_menu.add_checkbutton(label="Directories only",
                                  variable=self.dirs_only, command=self.refresh)
        view_menu.add_separator()
        view_menu.add_command(label="Expand all (depth limit)",
                              command=self.expand_all)
        view_menu.add_command(label="Collapse all", command=self.collapse_all)
        view_menu.add_separator()
        view_menu.add_command(label="Toggle theme", command=self.toggle_theme)
        menubar.add_cascade(label="View", menu=view_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

    def _build_toolbar(self, master: "tk.Tk") -> None:
        bar = ttk.Frame(master, padding=(8, 6))
        bar.pack(side="top", fill="x")

        ttk.Label(bar, text="Root:").pack(side="left")
        self.path_entry = ttk.Entry(bar)
        self.path_entry.insert(0, self.root_path)
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(4, 6))
        self.path_entry.bind("<Return>", lambda _e: self.apply_path())

        ttk.Button(bar, text="Browse", command=self.browse_root).pack(side="left")
        ttk.Button(bar, text="Go", command=self.apply_path).pack(side="left", padx=(4, 8))
        ttk.Button(bar, text="Refresh", command=self.refresh).pack(side="left")

        ttk.Label(bar, text=" Depth:").pack(side="left")
        ttk.Spinbox(bar, from_=1, to=32, width=4, textvariable=self.depth_var,
                    command=self.refresh).pack(side="left")

        ttk.Checkbutton(bar, text="Hidden", variable=self.show_hidden,
                        command=self.refresh).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(bar, text="Dirs only", variable=self.dirs_only,
                        command=self.refresh).pack(side="left", padx=(6, 0))

        ttk.Label(bar, text=" Filter:").pack(side="left", padx=(8, 0))
        filt = ttk.Entry(bar, width=14, textvariable=self.filter_var)
        filt.pack(side="left")
        filt.bind("<Return>", lambda _e: self.refresh())

    def _build_tree(self, master: "tk.Tk") -> None:
        frame = ttk.Frame(master)
        frame.pack(side="top", fill="both", expand=True, padx=8, pady=(0, 4))

        columns = ("size", "type", "modified")
        self.tree = ttk.Treeview(frame, columns=columns, show="tree headings",
                                 selectmode="extended")
        self.tree.heading("#0", text="Name",
                          command=lambda: self._sort_by("#0", False))
        self.tree.heading("size", text="Size",
                          command=lambda: self._sort_by("size", True))
        self.tree.heading("type", text="Type",
                          command=lambda: self._sort_by("type", False))
        self.tree.heading("modified", text="Modified",
                          command=lambda: self._sort_by("modified", False))
        self.tree.column("#0", width=520, stretch=True)
        self.tree.column("size", width=110, anchor="e", stretch=False)
        self.tree.column("type", width=140, anchor="w", stretch=False)
        self.tree.column("modified", width=160, anchor="w", stretch=False)

        yscroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        self.tree.bind("<<TreeviewOpen>>", self._on_open)
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Button-3>", self._on_right_click)
        if IS_MACOS:
            self.tree.bind("<Button-2>", self._on_right_click)

    def _build_status(self, master: "tk.Tk") -> None:
        bar = ttk.Frame(master, padding=(8, 4))
        bar.pack(side="bottom", fill="x")
        ttk.Label(bar, textvariable=self.status_var, anchor="w").pack(
            side="left", fill="x", expand=True)
        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=140)
        self.progress.pack(side="right")

    def _build_context_menu(self) -> None:
        self.menu = tk.Menu(self.master, tearoff=0)
        self.menu.add_command(label="Open", command=self.ctx_open)
        self.menu.add_command(label="Reveal in file manager", command=self.ctx_reveal)
        self.menu.add_command(label="Open terminal here", command=self.ctx_terminal)
        self.menu.add_separator()
        self.menu.add_command(label="Copy path", command=self.ctx_copy_path)
        self.menu.add_command(label="Copy name", command=self.ctx_copy_name)
        self.menu.add_command(label="Properties", command=self.ctx_properties)
        self.menu.add_command(label="SHA-256", command=self.ctx_hash)
        self.menu.add_separator()
        self.menu.add_command(label="Set as root", command=self.ctx_set_root)
        self.menu.add_command(label="Expand branch", command=self.ctx_expand_branch)
        self.menu.add_separator()
        self.menu.add_command(label="Refresh", command=self.refresh)

    def _bind_keys(self) -> None:
        self.master.bind_all("<F5>", lambda _e: self.refresh())
        self.master.bind_all("<Control-o>", lambda _e: self.browse_root())
        self.master.bind_all("<Control-q>", lambda _e: self.master.destroy())
        self.master.bind_all("<Control-f>", lambda _e: self.master.focus_get())

    # -- theming ----------------------------------------------------------- #

    def _apply_theme(self) -> None:
        t = self.theme
        self.master.configure(background=t["bg"])
        self.style.configure(".", background=t["bg"], foreground=t["fg"])
        self.style.configure("Treeview", background=t["tree_bg"],
                             foreground=t["tree_fg"], fieldbackground=t["tree_bg"])
        self.style.map("Treeview",
                       background=[("selected", t["sel"])],
                       foreground=[("selected", t["fg"])])
        self.style.configure("TFrame", background=t["bg"])
        self.style.configure("TLabel", background=t["bg"], foreground=t["fg"])
        self.style.configure("TCheckbutton", background=t["bg"], foreground=t["fg"])

    def toggle_theme(self) -> None:
        self.theme = DARK if self.theme is LIGHT else LIGHT
        self._apply_theme()

    # -- data -------------------------------------------------------------- #

    def _opts(self) -> Options:
        try:
            depth = int(self.depth_var.get())
        except (tk.TclError, ValueError):
            depth = self.max_depth
        return Options(
            max_depth=depth,
            include_hidden=bool(self.show_hidden.get()),
            dirs_only=bool(self.dirs_only.get()),
            follow_links=False,
            sort_by="name",
        )

    def _filter_text(self) -> str:
        try:
            return self.filter_var.get().strip().lower()
        except tk.TclError:
            return ""

    def load_root(self, path: str) -> None:
        self.root_path = str(Path(path).expanduser())
        try:
            self.root_path = str(Path(self.root_path).resolve())
        except OSError:
            pass
        self.path_entry.delete(0, "end")
        self.path_entry.insert(0, self.root_path)
        self.tree.delete(*self.tree.get_children())
        self.node_paths.clear()
        self.node_isdir.clear()

        if not os.path.exists(self.root_path):
            self.status_var.set(f"Path does not exist: {self.root_path}")
            return

        base = Path(self.root_path)
        name = base.name or self.root_path
        iid = self.tree.insert("", "end", text=name,
                               values=("", "Directory", self._mtime_of(base)),
                               open=False)
        self.node_paths[iid] = str(base)
        self.node_isdir[iid] = True
        self._ensure_children(iid)
        self.tree.item(iid, open=True)
        self.status_var.set(f"Root: {self.root_path}")

    def _mtime_of(self, path: Path) -> str:
        try:
            return human_time(os.stat(str(path)).st_mtime)
        except OSError:
            return "-"

    def _ensure_children(self, iid: str) -> None:
        """Populate ``iid`` once - called lazily on expand."""
        if self.tree.get_children(iid) and self.tree.tag_has("loaded", iid):
            return
        for child in self.tree.get_children(iid):
            self.tree.delete(child)

        path = self.node_paths.get(iid)
        if not path or not self.node_isdir.get(iid):
            return

        opts = self._opts()
        items, err, _hidden = _list_dir(Path(path), opts, depth=1)
        needle = self._filter_text()
        if needle:
            items = [n for n in items if needle in n.name.lower()]

        for node in items:
            label = node.name + (os.sep if node.is_dir else "")
            size = "" if node.is_dir else human_size(node.size)
            cid = self.tree.insert(
                iid, "end", text=label,
                values=(size, kind_of(node),
                        human_time(node.mtime) if node.mtime else "-"),
                open=False,
            )
            self.node_paths[cid] = str(node.path)
            self.node_isdir[cid] = node.is_dir
            if node.is_dir:
                self.tree.insert(cid, "end", text="...")
        self.tree.item(iid, tags=("loaded",))
        if err:
            self.status_var.set(f"{path}: {err}")
        else:
            self.status_var.set(f"{path}  -  {len(items)} entr{'y' if len(items) == 1 else 'ies'}")

    def _on_open(self, _event=None) -> None:
        iid = self.tree.focus()
        if not iid:
            return
        if self.tree.tag_has("loaded", iid):
            return
        self._ensure_children(iid)

    # -- interaction ------------------------------------------------------- #

    def refresh(self) -> None:
        self.load_root(self.path_entry.get().strip() or self.root_path)

    def apply_path(self) -> None:
        value = self.path_entry.get().strip()
        if value:
            self.load_root(value)

    def browse_root(self) -> None:
        picked = filedialog.askdirectory(initialdir=self.root_path)
        if picked:
            self.load_root(picked)

    def _on_double_click(self, _event=None) -> None:
        iid = self.tree.focus()
        if not iid:
            return
        path = self.node_paths.get(iid)
        if not path:
            return
        if self.node_isdir.get(iid):
            self.tree.item(iid, open=not self.tree.item(iid, "open"))
            if not self.tree.tag_has("loaded", iid):
                self._ensure_children(iid)
        else:
            open_path(path)

    def _on_right_click(self, event) -> None:
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.selection_set(iid)
            self.tree.focus(iid)
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def selected_path(self) -> Optional[str]:
        sel = self.tree.selection()
        if not sel:
            return None
        return self.node_paths.get(sel[0])

    def ctx_open(self) -> None:
        path = self.selected_path()
        if path:
            open_path(path)

    def ctx_reveal(self) -> None:
        path = self.selected_path()
        if path:
            reveal_path(path)

    def ctx_terminal(self) -> None:
        path = self.selected_path() or self.root_path
        terminal_here(path)

    def ctx_copy_path(self) -> None:
        path = self.selected_path()
        if not path:
            return
        self.master.clipboard_clear()
        self.master.clipboard_append(path)

    def ctx_copy_name(self) -> None:
        iid = self.tree.focus()
        if iid:
            self.master.clipboard_clear()
            self.master.clipboard_append(self.tree.item(iid, "text"))

    def ctx_properties(self) -> None:
        path = self.selected_path()
        if not path:
            return
        try:
            st = os.stat(path)
        except OSError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        kind = "Directory" if os.path.isdir(path) else "File"
        lines = [
            f"Path : {path}",
            f"Kind : {kind}",
            f"Size : {human_size(st.st_size)}",
            f"Mod. : {human_time(st.st_mtime)}",
            f"Acc. : {human_time(st.st_atime)}",
            f"Mode : {oct(st.st_mode & 0o7777)}",
            f"Inode: {getattr(st, 'st_ino', '-')}",
        ]
        messagebox.showinfo("Properties", "\n".join(lines))

    def ctx_hash(self) -> None:
        path = self.selected_path()
        if not path or not os.path.isfile(path):
            messagebox.showinfo(APP_TITLE, "Select a file first.")
            return
        self._run_background(
            lambda: _sha256_of(path),
            lambda digest: messagebox.showinfo("SHA-256", f"{path}\n\n{digest}"),
            "Hashing",
        )

    def ctx_set_root(self) -> None:
        path = self.selected_path()
        if path:
            self.load_root(path)

    def ctx_expand_branch(self) -> None:
        iid = self.tree.focus()
        if iid:
            self._expand_branch(iid, self._opts().max_depth)

    def _expand_branch(self, iid: str, depth: int) -> None:
        if depth <= 0:
            return
        if not self.tree.tag_has("loaded", iid):
            self._ensure_children(iid)
        for child in self.tree.get_children(iid):
            if self.node_isdir.get(child):
                self._expand_branch(child, depth - 1)
                self.tree.item(child, open=True)

    def collapse_all(self) -> None:
        for iid in self.tree.get_children(""):
            self._collapse(iid)

    def _collapse(self, iid: str) -> None:
        self.tree.item(iid, open=False)
        for child in self.tree.get_children(iid):
            self._collapse(child)

    def expand_all(self) -> None:
        depth = self._opts().max_depth
        self._run_background(
            lambda: _count_plan(self.root_path, self._opts(), depth),
            lambda _n: self._do_expand_all(depth),
            "Scanning",
        )

    def _do_expand_all(self, depth: int) -> None:
        count = 0
        for iid in self.tree.get_children(""):
            count = self._expand_all_node(iid, depth, count)
        self.status_var.set(f"Expanded {count} nodes (cap {EXPAND_ALL_CAP})")

    def _expand_all_node(self, iid: str, depth: int, count: int) -> int:
        if depth <= 0 or count >= EXPAND_ALL_CAP:
            return count
        if not self.tree.tag_has("loaded", iid):
            self._ensure_children(iid)
        count += 1
        for child in self.tree.get_children(iid):
            if self.node_isdir.get(child):
                count = self._expand_all_node(child, depth - 1, count)
                self.tree.item(child, open=True)
        return count

    def _sort_by(self, column: str, numeric: bool) -> None:
        rows = [(self.tree.set(k, column) if column != "#0" else self.tree.item(k, "text"), k)
                for k in self.tree.get_children("")]

        def key(item):
            value = item[0]
            if numeric:
                return _size_to_bytes(value)
            return value.lower()

        rows.sort(key=key)
        for index, (_value, iid) in enumerate(rows):
            self.tree.move(iid, "", index)

    # -- background jobs --------------------------------------------------- #

    def _run_background(self, job, done, label: str) -> None:
        if self.busy:
            return
        self.busy = True
        self.status_var.set(f"{label}...")
        self.progress.start(12)

        def worker() -> None:
            try:
                result = job()
                error: Optional[BaseException] = None
            except BaseException as exc:  # noqa: BLE001 - reported to the user
                result, error = None, exc
            self.master.after(0, lambda: self._job_done(done, result, error))

        threading.Thread(target=worker, daemon=True).start()

    def _job_done(self, done, result, error) -> None:
        self.busy = False
        self.progress.stop()
        if error is not None:
            self.status_var.set("Error")
            messagebox.showerror(APP_TITLE, str(error))
            return
        self.status_var.set("Ready")
        done(result)

    def export(self, kind: str) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=f".{kind}",
            filetypes=[(f"{kind.upper()} file", f"*.{kind}"), ("All files", "*.*")],
            initialfile=f"tree.{kind}",
        )
        if not path:
            return
        opts = self._opts()
        root = self.root_path

        def job() -> str:
            if kind == "json":
                from .treeview import to_json
            else:
                from .treeview import to_text
            text = (to_json(root, opts) if kind == "json"
                    else to_text(root, opts, show_size=True))
            Path(path).write_text(text, encoding="utf-8")
            return path

        self._run_background(job, lambda p: self.status_var.set(f"Exported {p}"),
                             "Exporting")

    def show_about(self) -> None:
        messagebox.showinfo(
            APP_TITLE,
            "fileforge live tree explorer\n\n"
            "Reads directly from disk on every expansion - no cache, no index.\n"
            "Skips symlinks / junctions so unreachable mounts never freeze it.\n"
            "Runs on Linux, Windows and macOS.",
        )


# --------------------------------------------------------------------------- #
# Module level helpers
# --------------------------------------------------------------------------- #


def _sha256_of(path: str) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _size_to_bytes(text: str) -> int:
    text = (text or "").strip()
    if not text:
        return -1
    units = {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3, "TB": 1024 ** 4}
    try:
        num, unit = text.rsplit(" ", 1)
        return int(float(num) * units.get(unit.upper(), 1))
    except ValueError:
        return -1


def _count_plan(root: str, opts: Options, depth: int) -> int:
    """Dry-run used by ``expand all`` to give the UI a warm-up pass."""
    total = 0
    for _ in _walk_paths(Path(root), opts, depth):
        total += 1
        if total > EXPAND_ALL_CAP:
            break
    return total


def _walk_paths(path: Path, opts: Options, depth: int):
    if depth <= 0:
        return
    items, _err, _hidden = _list_dir(path, opts, depth=1)
    for node in items:
        yield node.path
        if node.is_dir:
            yield from _walk_paths(node.path, opts, depth - 1)


def run(root: str = ".", max_depth: int = 3) -> int:
    """Open the explorer window (blocks until it is closed)."""
    master = tk.Tk()
    LiveTreeApp(master, root=root, max_depth=max_depth)
    master.mainloop()
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fileforge treeui",
        description="Open the live Tkinter file-system tree explorer.",
    )
    parser.add_argument("path", nargs="?", default=".", help="root directory")
    parser.add_argument("-L", "--max-depth", type=int, default=3,
                        help="default expansion depth (1-32)")
    args = parser.parse_args(argv)
    return run(args.path, max(1, min(32, args.max_depth)))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
