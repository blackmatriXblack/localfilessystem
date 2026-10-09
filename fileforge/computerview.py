#!/usr/bin/env python3
"""
fileforge.computerview
======================

**"This PC" explorer** - opens straight onto the whole machine so every drive
and every file is visible without picking a folder first.

Two tabs
--------
``This PC``
    A tree whose root is the computer itself. Every volume / mount point is a
    child, and they are expanded automatically on start-up (in a background
    thread) so the machine is already visible when the window appears.

``All Files``
    A flat, streaming table of every file found on every volume. Rows appear
    as the scan progresses; ``Stop`` cancels it at any moment.

Both views read the disk live - no cache, no index, no crawler. Symlinks,
junctions and reparse points are skipped, so an offline network mount can
never freeze the window.

Run it
------
    python fileforge.py computerui
    python fileforge.py computerui -L 3
    python -m fileforge.computerview
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

try:  # package import
    from .computer import (describe_volumes, iter_all_files, list_dir, volumes)
    from .treeview import Node, Options, human_size, human_time
    from .treeui import (EXPAND_ALL_CAP, _sha256_of, kind_of, open_path,
                         reveal_path, terminal_here)
    from .utils import IS_MACOS, IS_WINDOWS
except ImportError:  # pragma: no cover - direct script execution fallback
    from computer import describe_volumes, iter_all_files, list_dir, volumes  # type: ignore
    from treeview import Node, Options, human_size, human_time  # type: ignore
    from treeui import (EXPAND_ALL_CAP, _sha256_of, kind_of, open_path,  # type: ignore
                        reveal_path, terminal_here)
    from utils import IS_MACOS, IS_WINDOWS  # type: ignore

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError as _exc:  # pragma: no cover
    raise SystemExit("computerview requires tkinter (Linux: apt install python3-tk)") from _exc


APP_TITLE = "fileforge - This PC"

LIGHT = {"bg": "#f5f5f5", "fg": "#1b1b1b", "tree": "#ffffff", "sel": "#cce4ff"}
DARK = {"bg": "#1e1e1e", "fg": "#e6e6e6", "tree": "#252526", "sel": "#094771"}

#: Safety caps so a full-machine scan can never exhaust memory or lock the UI.
TREE_NODE_CAP = 60000
FILE_ROW_CAP = 300000
FLUSH_EVERY = 400


class ComputerViewApp:
    """Main window: the whole computer, visible immediately."""

    def __init__(self, master: "tk.Tk", depth: int = 2) -> None:
        self.master = master
        self.depth = depth
        self.theme = LIGHT

        self.show_hidden = tk.BooleanVar(value=False)
        self.dirs_only = tk.BooleanVar(value=False)
        self.depth_var = tk.IntVar(value=depth)
        self.maxc_var = tk.IntVar(value=500)
        self.filter_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Ready")

        self.jobs: "queue.Queue" = queue.Queue()
        self.stop_event = threading.Event()
        self.scanning = False
        self.started = 0.0
        self.tree_nodes = 0
        self.file_rows = 0

        self.iid_by_path: Dict[str, str] = {}
        self.path_by_iid: Dict[str, str] = {}
        self.isdir_by_iid: Dict[str, bool] = {}
        self.loaded_paths: set = set()

        master.title(APP_TITLE)
        master.geometry("1240x780")
        self._style = ttk.Style()
        try:
            self._style.theme_use("clam")
        except tk.TclError:
            pass

        self._build_menu()
        self._build_toolbar()
        self._build_notebook()
        self._build_status()
        self._build_context_menu()
        self._apply_theme()
        self._load_volumes()
        self._auto_expand()

    # -- widgets ----------------------------------------------------------- #

    def _build_menu(self) -> None:
        bar = tk.Menu(self.master)
        self.master.config(menu=bar)

        file_menu = tk.Menu(bar, tearoff=0)
        file_menu.add_command(label="Refresh volumes", command=self.refresh,
                              accelerator="F5")
        file_menu.add_command(label="Expand tree to depth", command=self.expand_tree)
        file_menu.add_command(label="Scan all files", command=self.scan_files)
        file_menu.add_command(label="Stop scan", command=self.stop_scan)
        file_menu.add_separator()
        file_menu.add_command(label="Export tree to text...",
                              command=lambda: self.export("txt"))
        file_menu.add_command(label="Export file list to JSON...",
                              command=lambda: self.export_files("json"))
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.master.destroy,
                              accelerator="Ctrl+Q")
        bar.add_cascade(label="File", menu=file_menu)

        view_menu = tk.Menu(bar, tearoff=0)
        view_menu.add_checkbutton(label="Show hidden entries",
                                  variable=self.show_hidden, command=self.refresh)
        view_menu.add_checkbutton(label="Directories only",
                                  variable=self.dirs_only, command=self.refresh)
        view_menu.add_separator()
        view_menu.add_command(label="Toggle theme", command=self.toggle_theme)
        bar.add_cascade(label="View", menu=view_menu)

        help_menu = tk.Menu(bar, tearoff=0)
        help_menu.add_command(label="Volumes", command=self.show_volumes)
        help_menu.add_command(label="About", command=self.show_about)
        bar.add_cascade(label="Help", menu=help_menu)

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self.master, padding=(8, 6))
        bar.pack(side="top", fill="x")

        ttk.Button(bar, text="This PC", command=self._load_volumes).pack(side="left")
        ttk.Button(bar, text="Refresh", command=self.refresh).pack(side="left", padx=(4, 8))
        ttk.Button(bar, text="Expand tree", command=self.expand_tree).pack(side="left")
        ttk.Button(bar, text="Scan files", command=self.scan_files).pack(side="left", padx=(4, 0))
        ttk.Button(bar, text="Stop", command=self.stop_scan).pack(side="left", padx=(4, 8))

        ttk.Label(bar, text=" Depth:").pack(side="left")
        ttk.Spinbox(bar, from_=1, to=16, width=4,
                    textvariable=self.depth_var).pack(side="left")

        ttk.Label(bar, text=" Max/folder:").pack(side="left", padx=(10, 0))
        ttk.Spinbox(bar, from_=0, to=20000, increment=500, width=7,
                    textvariable=self.maxc_var).pack(side="left")

        ttk.Checkbutton(bar, text="Hidden", variable=self.show_hidden).pack(
            side="left", padx=(10, 0))
        ttk.Checkbutton(bar, text="Dirs only", variable=self.dirs_only).pack(
            side="left", padx=(6, 0))

        ttk.Label(bar, text=" Filter:").pack(side="left", padx=(10, 0))
        entry = ttk.Entry(bar, width=16, textvariable=self.filter_var)
        entry.pack(side="left")
        entry.bind("<Return>", lambda _e: self.refresh())

        ttk.Button(bar, text="Export", command=lambda: self.export("txt")).pack(
            side="right")

    def _build_notebook(self) -> None:
        self.notebook = ttk.Notebook(self.master)
        self.notebook.pack(side="top", fill="both", expand=True, padx=8, pady=(0, 4))

        # --- tab 1: whole-machine tree ---------------------------------- #
        tab_tree = ttk.Frame(self.notebook)
        self.notebook.add(tab_tree, text="  This PC (tree)  ")

        self.tree = ttk.Treeview(tab_tree, columns=("size", "type", "modified"),
                                 show="tree headings", selectmode="extended")
        self.tree.heading("#0", text="Computer / Name")
        self.tree.heading("size", text="Size")
        self.tree.heading("type", text="Type")
        self.tree.heading("modified", text="Modified")
        self.tree.column("#0", width=620, stretch=True)
        self.tree.column("size", width=190, anchor="e", stretch=False)
        self.tree.column("type", width=150, anchor="w", stretch=False)
        self.tree.column("modified", width=160, anchor="w", stretch=False)
        ys = ttk.Scrollbar(tab_tree, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=ys.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        tab_tree.rowconfigure(0, weight=1)
        tab_tree.columnconfigure(0, weight=1)
        self.tree.bind("<<TreeviewOpen>>", self._on_open)
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Button-3>", self._on_right_click)
        if IS_MACOS:
            self.tree.bind("<Button-2>", self._on_right_click)

        # --- tab 2: every file on the machine ---------------------------- #
        tab_files = ttk.Frame(self.notebook)
        self.notebook.add(tab_files, text="  All files  ")

        self.files = ttk.Treeview(tab_files,
                                  columns=("path", "size", "type", "modified"),
                                  show="headings", selectmode="extended")
        self.files.heading("path", text="Full path")
        self.files.heading("size", text="Size")
        self.files.heading("type", text="Type")
        self.files.heading("modified", text="Modified")
        self.files.column("path", width=680, stretch=True)
        self.files.column("size", width=110, anchor="e", stretch=False)
        self.files.column("type", width=130, anchor="w", stretch=False)
        self.files.column("modified", width=160, anchor="w", stretch=False)
        fys = ttk.Scrollbar(tab_files, orient="vertical", command=self.files.yview)
        self.files.configure(yscrollcommand=fys.set)
        self.files.grid(row=0, column=0, sticky="nsew")
        fys.grid(row=0, column=1, sticky="ns")
        tab_files.rowconfigure(0, weight=1)
        tab_files.columnconfigure(0, weight=1)
        self.files.bind("<Double-1>", self._on_file_double_click)
        self.files.bind("<Button-3>", self._on_file_right_click)
        if IS_MACOS:
            self.files.bind("<Button-2>", self._on_file_right_click)

    def _build_status(self) -> None:
        bar = ttk.Frame(self.master, padding=(8, 4))
        bar.pack(side="bottom", fill="x")
        ttk.Label(bar, textvariable=self.status_var, anchor="w").pack(
            side="left", fill="x", expand=True)
        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=160)
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
        self.menu.add_command(label="Expand branch", command=self.ctx_expand_branch)
        self.menu.add_command(label="Refresh", command=self.refresh)
        self.file_menu = tk.Menu(self.master, tearoff=0)
        self.file_menu.add_command(label="Open file", command=self.ctx_open)
        self.file_menu.add_command(label="Reveal in file manager", command=self.ctx_reveal)
        self.file_menu.add_command(label="Open terminal here", command=self.ctx_terminal)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Copy path", command=self.ctx_copy_path)
        self.file_menu.add_command(label="Properties", command=self.ctx_properties)
        self.file_menu.add_command(label="SHA-256", command=self.ctx_hash)

    def _apply_theme(self) -> None:
        t = self.theme
        self.master.configure(background=t["bg"])
        self._style.configure(".", background=t["bg"], foreground=t["fg"])
        self._style.configure("Treeview", background=t["tree"], foreground=t["fg"],
                              fieldbackground=t["tree"])
        self._style.map("Treeview", background=[("selected", t["sel"])],
                        foreground=[("selected", t["fg"])])
        self._style.configure("TFrame", background=t["bg"])
        self._style.configure("TLabel", background=t["bg"], foreground=t["fg"])
        self._style.configure("TCheckbutton", background=t["bg"], foreground=t["fg"])
        self._style.configure("TNotebook", background=t["bg"])

    def toggle_theme(self) -> None:
        self.theme = DARK if self.theme is LIGHT else LIGHT
        self._apply_theme()

    # -- options / helpers ------------------------------------------------- #

    def _opts(self) -> Options:
        try:
            depth = int(self.depth_var.get())
        except (tk.TclError, ValueError):
            depth = self.depth
        try:
            max_children = int(self.maxc_var.get())
        except (tk.TclError, ValueError):
            max_children = 500
        return Options(max_depth=max(1, min(16, depth)),
                       include_hidden=bool(self.show_hidden.get()),
                       dirs_only=bool(self.dirs_only.get()),
                       follow_links=False, sort_by="name",
                       max_children=max_children if max_children > 0 else None)

    def _needle(self) -> str:
        try:
            return self.filter_var.get().strip().lower()
        except tk.TclError:
            return ""

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    # -- tree tab ---------------------------------------------------------- #

    def _load_volumes(self) -> None:
        self.stop_scan()
        self.tree.delete(*self.tree.get_children())
        self.iid_by_path.clear()
        self.path_by_iid.clear()
        self.isdir_by_iid.clear()
        self.loaded_paths.clear()
        self.tree_nodes = 0

        root_iid = self.tree.insert("", "end", text="This PC",
                                    values=("", "Computer", ""), open=True)
        self.iid_by_path["This PC"] = root_iid
        self.path_by_iid[root_iid] = "This PC"
        self.isdir_by_iid[root_iid] = True
        self.pc_iid = root_iid

        for name, total, free in volumes():
            size_text = f"free {human_size(free)} of {human_size(total)}" if total else "unavailable"
            iid = self.tree.insert(root_iid, "end", text=name,
                                   values=(size_text, "Volume", ""), open=False)
            self.iid_by_path[name] = iid
            self.path_by_iid[iid] = name
            self.isdir_by_iid[iid] = True
            self.tree.insert(iid, "end", text="...")
        self._set_status(f"{len(volumes())} volume(s) detected - reading disk...")

    def _on_open(self, _event=None) -> None:
        iid = self.tree.focus()
        if not iid:
            return
        path = self.path_by_iid.get(iid)
        if not path or path == "This PC" or path in self.loaded_paths:
            return
        self._populate(iid, path, lazy=True)

    def _populate(self, iid: str, path: str, lazy: bool = False) -> int:
        """Fill ``iid`` with the children of ``path``. Returns the count."""
        if path in self.loaded_paths:
            return 0
        for child in self.tree.get_children(iid):
            self.tree.delete(child)

        items, err, hidden = list_dir(Path(path), self._opts(), depth=1)
        needle = self._needle()
        if needle:
            items = [n for n in items if needle in n.name.lower()]

        for node in items:
            if self.tree_nodes >= TREE_NODE_CAP:
                break
            label = node.name + (os.sep if node.is_dir else "")
            size = "" if node.is_dir else human_size(node.size)
            cid = self.tree.insert(iid, "end", text=label,
                                   values=(size, kind_of(node),
                                           human_time(node.mtime) if node.mtime else "-"),
                                   open=False)
            key = str(node.path)
            self.iid_by_path[key] = cid
            self.path_by_iid[cid] = key
            self.isdir_by_iid[cid] = node.is_dir
            self.tree_nodes += 1
            if node.is_dir:
                self.tree.insert(cid, "end", text="...")
        self.loaded_paths.add(path)
        if hidden:
            more = self.tree.insert(iid, "end", text=f"+ {hidden} more entries (not listed)",
                                    values=("", "Truncated", ""))
            self.path_by_iid[more] = path
            self.isdir_by_iid[more] = False
        if err:
            err_iid = self.tree.insert(iid, "end", text=f"<{err}>",
                                       values=("", "Error", ""))
            self.path_by_iid[err_iid] = path
            self.isdir_by_iid[err_iid] = False
        if lazy:
            self._set_status(f"{path}  -  {len(items)} entr{'y' if len(items) == 1 else 'ies'}")
        return len(items)

    def _auto_expand(self) -> None:
        """Expand every volume to the configured depth right after start-up."""
        self.expand_tree()

    def expand_tree(self) -> None:
        depth = self._opts().max_depth
        opts = self._opts()
        self.stop_event.clear()
        self.scanning = True
        self.started = time.time()
        self.progress.start(12)
        self._set_status(f"Expanding every volume to depth {depth}...")
        needle = self._needle()

        def worker() -> None:
            try:
                for root, _total, _free in volumes():
                    if self.stop_event.is_set():
                        break
                    self.jobs.put(("expand-root", root, None))
                    self._walk_into(root, Path(root), depth, opts, needle)
            finally:
                self.jobs.put(("done-tree", None, None))

        threading.Thread(target=worker, daemon=True).start()
        self.master.after(60, self._drain)

    def _walk_into(self, root: str, path: Path, depth: int, opts: Options,
                   needle: str) -> None:
        if depth <= 0 or self.stop_event.is_set() or self.tree_nodes >= TREE_NODE_CAP:
            return
        items, _err, hidden = list_dir(path, opts, depth=1)
        if hidden:
            self.jobs.put(("node", str(path), Node(
                path=path, name=f"+ {hidden} more entries (not listed)",
                is_dir=False)))
        for node in items:
            if self.stop_event.is_set() or self.tree_nodes >= TREE_NODE_CAP:
                return
            if needle and needle not in node.name.lower():
                continue
            self.jobs.put(("node", str(path), node))
            if node.is_dir:
                self._walk_into(root, node.path, depth - 1, opts, needle)

    # -- file tab ---------------------------------------------------------- #

    def scan_files(self) -> None:
        self.notebook.select(1)
        self.files.delete(*self.files.get_children())
        self.file_rows = 0
        self.stop_event.clear()
        self.scanning = True
        self.started = time.time()
        self.progress.start(12)
        self._set_status("Scanning every volume for files...")
        opts = self._opts()
        needle = self._needle()

        def worker() -> None:
            try:
                for node in iter_all_files(
                    opts, max_items=FILE_ROW_CAP,
                    max_depth=max(opts.max_depth, 1),
                    should_stop=self.stop_event.is_set,
                ):
                    if needle and needle not in node.name.lower():
                        continue
                    self.jobs.put(("file", None, node))
            finally:
                self.jobs.put(("done-files", None, None))

        threading.Thread(target=worker, daemon=True).start()
        self.master.after(60, self._drain)

    def stop_scan(self) -> None:
        self.stop_event.set()
        if self.scanning:
            self._set_status("Stopping...")

    def _drain(self) -> None:
        """Move queued work onto the UI thread."""
        processed = 0
        try:
            while processed < FLUSH_EVERY:
                kind, parent, payload = self.jobs.get_nowait()
                if kind == "node":
                    self._insert_node(parent, payload)
                elif kind == "file":
                    self._insert_file(payload)
                elif kind == "expand-root":
                    self._populate_root(parent)
                elif kind == "done-tree":
                    self._finish("Tree ready")
                    return
                elif kind == "done-files":
                    self._finish("File scan finished")
                    return
                processed += 1
        except queue.Empty:
            pass
        if self.scanning:
            elapsed = time.time() - self.started
            self._set_status(
                f"Scanning... {self.tree_nodes} folder entries / "
                f"{self.file_rows} files  ({elapsed:.1f}s) - live from disk"
            )
            self.master.after(80, self._drain)

    def _populate_root(self, path: str) -> None:
        iid = self.iid_by_path.get(path)
        if iid:
            self._populate(iid, path)
            self.tree.item(iid, open=True)

    def _insert_node(self, parent_path: str, node: "Node") -> None:
        parent_iid = self.iid_by_path.get(parent_path)
        if parent_iid is None or self.tree_nodes >= TREE_NODE_CAP:
            return
        key = str(node.path)
        if key in self.iid_by_path:
            return
        label = node.name + (os.sep if node.is_dir else "")
        size = "" if node.is_dir else human_size(node.size)
        cid = self.tree.insert(parent_iid, "end", text=label,
                               values=(size, kind_of(node),
                                       human_time(node.mtime) if node.mtime else "-"),
                               open=False)
        self.iid_by_path[key] = cid
        self.path_by_iid[cid] = key
        self.isdir_by_iid[cid] = node.is_dir
        self.tree_nodes += 1

    def _insert_file(self, node: "Node") -> None:
        if self.file_rows >= FILE_ROW_CAP:
            return
        self.files.insert("", "end",
                          values=(str(node.path), human_size(node.size),
                                  kind_of(node),
                                  human_time(node.mtime) if node.mtime else "-"))
        self.file_rows += 1

    def _finish(self, label: str) -> None:
        self.scanning = False
        self.progress.stop()
        elapsed = time.time() - self.started
        self._set_status(
            f"{label}: {self.tree_nodes} folder entries, {self.file_rows} files, "
            f"{elapsed:.1f}s"
            + (" [stopped]" if self.stop_event.is_set() else "")
        )

    # -- interaction ------------------------------------------------------- #

    def refresh(self) -> None:
        self.stop_scan()
        self._load_volumes()
        self.expand_tree()

    def _on_double_click(self, _event=None) -> None:
        iid = self.tree.focus()
        path = self.path_by_iid.get(iid) if iid else None
        if not path or path == "This PC":
            return
        if self.isdir_by_iid.get(iid):
            if path not in self.loaded_paths:
                self._populate(iid, path, lazy=True)
            self.tree.item(iid, open=not self.tree.item(iid, "open"))
        else:
            open_path(path)

    def _on_file_double_click(self, _event=None) -> None:
        sel = self.files.selection()
        if sel:
            open_path(self.files.set(sel[0], "path"))

    def _on_right_click(self, event) -> None:
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.selection_set(iid)
            self.tree.focus(iid)
        self._popup(self.menu, event.x_root, event.y_root)

    def _on_file_right_click(self, event) -> None:
        iid = self.files.identify_row(event.y)
        if iid:
            self.files.selection_set(iid)
        self._popup(self.file_menu, event.x_root, event.y_root)

    def _popup(self, menu: "tk.Menu", x: int, y: int) -> None:
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def selected_path(self) -> Optional[str]:
        if self.notebook.index(self.notebook.select()) == 1:
            sel = self.files.selection()
            return self.files.set(sel[0], "path") if sel else None
        sel = self.tree.selection()
        if not sel:
            return None
        path = self.path_by_iid.get(sel[0])
        return None if path == "This PC" else path

    def ctx_open(self) -> None:
        path = self.selected_path()
        if path:
            open_path(path)

    def ctx_reveal(self) -> None:
        path = self.selected_path()
        if path:
            reveal_path(path)

    def ctx_terminal(self) -> None:
        path = self.selected_path() or "."
        terminal_here(path if os.path.isdir(path) else os.path.dirname(path))

    def ctx_copy_path(self) -> None:
        path = self.selected_path()
        if path:
            self.master.clipboard_clear()
            self.master.clipboard_append(path)

    def ctx_copy_name(self) -> None:
        sel = self.tree.selection()
        if sel:
            self.master.clipboard_clear()
            self.master.clipboard_append(self.tree.item(sel[0], "text"))

    def ctx_properties(self) -> None:
        path = self.selected_path()
        if not path:
            return
        try:
            st = os.stat(path)
        except OSError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        messagebox.showinfo("Properties", "\n".join([
            f"Path : {path}",
            f"Kind : {'Directory' if os.path.isdir(path) else 'File'}",
            f"Size : {human_size(st.st_size)}",
            f"Mod. : {human_time(st.st_mtime)}",
            f"Mode : {oct(st.st_mode & 0o7777)}",
        ]))

    def ctx_hash(self) -> None:
        path = self.selected_path()
        if not path or not os.path.isfile(path):
            messagebox.showinfo(APP_TITLE, "Select a file first.")
            return
        self._set_status("Hashing...")
        threading.Thread(
            target=lambda: self.jobs.put(("hash", None, (path, _sha256_of(path)))),
            daemon=True).start()
        self.master.after(60, self._drain_hash)

    def _drain_hash(self) -> None:
        try:
            while True:
                kind, _p, payload = self.jobs.get_nowait()
                if kind == "hash":
                    path, digest = payload
                    messagebox.showinfo("SHA-256", f"{path}\n\n{digest}")
                    self._set_status("Ready")
                    return
        except queue.Empty:
            pass
        self.master.after(120, self._drain_hash)

    def ctx_expand_branch(self) -> None:
        iid = self.tree.focus()
        path = self.path_by_iid.get(iid) if iid else None
        if not path or path == "This PC":
            return
        opts = self._opts()
        self._walk_into(path, Path(path), opts.max_depth, opts, self._needle())
        self.tree.item(iid, open=True)
        self.master.after(80, self._drain_branch)

    def _drain_branch(self) -> None:
        processed = 0
        try:
            while processed < FLUSH_EVERY:
                kind, parent, payload = self.jobs.get_nowait()
                if kind == "node":
                    self._insert_node(parent, payload)
                processed += 1
        except queue.Empty:
            pass
        if not self.jobs.empty():
            self.master.after(80, self._drain_branch)
        else:
            self._set_status(f"{self.tree_nodes} folder entries loaded")

    # -- export ------------------------------------------------------------ #

    def export(self, kind: str) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=f".{kind}",
            filetypes=[(f"{kind.upper()} file", f"*.{kind}"), ("All files", "*.*")],
            initialfile=f"this-pc.{kind}")
        if not path:
            return
        lines = self._tree_text_lines()
        Path(path).write_text("\n".join(lines), encoding="utf-8")
        self._set_status(f"Exported {len(lines)} lines to {path}")

    def _tree_text_lines(self) -> List[str]:
        out: List[str] = []
        stack: List[Tuple[str, str]] = [(self.pc_iid, "")]
        while stack:
            iid, prefix = stack.pop()
            if iid is None:
                continue
            out.append(prefix + self.tree.item(iid, "text"))
            children = list(self.tree.get_children(iid))
            for index in range(len(children) - 1, -1, -1):
                child = children[index]
                last = index == len(children) - 1
                branch = "└── " if last else "├── "
                child_prefix = prefix.replace("├── ", "│   ").replace("└── ", "    ")
                stack.append((child, child_prefix + branch))
        return out

    def export_files(self, kind: str) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=f".{kind}",
            filetypes=[(f"{kind.upper()} file", f"*.{kind}")],
            initialfile=f"all-files.{kind}")
        if not path:
            return
        rows = [{"path": self.files.set(i, "path"),
                 "size": self.files.set(i, "size"),
                 "type": self.files.set(i, "type"),
                 "modified": self.files.set(i, "modified")}
                for i in self.files.get_children("")]
        Path(path).write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        self._set_status(f"Exported {len(rows)} files to {path}")

    # -- info -------------------------------------------------------------- #

    def show_volumes(self) -> None:
        messagebox.showinfo("Volumes", "\n".join(describe_volumes()) or "None")

    def show_about(self) -> None:
        messagebox.showinfo(
            APP_TITLE,
            "fileforge This PC explorer\n\n"
            "Opens straight onto every drive of the machine.\n"
            "Everything is read live from disk - no cache, no index.\n"
            "Symlinks / junctions are skipped so offline mounts never freeze it.\n"
            "Runs on Linux, Windows and macOS.",
        )


def run(depth: int = 2) -> int:
    """Open the This PC window (blocks until closed)."""
    master = tk.Tk()
    app = ComputerViewApp(master, depth=depth)
    master.bind_all("<F5>", lambda _e: app.refresh())
    master.bind_all("<Control-q>", lambda _e: master.destroy())
    master.mainloop()
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fileforge computerui",
        description="Open the whole-computer (This PC) explorer window.")
    parser.add_argument("-L", "--max-depth", type=int, default=2,
                        help="auto-expand depth for each volume (1-16)")
    args = parser.parse_args(argv)
    return run(max(1, min(16, args.max_depth)))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
