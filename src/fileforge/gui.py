"""
fileforge.gui
=============

A cross-platform Tkinter front-end for the fileforge toolkit.

Features
--------
* Dual-panel browser : directory tree (left) + rich file table (right)
* 8 tool tabs        : Browser, Search, Grep, Integrity, Archive,
                       Analytics, Security, Text Tools
* Context menus, property dialogs, editable file viewer
* Background threads for long jobs (UI never freezes)
* Light / dark minimal theme, status bar with live free space

Launch with::

    python fileforge.py gui          # from the repo
    fileforge-gui                    # after pip install
"""

from __future__ import annotations

import os
import platform
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable, List, Optional, Sequence

from . import analytics, archive, core, hashutil, search, security, utils
from .utils import FileForgeError, human_size, human_time, resolve

APP_TITLE = "fileforge"
APP_VERSION = "1.0.0"

# --------------------------------------------------------------------------- #
# Theme (minimal black & white)
# --------------------------------------------------------------------------- #

LIGHT = {
    "bg": "#ffffff",
    "fg": "#111111",
    "panel": "#f4f4f4",
    "accent": "#111111",
    "select": "#dcdcdc",
    "border": "#cccccc",
    "muted": "#777777",
    "ok": "#0a7d32",
    "warn": "#b58900",
    "err": "#c0392b",
    "tree_field": "#ffffff",
    "tree_head": "#eaeaea",
}

DARK = {
    "bg": "#141414",
    "fg": "#e6e6e6",
    "panel": "#1f1f1f",
    "accent": "#ffffff",
    "select": "#3a3a3a",
    "border": "#3c3c3c",
    "muted": "#999999",
    "ok": "#7bd88f",
    "warn": "#e6c07b",
    "err": "#e06c75",
    "tree_field": "#191919",
    "tree_head": "#262626",
}


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #

def _sort_children(tree: ttk.Treeview, parent: str) -> None:
    children = tree.get_children(parent)
    if not children:
        return
    ordered = sorted(
        children,
        key=lambda iid: (
            not str(tree.set(iid, "type")).lower().startswith("dir"),
            str(tree.set(iid, "name")).lower(),
        ),
    )
    for iid in ordered:
        tree.move(iid, parent, "end")


class BackgroundRunner:
    """Runs callables on worker threads and marshals results to the UI thread."""

    def __init__(self, widget: tk.Misc) -> None:
        self.widget = widget
        self._queue: "queue.Queue[tuple]" = queue.Queue()
        self._tasks = 0
        widget.after(80, self._poll)

    def run(self, fn: Callable, on_done: Optional[Callable] = None,
            label: str = "Working...") -> None:
        self._tasks += 1
        app = self.widget  # type: ignore[attr-defined]
        if hasattr(app, "set_busy"):
            app.set_busy(f"{label} ({self._tasks} running)")

        def worker() -> None:
            try:
                result = fn()
                self._queue.put(("ok", result, on_done))
            except Exception as exc:  # noqa: BLE001
                self._queue.put(("err", exc, None))

        threading.Thread(target=worker, daemon=True).start()

    def _poll(self) -> None:
        try:
            while True:
                kind, payload, on_done = self._queue.get_nowait()
                self._tasks = max(0, self._tasks - 1)
                if kind == "ok":
                    if on_done:
                        try:
                            on_done(payload)
                        except Exception as exc:  # noqa: BLE001
                            messagebox.showerror(APP_TITLE, str(exc))
                else:
                    messagebox.showerror(APP_TITLE, f"{type(payload).__name__}: {payload}")
                app = self.widget  # type: ignore[attr-defined]
                if hasattr(app, "set_busy"):
                    app.set_busy(None if self._tasks == 0 else f"{self._tasks} running")
        except queue.Empty:
            pass
        self.widget.after(80, self._poll)


# --------------------------------------------------------------------------- #
# Main application
# --------------------------------------------------------------------------- #

class FileForgeApp(ttk.Frame):

    def __init__(self, master: tk.Tk) -> None:
        super().__init__(master)
        self.master = master
        self.theme: dict = LIGHT
        self.show_hidden = tk.BooleanVar(value=False)
        self.current_dir = resolve(os.getcwd())

        master.title(f"{APP_TITLE} {APP_VERSION}")
        w, h = 1280, 800
        master.geometry(f"{w}x{h}")
        master.minsize(960, 600)

        self.runner = BackgroundRunner(master)
        master.set_busy = self.set_busy  # type: ignore[attr-defined]

        self._build_menu()
        self._build_layout()
        self.apply_theme()
        self.refresh_all()

    # ------------------------------------------------------------------ #
    # Theme
    # ------------------------------------------------------------------ #

    def apply_theme(self) -> None:
        t = self.theme
        style = ttk.Style(self.master)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", background=t["panel"], foreground=t["fg"],
                        fieldbackground=t["bg"], bordercolor=t["border"],
                        lightcolor=t["panel"], darkcolor=t["panel"])
        style.configure("TFrame", background=t["panel"])
        style.configure("TLabel", background=t["panel"], foreground=t["fg"])
        style.configure("TButton", background=t["panel"], foreground=t["fg"],
                        padding=(10, 4))
        style.map("TButton",
                  background=[("active", t["select"])],
                  foreground=[("active", t["fg"])])
        style.configure("Accent.TButton", background=t["accent"],
                        foreground=t["bg"])
        style.configure("TEntry", fieldbackground=t["bg"], foreground=t["fg"],
                        insertcolor=t["fg"])
        style.configure("TCombobox", fieldbackground=t["bg"], foreground=t["fg"])
        style.configure("TNotebook", background=t["panel"],
                        bordercolor=t["border"])
        style.configure("TNotebook.Tab", background=t["panel"],
                        foreground=t["fg"], padding=(14, 6))
        style.map("TNotebook.Tab",
                  background=[("selected", t["bg"])],
                  foreground=[("selected", t["fg"])])
        style.configure("Treeview", background=t["tree_field"],
                        foreground=t["fg"], fieldbackground=t["tree_field"],
                        bordercolor=t["border"])
        style.configure("Treeview.Heading", background=t["tree_head"],
                        foreground=t["fg"])
        style.map("Treeview", background=[("selected", t["select"])])
        style.configure("Status.TLabel", background=t["panel"],
                        foreground=t["muted"])

        self.master.configure(bg=t["panel"])
        for widget in self.master.winfo_children():
            try:
                widget.configure(bg=t["panel"])
            except tk.TclError:
                pass

    def toggle_theme(self) -> None:
        self.theme = DARK if self.theme is LIGHT else LIGHT
        self.apply_theme()
        self.refresh_all()

    # ------------------------------------------------------------------ #
    # Layout
    # ------------------------------------------------------------------ #

    def _build_menu(self) -> None:
        m = tk.Menu(self.master)
        self.master.config(menu=m)

        file_menu = tk.Menu(m, tearoff=0)
        file_menu.add_command(label="New File...", command=self.act_new_file)
        file_menu.add_command(label="New Folder...", command=self.act_new_folder)
        file_menu.add_separator()
        file_menu.add_command(label="Open in System File Manager", command=self.act_open_fm)
        file_menu.add_command(label="Open Terminal Here", command=self.act_open_term)
        file_menu.add_command(label="Launch CLI Shell", command=self.act_launch_shell)
        file_menu.add_separator()
        file_menu.add_command(label="Refresh  (F5)", command=self.refresh_all)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.master.destroy)
        m.add_cascade(label="File", menu=file_menu)

        edit_menu = tk.Menu(m, tearoff=0)
        edit_menu.add_command(label="Copy...", command=self.act_copy)
        edit_menu.add_command(label="Move...", command=self.act_move)
        edit_menu.add_command(label="Rename...", command=self.act_rename)
        edit_menu.add_command(label="Delete", command=self.act_delete)
        edit_menu.add_command(label="Shred (secure delete)...", command=self.act_shred)
        edit_menu.add_separator()
        edit_menu.add_command(label="Properties...", command=self.act_properties)
        m.add_cascade(label="Edit", menu=edit_menu)

        view_menu = tk.Menu(m, tearoff=0)
        view_menu.add_checkbutton(label="Show hidden files",
                                  variable=self.show_hidden,
                                  command=self.refresh_all)
        view_menu.add_command(label="Toggle Dark Theme", command=self.toggle_theme)
        m.add_cascade(label="View", menu=view_menu)

        tools_menu = tk.Menu(m, tearoff=0)
        tools_menu.add_command(label="Find Duplicates...", command=lambda: self._select_tab("Integrity"))
        tools_menu.add_command(label="Disk Usage / Analytics", command=lambda: self._select_tab("Analytics"))
        tools_menu.add_command(label="Create Archive...", command=lambda: self._select_tab("Archive"))
        tools_menu.add_command(label="Verify Manifest...", command=lambda: self._select_tab("Integrity"))
        m.add_cascade(label="Tools", menu=tools_menu)

        help_menu = tk.Menu(m, tearoff=0)
        help_menu.add_command(label="Command Reference", command=self.show_help)
        help_menu.add_command(label="About", command=self.show_about)
        m.add_cascade(label="Help", menu=help_menu)

        self.master.bind("<F5>", lambda e: self.refresh_all())
        self.master.bind("<Delete>", lambda e: self.act_delete())

    def _build_layout(self) -> None:
        # Status bar (bottom)
        self.status_var = tk.StringVar(value="Ready")
        bar = ttk.Frame(self)
        bar.pack(side="bottom", fill="x")
        ttk.Label(bar, textvariable=self.status_var,
                  style="Status.TLabel").pack(side="left", padx=8, pady=3)
        self.busy_var = tk.StringVar(value="")
        ttk.Label(bar, textvariable=self.busy_var,
                  style="Status.TLabel").pack(side="right", padx=8)

        # Split: dir tree | notebook
        paned = ttk.Panedwindow(self, orient="horizontal")
        paned.pack(side="top", fill="both", expand=True)

        # --- left: directory tree
        left = ttk.Frame(paned)
        ttk.Label(left, text="Directories").pack(anchor="w", padx=8, pady=(6, 2))
        self.dir_tree = ttk.Treeview(left, selectmode="browse",
                                     columns=("fullpath", "loaded"), show="tree")
        self.dir_tree.column("#0", width=280)
        self.dir_tree.column("fullpath", width=0, stretch=False)
        self.dir_tree.column("loaded", width=0, stretch=False)
        self.dir_tree.pack(fill="both", expand=True, padx=4, pady=4)
        self.dir_tree.bind("<<TreeviewOpen>>", self._on_dir_expand)
        self.dir_tree.bind("<<TreeviewSelect>>", self._on_dir_select)
        paned.add(left, weight=1)

        # --- right: notebook of tools
        self.notebook = ttk.Notebook(paned)
        paned.add(self.notebook, weight=3)

        self._tab_browser()
        self._tab_search()
        self._tab_grep()
        self._tab_integrity()
        self._tab_archive()
        self._tab_analytics()
        self._tab_security()
        self._tab_text()

    def _select_tab(self, name: str) -> None:
        for tab in self.notebook.tabs():
            if self.notebook.tab(tab, "text") == name:
                self.notebook.select(tab)
                return

    # ================================================================== #
    # TAB: Browser
    # ================================================================== #

    def _tab_browser(self) -> None:
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Browser")

        # Path row
        row = ttk.Frame(tab)
        row.pack(fill="x", padx=8, pady=(8, 4))
        ttk.Label(row, text="Path:").pack(side="left")
        self.browse_var = tk.StringVar(value=str(self.current_dir))
        self.path_entry = ttk.Entry(row, textvariable=self.browse_var)
        self.path_entry.pack(side="left", fill="x", expand=True, padx=6)
        self.path_entry.bind("<Return>", lambda e: self.navigate(resolve(self.browse_var.get())))

        for text, cmd in (
            ("Go", lambda: self.navigate(resolve(self.browse_var.get()))),
            ("Up", lambda: self.navigate(self.current_dir.parent)),
            ("Home", lambda: self.navigate(resolve("~"))),
            ("Refresh", self.refresh_all),
        ):
            ttk.Button(row, text=text, command=cmd).pack(side="left", padx=2)

        # Toolbar
        tools = ttk.Frame(tab)
        tools.pack(fill="x", padx=8, pady=2)
        for text, cmd in (
            ("New File", self.act_new_file),
            ("New Folder", self.act_new_folder),
            ("Copy", self.act_copy),
            ("Move", self.act_move),
            ("Rename", self.act_rename),
            ("Delete", self.act_delete),
            ("Shred", self.act_shred),
            ("Properties", self.act_properties),
            ("Hash", self.act_hash_selected),
            ("Archive", self.act_archive_selected),
            ("Encrypt", self.act_encrypt_selected),
            ("Terminal", self.act_open_term),
        ):
            ttk.Button(tools, text=text, command=cmd).pack(side="left", padx=2, pady=2)

        # File table
        cols = ("name", "size", "type", "ext", "modified")
        self.file_tree = ttk.Treeview(tab, columns=cols, show="headings",
                                      selectmode="extended")
        widths = {"name": 320, "size": 110, "type": 60, "ext": 80, "modified": 170}
        for c in cols:
            self.file_tree.heading(c, text=c.capitalize(),
                                   command=lambda cc=c: self._sort_file_tree(cc))
            self.file_tree.column(c, width=widths[c], anchor="w")
        self.file_tree.column("size", anchor="e")
        self.file_tree.pack(fill="both", expand=True, padx=8, pady=8)

        self.file_tree.bind("<Double-1>", self._on_file_double)
        self.file_tree.bind("<Button-3>", self._on_file_context)

        ctx = tk.Menu(self, tearoff=0)
        for label, cmd in (
            ("Open / Navigate", lambda: self._on_file_double(None)),
            ("Copy...", self.act_copy),
            ("Move...", self.act_move),
            ("Rename...", self.act_rename),
            ("Delete", self.act_delete),
            ("Shred...", self.act_shred),
            ("Properties", self.act_properties),
            ("Hash (SHA-256)", self.act_hash_selected),
            ("Encrypt...", self.act_encrypt_selected),
        ):
            ctx.add_command(label=label, command=cmd)
        self.file_menu = ctx

    # ================================================================== #
    # TAB: Search
    # ================================================================== #

    def _tab_search(self) -> None:
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Search")

        form = ttk.Frame(tab)
        form.pack(fill="x", padx=8, pady=8)

        self.sv = {
            "root": tk.StringVar(value=str(self.current_dir)),
            "name": tk.StringVar(),
            "regex": tk.StringVar(),
            "ext": tk.StringVar(),
            "min": tk.StringVar(),
            "max": tk.StringVar(),
            "newer": tk.StringVar(),
            "older": tk.StringVar(),
            "content": tk.StringVar(),
            "depth": tk.StringVar(),
            "limit": tk.StringVar(value="500"),
        }
        self.sv_flags = {
            "files": tk.BooleanVar(value=True),
            "dirs": tk.BooleanVar(value=False),
            "empty": tk.BooleanVar(value=False),
            "hidden": tk.BooleanVar(value=False),
        }

        def entry(parent, label, var, r, c, w=14):
            ttk.Label(parent, text=label).grid(row=r, column=c * 2, sticky="e", padx=4, pady=3)
            e = ttk.Entry(parent, textvariable=var, width=w)
            e.grid(row=r, column=c * 2 + 1, sticky="w", padx=4)
            return e

        ttk.Label(form, text="Search root:").grid(row=0, column=0, sticky="e")
        ttk.Entry(form, textvariable=self.sv["root"], width=52).grid(row=0, column=1, columnspan=3, sticky="we")
        ttk.Button(form, text="Browse...", command=lambda: self._pick_dir(self.sv["root"])).grid(row=0, column=4)

        entry(form, "Name glob", self.sv["name"], 1, 0)
        entry(form, "Name regex", self.sv["regex"], 1, 1)
        entry(form, "Extensions (.py,.txt)", self.sv["ext"], 1, 2)
        entry(form, "Contains text", self.sv["content"], 2, 0)
        entry(form, "Min size (10k)", self.sv["min"], 2, 1)
        entry(form, "Max size (1G)", self.sv["max"], 2, 2)
        entry(form, "Newer than (7d)", self.sv["newer"], 3, 0)
        entry(form, "Older than (30d)", self.sv["older"], 3, 1)
        entry(form, "Max depth", self.sv["depth"], 3, 2)
        entry(form, "Result limit", self.sv["limit"], 4, 0)

        flags = ttk.Frame(form)
        flags.grid(row=5, column=0, columnspan=6, sticky="w", pady=4)
        ttk.Label(flags, text="Filters:").pack(side="left")
        for key, text in (("files", "Files only"), ("dirs", "Dirs only"),
                          ("empty", "Empty items"), ("hidden", "Include hidden")):
            ttk.Checkbutton(flags, text=text, variable=self.sv_flags[key]).pack(side="left", padx=8)

        ttk.Button(form, text="Find", style="Accent.TButton",
                   command=self.run_search).grid(row=5, column=5, padx=8)
        ttk.Button(form, text="Clear", command=lambda: [v.set("") for v in self.sv.values()
                                                        if v is not self.sv["root"]]).grid(row=5, column=6)

        cols = ("name", "size", "type", "modified", "path")
        self.search_tree = ttk.Treeview(tab, columns=cols, show="headings",
                                        selectmode="extended")
        for c in cols:
            self.search_tree.heading(c, text=c.capitalize())
        self.search_tree.column("name", width=260)
        self.search_tree.column("size", width=100, anchor="e")
        self.search_tree.column("type", width=50)
        self.search_tree.column("modified", width=150)
        self.search_tree.column("path", width=380)
        self.search_tree.pack(fill="both", expand=True, padx=8, pady=8)
        self.search_tree.bind("<Double-1>", self._on_search_double)
        self.search_tree.bind("<Button-3>", self._on_search_context)
        self.search_count = ttk.Label(tab, text="", style="Status.TLabel")
        self.search_count.pack(anchor="w", padx=10)

        ctx = tk.Menu(self, tearoff=0)
        ctx.add_command(label="Open location", command=self._on_search_double)
        ctx.add_command(label="View file", command=self._search_view_file)
        ctx.add_command(label="Copy path", command=self._search_copy_path)
        ctx.add_command(label="Delete selected", command=self._search_delete)
        ctx.add_command(label="Hash selected", command=self._search_hash)
        self.search_menu = ctx

    # ================================================================== #
    # TAB: Grep
    # ================================================================== #

    def _tab_grep(self) -> None:
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Grep")

        form = ttk.Frame(tab)
        form.pack(fill="x", padx=8, pady=8)
        self.gv = {
            "pattern": tk.StringVar(),
            "root": tk.StringVar(value=str(self.current_dir)),
            "include": tk.StringVar(),
            "exclude": tk.StringVar(),
        }
        self.g_regex = tk.BooleanVar(value=False)
        self.g_case = tk.BooleanVar(value=False)
        self.g_binary = tk.BooleanVar(value=True)

        ttk.Label(form, text="Pattern:").grid(row=0, column=0, sticky="e")
        ttk.Entry(form, textvariable=self.gv["pattern"], width=48).grid(row=0, column=1, columnspan=3, sticky="we")
        ttk.Label(form, text="Root:").grid(row=1, column=0, sticky="e")
        ttk.Entry(form, textvariable=self.gv["root"], width=48).grid(row=1, column=1, columnspan=3, sticky="we")
        ttk.Button(form, text="Browse...", command=lambda: self._pick_dir(self.gv["root"])).grid(row=1, column=4)

        ttk.Label(form, text="Include glob").grid(row=2, column=0, sticky="e")
        ttk.Entry(form, textvariable=self.gv["include"], width=18).grid(row=2, column=1, sticky="w")
        ttk.Label(form, text="Exclude glob").grid(row=2, column=2, sticky="e")
        ttk.Entry(form, textvariable=self.gv["exclude"], width=18).grid(row=2, column=3, sticky="w")

        flags = ttk.Frame(form)
        flags.grid(row=3, column=0, columnspan=5, sticky="w", pady=4)
        ttk.Checkbutton(flags, text="Regex", variable=self.g_regex).pack(side="left", padx=8)
        ttk.Checkbutton(flags, text="Case sensitive", variable=self.g_case).pack(side="left", padx=8)
        ttk.Checkbutton(flags, text="Skip binary", variable=self.g_binary).pack(side="left", padx=8)
        ttk.Button(flags, text="Search", style="Accent.TButton",
                   command=self.run_grep).pack(side="left", padx=16)

        self.grep_tree = ttk.Treeview(tab, columns=("path", "line_no", "line"),
                                      show="headings")
        self.grep_tree.heading("path", text="File")
        self.grep_tree.heading("line_no", text="Line")
        self.grep_tree.heading("line", text="Content")
        self.grep_tree.column("path", width=360)
        self.grep_tree.column("line_no", width=60, anchor="e")
        self.grep_tree.column("line", width=640)
        self.grep_tree.pack(fill="both", expand=True, padx=8, pady=8)
        self.grep_tree.bind("<Double-1>", self._on_grep_double)

    # ================================================================== #
    # TAB: Integrity
    # ================================================================== #

    def _tab_integrity(self) -> None:
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Integrity")

        # --- hash
        f1 = ttk.LabelFrame(tab, text="Hash a file")
        f1.pack(fill="x", padx=8, pady=6)
        self.hash_path = tk.StringVar()
        self.hash_algo = tk.StringVar(value="sha256")
        ttk.Entry(f1, textvariable=self.hash_path, width=64).pack(side="left", fill="x", expand=True, padx=6, pady=6)
        ttk.Button(f1, text="Browse...", command=lambda: self._pick_file(self.hash_path)).pack(side="left", padx=2)
        ttk.Combobox(f1, textvariable=self.hash_algo, values=list(utils.HASH_ALGOS),
                     state="readonly", width=10).pack(side="left", padx=2)
        ttk.Button(f1, text="Compute", command=self.run_hash).pack(side="left", padx=2)

        # --- compare
        f2 = ttk.LabelFrame(tab, text="Compare two files")
        f2.pack(fill="x", padx=8, pady=6)
        self.cmp_a = tk.StringVar()
        self.cmp_b = tk.StringVar()
        ttk.Entry(f2, textvariable=self.cmp_a, width=48).pack(side="left", fill="x", expand=True, padx=6, pady=6)
        ttk.Button(f2, text="A...", command=lambda: self._pick_file(self.cmp_a)).pack(side="left")
        ttk.Entry(f2, textvariable=self.cmp_b, width=48).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(f2, text="B...", command=lambda: self._pick_file(self.cmp_b)).pack(side="left")
        ttk.Button(f2, text="Compare", command=self.run_compare).pack(side="left", padx=6)

        # --- manifest
        f3 = ttk.LabelFrame(tab, text="Checksum manifest")
        f3.pack(fill="x", padx=8, pady=6)
        self.man_root = tk.StringVar(value=str(self.current_dir))
        ttk.Label(f3, text="Root:").pack(side="left")
        ttk.Entry(f3, textvariable=self.man_root, width=48).pack(side="left", padx=6, pady=6)
        ttk.Button(f3, text="Browse...", command=lambda: self._pick_dir(self.man_root)).pack(side="left")
        ttk.Button(f3, text="Create manifest", command=self.run_manifest_create).pack(side="left", padx=6)
        ttk.Button(f3, text="Verify manifest", command=self.run_manifest_verify).pack(side="left")

        # --- duplicates
        f4 = ttk.LabelFrame(tab, text="Duplicate finder")
        f4.pack(fill="both", expand=True, padx=8, pady=6)
        top = ttk.Frame(f4)
        top.pack(fill="x")
        self.dup_root = tk.StringVar(value=str(self.current_dir))
        self.dup_min = tk.StringVar(value="1B")
        ttk.Label(top, text="Root:").pack(side="left")
        ttk.Entry(top, textvariable=self.dup_root, width=42).pack(side="left", padx=4, pady=4)
        ttk.Button(top, text="Browse...", command=lambda: self._pick_dir(self.dup_root)).pack(side="left")
        ttk.Label(top, text="Min size:").pack(side="left", padx=(12, 0))
        ttk.Entry(top, textvariable=self.dup_min, width=8).pack(side="left", padx=4)
        ttk.Button(top, text="Find duplicates", style="Accent.TButton",
                   command=self.run_dupes).pack(side="left", padx=12)

        cols = ("size", "digest", "path")
        self.dup_tree = ttk.Treeview(f4, columns=cols, show="tree headings")
        self.dup_tree.heading("#0", text="Group")
        self.dup_tree.column("#0", width=280)
        for c in cols:
            self.dup_tree.heading(c, text=c.capitalize())
        self.dup_tree.column("size", width=100, anchor="e")
        self.dup_tree.column("digest", width=140)
        self.dup_tree.column("path", width=480)
        self.dup_tree.pack(fill="both", expand=True, padx=4, pady=4)
        self.dup_tree.bind("<Button-3>", self._on_dup_context)
        dmenu = tk.Menu(self, tearoff=0)
        dmenu.add_command(label="Delete selected file", command=self._dup_delete)
        dmenu.add_command(label="Open location", command=self._dup_locate)
        self.dup_menu = dmenu

        self.integrity_out = tk.Text(tab, height=4, wrap="none")
        self.integrity_out.pack(fill="x", padx=8, pady=(2, 8))

    # ================================================================== #
    # TAB: Archive
    # ================================================================== #

    def _tab_archive(self) -> None:
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Archive")

        # create
        f1 = ttk.LabelFrame(tab, text="Create archive (zip / tar / tar.gz / tar.bz2 / tar.xz)")
        f1.pack(fill="x", padx=8, pady=6)
        self.arc_sources: List[str] = []
        self.arc_src_var = tk.StringVar(value="(no sources selected)")
        self.arc_out = tk.StringVar()
        self.arc_fmt = tk.StringVar(value="zip")
        ttk.Label(f1, textvariable=self.arc_src_var, style="Status.TLabel").pack(side="left", padx=6, pady=6)
        ttk.Button(f1, text="Pick files...", command=self.pick_arc_files).pack(side="left", padx=2)
        ttk.Button(f1, text="Pick folder...", command=self.pick_arc_dir).pack(side="left", padx=2)
        ttk.Entry(f1, textvariable=self.arc_out, width=36).pack(side="left", padx=6)
        ttk.Button(f1, text="Output...", command=lambda: self._pick_save(self.arc_out)).pack(side="left")
        ttk.Combobox(f1, textvariable=self.arc_fmt, values=["zip", "tar"],
                     state="readonly", width=6).pack(side="left", padx=4)
        ttk.Button(f1, text="Create", style="Accent.TButton",
                   command=self.run_archive_create).pack(side="left", padx=4)

        # extract / list
        f2 = ttk.LabelFrame(tab, text="Extract / inspect archive")
        f2.pack(fill="x", padx=8, pady=6)
        self.arc_file = tk.StringVar()
        self.arc_dest = tk.StringVar()
        ttk.Entry(f2, textvariable=self.arc_file, width=52).pack(side="left", padx=6, pady=6)
        ttk.Button(f2, text="Archive...", command=lambda: self._pick_file(self.arc_file)).pack(side="left")
        ttk.Entry(f2, textvariable=self.arc_dest, width=36).pack(side="left", padx=6)
        ttk.Button(f2, text="Dest...", command=lambda: self._pick_dir(self.arc_dest, entry=True)).pack(side="left")
        ttk.Button(f2, text="Extract", style="Accent.TButton", command=self.run_archive_extract).pack(side="left", padx=4)
        ttk.Button(f2, text="List", command=self.run_archive_list).pack(side="left")

        # gzip / split / merge
        f3 = ttk.LabelFrame(tab, text="Gzip / split / merge")
        f3.pack(fill="x", padx=8, pady=6)
        self.gz_path = tk.StringVar()
        self.split_size = tk.StringVar(value="10M")
        self.split_path = tk.StringVar()
        ttk.Label(f3, text="File:").pack(side="left", padx=(6, 0))
        ttk.Entry(f3, textvariable=self.gz_path, width=44).pack(side="left", padx=4, pady=6)
        ttk.Button(f3, text="Browse...", command=lambda: self._pick_file(self.gz_path)).pack(side="left")
        ttk.Button(f3, text="Gzip", command=lambda: self.run_gzip(False)).pack(side="left", padx=2)
        ttk.Button(f3, text="Gunzip", command=lambda: self.run_gzip(True)).pack(side="left", padx=2)
        ttk.Label(f3, text="Split:").pack(side="left", padx=(16, 0))
        ttk.Entry(f3, textvariable=self.split_size, width=8).pack(side="left", padx=4)
        ttk.Button(f3, text="Split", command=self.run_split).pack(side="left", padx=2)
        ttk.Button(f3, text="Merge parts...", command=self.run_merge).pack(side="left", padx=2)

        # sync
        f4 = ttk.LabelFrame(tab, text="Incremental mirror (sync)")
        f4.pack(fill="x", padx=8, pady=6)
        self.sync_src = tk.StringVar()
        self.sync_dst = tk.StringVar()
        self.sync_delete = tk.BooleanVar(value=False)
        ttk.Label(f4, text="Source:").pack(side="left", padx=(6, 0))
        ttk.Entry(f4, textvariable=self.sync_src, width=38).pack(side="left", padx=4, pady=6)
        ttk.Button(f4, text="...", command=lambda: self._pick_dir(self.sync_src, entry=True)).pack(side="left")
        ttk.Label(f4, text="Dest:").pack(side="left", padx=(12, 0))
        ttk.Entry(f4, textvariable=self.sync_dst, width=38).pack(side="left", padx=4)
        ttk.Button(f4, text="...", command=lambda: self._pick_dir(self.sync_dst, entry=True)).pack(side="left")
        ttk.Checkbutton(f4, text="Delete extras", variable=self.sync_delete).pack(side="left", padx=8)
        ttk.Button(f4, text="Sync", style="Accent.TButton", command=self.run_sync).pack(side="left", padx=4)

        self.archive_out = tk.Text(tab, height=10, wrap="none")
        self.archive_out.pack(fill="both", expand=True, padx=8, pady=(2, 8))

    # ================================================================== #
    # TAB: Analytics
    # ================================================================== #

    def _tab_analytics(self) -> None:
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Analytics")

        form = ttk.Frame(tab)
        form.pack(fill="x", padx=8, pady=8)
        self.ana_root = tk.StringVar(value=str(self.current_dir))
        ttk.Label(form, text="Root:").pack(side="left")
        ttk.Entry(form, textvariable=self.ana_root, width=52).pack(side="left", padx=6)
        ttk.Button(form, text="Browse...", command=lambda: self._pick_dir(self.ana_root)).pack(side="left")
        for label, cmd in (
            ("Summary", self.run_summary),
            ("By extension", self.run_ext_summary),
            ("Largest", self.run_largest),
            ("Newest", self.run_newest),
            ("Oldest", self.run_oldest),
            ("Empty items", self.run_empty),
            ("Broken links", self.run_broken),
            ("Chart top extensions", self.run_chart),
        ):
            ttk.Button(form, text=label, command=cmd).pack(side="left", padx=3)

        body = ttk.Frame(tab)
        body.pack(fill="both", expand=True, padx=8, pady=4)
        self.chart = tk.Canvas(body, height=220, bg=self.theme["tree_field"],
                               highlightthickness=0)
        self.chart.pack(fill="x")
        self.ana_out = tk.Text(body, wrap="none")
        self.ana_out.pack(fill="both", expand=True, pady=(6, 0))

    # ================================================================== #
    # TAB: Security
    # ================================================================== #

    def _tab_security(self) -> None:
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Security")

        f1 = ttk.LabelFrame(tab, text="Encrypt / decrypt (PBKDF2 + SHA-256 stream, HMAC verified)")
        f1.pack(fill="x", padx=8, pady=6)
        self.sec_path = tk.StringVar()
        self.sec_pass = tk.StringVar()
        ttk.Label(f1, text="File:").pack(side="left", padx=(6, 0))
        ttk.Entry(f1, textvariable=self.sec_path, width=44).pack(side="left", padx=4, pady=6)
        ttk.Button(f1, text="Browse...", command=lambda: self._pick_file(self.sec_path)).pack(side="left")
        ttk.Label(f1, text="Password:").pack(side="left", padx=(12, 0))
        ttk.Entry(f1, textvariable=self.sec_pass, width=20, show="*").pack(side="left", padx=4)
        ttk.Button(f1, text="Encrypt", style="Accent.TButton",
                   command=self.run_encrypt).pack(side="left", padx=4)
        ttk.Button(f1, text="Decrypt", command=self.run_decrypt).pack(side="left")

        f2 = ttk.LabelFrame(tab, text="Secure delete (shred)")
        f2.pack(fill="x", padx=8, pady=6)
        self.shred_passes = tk.StringVar(value="3")
        ttk.Label(f2, text="Select files in the Browser tab, then shred here. Passes:").pack(side="left", padx=6, pady=6)
        ttk.Entry(f2, textvariable=self.shred_passes, width=5).pack(side="left")
        ttk.Button(f2, text="Shred selected", command=self.act_shred).pack(side="left", padx=6)

        f3 = ttk.LabelFrame(tab, text="Permissions")
        f3.pack(fill="both", expand=True, padx=8, pady=6)
        top = ttk.Frame(f3)
        top.pack(fill="x")
        self.perm_path = tk.StringVar()
        self.perm_mode = tk.StringVar()
        self.perm_recursive = tk.BooleanVar(value=False)
        ttk.Label(top, text="Path:").pack(side="left", padx=(6, 0))
        ttk.Entry(top, textvariable=self.perm_path, width=46).pack(side="left", padx=4, pady=4)
        ttk.Button(top, text="...", command=lambda: self._pick_file(self.perm_path)).pack(side="left")
        ttk.Label(top, text="Mode (644 / +x / go-w):").pack(side="left", padx=(12, 0))
        ttk.Entry(top, textvariable=self.perm_mode, width=10).pack(side="left", padx=4)
        ttk.Checkbutton(top, text="Recursive", variable=self.perm_recursive).pack(side="left", padx=4)
        ttk.Button(top, text="Apply", command=self.run_chmod).pack(side="left", padx=4)
        ttk.Button(top, text="Show", command=self.run_perms).pack(side="left")
        ttk.Button(top, text="Audit world-writable",
                   command=self.run_world_writable).pack(side="left", padx=4)

        self.sec_out = tk.Text(f3, wrap="none")
        self.sec_out.pack(fill="both", expand=True, padx=4, pady=4)

    # ================================================================== #
    # TAB: Text tools
    # ================================================================== #

    def _tab_text(self) -> None:
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Text Tools")

        form = ttk.Frame(tab)
        form.pack(fill="x", padx=8, pady=8)
        self.txt_path = tk.StringVar()
        self.txt_encoding = tk.StringVar(value="utf-8")
        ttk.Label(form, text="File:").pack(side="left")
        ttk.Entry(form, textvariable=self.txt_path, width=52).pack(side="left", padx=6)
        ttk.Button(form, text="Browse...", command=lambda: self._pick_file(self.txt_path)).pack(side="left")
        ttk.Combobox(form, textvariable=self.txt_encoding, width=8,
                     values=["utf-8", "utf-16", "latin-1", "ascii", "cp1252", "gbk"],
                     state="readonly").pack(side="left", padx=4)
        ttk.Button(form, text="Open", style="Accent.TButton",
                   command=self.run_text_open).pack(side="left", padx=4)
        ttk.Button(form, text="Save", command=self.run_text_save).pack(side="left", padx=2)
        ttk.Button(form, text="Word count", command=self.run_wc).pack(side="left", padx=2)
        ttk.Button(form, text="Convert encoding...", command=self.run_convert_enc).pack(side="left", padx=2)

        rep = ttk.Frame(tab)
        rep.pack(fill="x", padx=8, pady=(0, 4))
        self.rep_old = tk.StringVar()
        self.rep_new = tk.StringVar()
        self.rep_regex = tk.BooleanVar(value=False)
        self.rep_case = tk.BooleanVar(value=False)
        self.rep_dry = tk.BooleanVar(value=True)
        ttk.Label(rep, text="Replace:").pack(side="left", padx=(2, 0))
        ttk.Entry(rep, textvariable=self.rep_old, width=24).pack(side="left", padx=4)
        ttk.Label(rep, text="with:").pack(side="left")
        ttk.Entry(rep, textvariable=self.rep_new, width=24).pack(side="left", padx=4)
        ttk.Checkbutton(rep, text="Regex", variable=self.rep_regex).pack(side="left", padx=4)
        ttk.Checkbutton(rep, text="Ignore case", variable=self.rep_case).pack(side="left")
        ttk.Checkbutton(rep, text="Dry run", variable=self.rep_dry).pack(side="left", padx=4)
        ttk.Button(rep, text="Replace", command=self.run_replace).pack(side="left", padx=6)

        self.txt_area = tk.Text(tab, wrap="none", undo=True)
        ysb = ttk.Scrollbar(tab, orient="vertical", command=self.txt_area.yview)
        xsb = ttk.Scrollbar(tab, orient="horizontal", command=self.txt_area.xview)
        self.txt_area.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        self.txt_area.pack(fill="both", expand=True, side="left", padx=(8, 0), pady=8)
        xsb.pack(fill="x", side="bottom")
        ysb.pack(fill="y", side="right", padx=(0, 8))

    # ================================================================== #
    # Small pickers
    # ================================================================== #

    def _pick_dir(self, var: tk.StringVar, entry: bool = False) -> None:
        if entry:
            d = filedialog.askdirectory(initialdir=var.get() or os.getcwd())
        else:
            d = filedialog.askdirectory(initialdir=var.get() or os.getcwd(),
                                        mustexist=True)
        if d:
            var.set(d)

    def _pick_file(self, var: tk.StringVar) -> None:
        f = filedialog.askopenfilename(initialdir=os.path.dirname(var.get() or ".") or ".")
        if f:
            var.set(f)

    def _pick_save(self, var: tk.StringVar) -> None:
        f = filedialog.asksaveasfilename()
        if f:
            var.set(f)

    def _ask(self, title: str, prompt: str, initial: str = "") -> Optional[str]:
        return simpledialog.askstring(title, prompt, initialvalue=initial)

    def _text_out(self, widget: tk.Text, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="normal")

    def set_busy(self, label: Optional[str]) -> None:
        self.busy_var.set(label or "")

    # ------------------------------------------------------------------ #
    # Directory tree (left panel)
    # ------------------------------------------------------------------ #

    def _dir_children(self, path) -> List[str]:
        """
        Return immediate sub-directory *names* of `path`.

        Uses os.scandir with follow_symlinks=False so that symlinks,
        junctions and other reparse points are never followed — following
        them can block for the network timeout on disconnected shares.
        """
        try:
            path = resolve(str(path))
        except (OSError, ValueError):
            return []
        names: List[str] = []
        try:
            with os.scandir(path) as it:
                for entry in it:
                    try:
                        if not entry.is_dir(follow_symlinks=False):
                            continue
                        if entry.is_symlink():
                            continue
                        st = entry.stat(follow_symlinks=False)
                        attrs = getattr(st, "st_file_attributes", 0)
                        import stat as _stat

                        reparse = 0x400  # FILE_ATTRIBUTE_REPARSE_POINT
                        if getattr(_stat, "FILE_ATTRIBUTE_REPARSE_POINT", None):
                            reparse = _stat.FILE_ATTRIBUTE_REPARSE_POINT
                        if attrs & reparse:
                            continue  # junction / mount point
                    except OSError:
                        continue
                    if not self.show_hidden.get() and entry.name.startswith("."):
                        continue
                    names.append(entry.name)
        except (OSError, PermissionError):
            return []
        return sorted(names)

    def _on_dir_expand(self, _event) -> None:
        node = self.dir_tree.focus()
        if not node:
            return
        path = self.dir_tree.set(node, "fullpath")
        if self.dir_tree.set(node, "loaded") == "1":
            return
        self.dir_tree.delete(*self.dir_tree.get_children(node))
        base = Path(path)
        for name in self._dir_children(path):
            full = base / name
            iid = self.dir_tree.insert(node, "end", text=name,
                                       values=[str(full), "0"])
            # always show an expander; cleared on expand if empty
            self.dir_tree.insert(iid, "end", text="...")
        self.dir_tree.set(node, "loaded", "1")

    def _on_dir_select(self, _event) -> None:
        node = self.dir_tree.focus()
        if not node:
            return
        path = self.dir_tree.set(node, "fullpath")
        if path:
            self.navigate(path)

    def load_dir_tree(self) -> None:
        self.dir_tree.delete(*self.dir_tree.get_children(""))
        for drive in self._roots():
            iid = self.dir_tree.insert("", "end", text=drive,
                                       values=[drive, "0"], open=False)
            self.dir_tree.insert(iid, "end", text="...")

    @staticmethod
    def _roots() -> List[str]:
        if utils.IS_WINDOWS:
            import string

            roots = []
            for letter in string.ascii_uppercase:
                drive = f"{letter}:\\"
                if os.path.exists(drive):
                    roots.append(drive)
            return roots
        return ["/"]

    # ------------------------------------------------------------------ #
    # Browser tab logic
    # ------------------------------------------------------------------ #

    def navigate(self, path) -> None:
        path = resolve(str(path))
        if not path.is_dir():
            messagebox.showwarning(APP_TITLE, f"Not a directory: {path}")
            return
        self.current_dir = path
        self.browse_var.set(str(path))
        self.sv["root"].set(str(path))
        self.gv["root"].set(str(path))
        self.load_file_table()
        self.update_status()

    def load_file_table(self) -> None:
        tree = self.file_tree
        tree.delete(*tree.get_children(""))
        try:
            entries = core.list_dir(str(self.current_dir),
                                    show_hidden=self.show_hidden.get(),
                                    long=True, sort="name")
        except (OSError, FileForgeError) as exc:
            self.set_status(f"Cannot list {self.current_dir}: {exc}")
            return
        for e in entries:
            tree.insert("", "end", iid=str(e.path),
                        values=(e.path.name + ("/" if e.is_dir else ""),
                                "-" if e.is_dir else human_size(e.size),
                                "dir" if e.is_dir else ("link" if e.is_link else "file"),
                                e.ext or "",
                                human_time(e.mtime)))
        self.set_status(f"{self.current_dir}  -  {len(entries)} items")

    def _sort_file_tree(self, col: str) -> None:
        items = [(self.file_tree.set(iid, col), iid)
                 for iid in self.file_tree.get_children("")]
        if col in ("size", "modified"):
            items.sort(key=lambda kv: (kv[1] == "", _num(kv[0])), reverse=True)
        else:
            items.sort(key=lambda kv: kv[0].lower())
        for i, (_, iid) in enumerate(items):
            self.file_tree.move(iid, "", i)

    def _selected_paths(self) -> List[str]:
        return list(self.file_tree.selection())

    def _selected_files(self) -> List[str]:
        return [p for p in self._selected_paths() if os.path.isfile(p)]

    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def update_status(self) -> None:
        try:
            total, used, free = utils.free_space(self.current_dir)
            self.set_status(f"{self.current_dir}   |   free {human_size(free)} "
                            f"of {human_size(total)}")
        except OSError:
            pass

    def _on_file_double(self, _event) -> None:
        sel = self._selected_paths()
        if not sel:
            return
        path = resolve(sel[0])
        if path.is_dir():
            self.navigate(path)
        else:
            self.txt_path.set(str(path))
            self._select_tab("Text Tools")
            self.run_text_open()

    def _on_file_context(self, event) -> None:
        iid = self.file_tree.identify_row(event.y)
        if iid:
            self.file_tree.selection_set(iid)
            self.file_menu.tk_popup(event.x_root, event.y_root)

    # ------------------------------------------------------------------ #
    # Browser actions
    # ------------------------------------------------------------------ #

    def act_new_file(self) -> None:
        name = self._ask(APP_TITLE, "New file name:", "untitled.txt")
        if not name:
            return
        try:
            p = core.touch(str(self.current_dir / name))
            self.refresh_all()
            self.set_status(f"Created {p}")
        except (OSError, FileForgeError) as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def act_new_folder(self) -> None:
        name = self._ask(APP_TITLE, "New folder name:", "NewFolder")
        if not name:
            return
        try:
            core.make_dir(str(self.current_dir / name))
            self.refresh_all()
        except (OSError, FileForgeError) as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def act_copy(self) -> None:
        sel = self._selected_paths()
        if not sel:
            return
        dest = filedialog.askdirectory(title="Copy to folder")
        if not dest:
            return
        def job():
            out = []
            for s in sel:
                out.append(str(core.copy(s, dest, overwrite=False)))
            return out
        self.runner.run(job, lambda out: (self.refresh_all(),
                                          messagebox.showinfo(APP_TITLE, f"Copied {len(out)} item(s)")))

    def act_move(self) -> None:
        sel = self._selected_paths()
        if not sel:
            return
        dest = filedialog.askdirectory(title="Move to folder")
        if not dest:
            return
        def job():
            out = []
            for s in sel:
                out.append(str(core.move(s, dest, overwrite=False)))
            return out
        self.runner.run(job, lambda out: (self.refresh_all(),
                                          messagebox.showinfo(APP_TITLE, f"Moved {len(out)} item(s)")))

    def act_rename(self) -> None:
        sel = self._selected_paths()
        if len(sel) != 1:
            messagebox.showinfo(APP_TITLE, "Select exactly one item to rename.")
            return
        p = resolve(sel[0])
        new = self._ask(APP_TITLE, f"Rename '{p.name}' to:", p.name)
        if not new or new == p.name:
            return
        try:
            core.rename(str(p), new)
            self.refresh_all()
        except (OSError, FileForgeError) as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def act_delete(self) -> None:
        sel = self._selected_paths()
        if not sel:
            return
        if not messagebox.askyesno(
                APP_TITLE,
                f"Delete {len(sel)} selected item(s)?\n\n" + "\n".join(sel[:8]) +
                ("\n..." if len(sel) > 8 else ""),
                icon="warning"):
            return
        def job():
            removed = 0
            errs = []
            for s in sel:
                try:
                    core.remove(s, recursive=resolve(s).is_dir(), force=False)
                    removed += 1
                except (OSError, FileForgeError) as exc:
                    errs.append(f"{s}: {exc}")
            return removed, errs
        def done(res):
            removed, errs = res
            self.refresh_all()
            msg = f"Deleted {removed} item(s)."
            if errs:
                msg += "\n\nErrors:\n" + "\n".join(errs[:8])
                messagebox.showwarning(APP_TITLE, msg)
            else:
                self.set_status(msg)
        self.runner.run(job, done)

    def act_shred(self) -> None:
        sel = self._selected_files()
        if not sel:
            messagebox.showinfo(APP_TITLE, "Select file(s) in the Browser tab first.")
            return
        try:
            passes = int(self.shred_passes.get())
        except ValueError:
            passes = 3
        if not messagebox.askyesno(APP_TITLE,
                                   f"Securely overwrite and delete {len(sel)} file(s)?",
                                   icon="warning"):
            return
        def job():
            done_ = []
            for s in sel:
                try:
                    security.secure_delete(s, passes=passes)
                    done_.append(s)
                except (OSError, FileForgeError):
                    pass
            return done_
        self.runner.run(job, lambda d: (self.refresh_all(),
                                        self.set_status(f"Shredded {len(d)} file(s)")))

    def act_properties(self) -> None:
        sel = self._selected_paths()
        if len(sel) != 1:
            return
        try:
            data = core.stat_info(sel[0])
        except (OSError, FileForgeError) as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        win = tk.Toplevel(self)
        win.title(f"Properties - {data['name']}")
        win.geometry("480x480")
        txt = tk.Text(win, wrap="none")
        txt.pack(fill="both", expand=True, padx=8, pady=8)
        for k, v in data.items():
            txt.insert("end", f"{k:<16}: {v}\n")
        txt.configure(state="disabled")

    def act_hash_selected(self) -> None:
        sel = self._selected_files()
        if not sel:
            return
        def job():
            return [(s, utils.hash_file(resolve(s), "sha256")) for s in sel]
        def done(rows):
            self._select_tab("Integrity")
            self._text_out(self.integrity_out,
                           "\n".join(f"{d}  {p}" for p, d in rows))
        self.runner.run(job, done)

    def act_archive_selected(self) -> None:
        sel = self._selected_paths()
        if not sel:
            return
        out = filedialog.asksaveasfilename(title="Create archive",
                                           defaultextension=".zip",
                                           filetypes=[("zip", "*.zip"), ("tar.gz", "*.tar.gz")])
        if not out:
            return
        def job():
            return str(archive.create_archive(sel, out))
        self.runner.run(job, lambda p: (self.set_status(f"Archive created: {p}"),
                                        messagebox.showinfo(APP_TITLE, f"Archive created:\n{p}")))

    def act_encrypt_selected(self) -> None:
        sel = self._selected_files()
        if len(sel) != 1:
            messagebox.showinfo(APP_TITLE, "Select exactly one file to encrypt.")
            return
        self.sec_path.set(sel[0])
        self._select_tab("Security")
        self.sec_pass.set("")

    def act_open_fm(self) -> None:
        path = str(self.current_dir)
        try:
            if utils.IS_WINDOWS:
                os.startfile(path)  # type: ignore[attr-defined]
            elif utils.IS_MACOS:
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except OSError as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def act_open_term(self) -> None:
        path = str(self.current_dir)
        try:
            if utils.IS_WINDOWS:
                subprocess.Popen(["cmd", "/k", f"cd /d {path}"])
            elif utils.IS_MACOS:
                subprocess.Popen(["open", "-a", "Terminal", path])
            else:
                subprocess.Popen(["x-terminal-emulator", "--working-directory", path])
        except OSError as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def act_launch_shell(self) -> None:
        mod = f'"{sys.executable}" -m fileforge shell'
        try:
            if utils.IS_WINDOWS:
                subprocess.Popen(["cmd", "/k", mod])
            elif utils.IS_MACOS:
                script = f'tell application "Terminal" to do script "{mod}"'
                subprocess.Popen(["osascript", "-e", script])
            else:
                subprocess.Popen(["x-terminal-emulator", "-e", mod])
        except OSError as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    # ------------------------------------------------------------------ #
    # Search tab logic
    # ------------------------------------------------------------------ #

    def run_search(self) -> None:
        # Read every Tk variable on the main thread BEFORE spawning work.
        v, fl = self.sv, self.sv_flags
        root = v["root"].get()
        name_glob = v["name"].get().strip()
        name_re = v["regex"].get().strip()
        exts = [e.strip() for e in v["ext"].get().split(",") if e.strip()]
        min_s, max_s = v["min"].get(), v["max"].get()
        newer, older = v["newer"].get(), v["older"].get()
        content = v["content"].get() or None
        depth, limit = v["depth"].get(), v["limit"].get()
        files_only = fl["files"].get() and not fl["dirs"].get()
        dirs_only = fl["dirs"].get()
        empty = fl["empty"].get()
        hidden = fl["hidden"].get()

        def job():
            crit = search.FindCriteria(
                root=root,
                name=[name_glob] if name_glob else [],
                regex=name_re or None,
                extensions=exts,
                min_size=search.parse_size(min_s) if min_s else None,
                max_size=search.parse_size(max_s) if max_s else None,
                newer_than=search.parse_duration(newer) if newer else None,
                older_than=search.parse_duration(older) if older else None,
                content=content,
                files_only=files_only,
                dirs_only=dirs_only,
                empty=empty,
                include_hidden=hidden,
                max_depth=int(depth) if depth.isdigit() else None,
                limit=int(limit) if limit.isdigit() else None,
            )
            return search.find(crit)
        self.runner.run(job, self._show_search_results, "Searching")

    def _show_search_results(self, entries) -> None:
        tree = self.search_tree
        tree.delete(*tree.get_children(""))
        for e in entries:
            tree.insert("", "end", iid=str(e.path),
                        values=(e.path.name + ("/" if e.is_dir else ""),
                                "-" if e.is_dir else human_size(e.size),
                                "dir" if e.is_dir else "file",
                                human_time(e.mtime),
                                str(e.path.parent)))
        self.search_count.configure(
            text=f"{len(entries)} result(s) - double-click to open location")

    def _on_search_double(self, _event=None) -> None:
        sel = self.search_tree.selection()
        if not sel:
            return
        path = resolve(sel[0])
        if path.is_dir():
            self.navigate(path)
        else:
            self.navigate(path.parent)
        for iid in self.file_tree.get_children():
            if iid == str(path):
                self.file_tree.selection_set(iid)
                self.file_tree.see(iid)
                break

    def _on_search_context(self, event) -> None:
        iid = self.search_tree.identify_row(event.y)
        if iid:
            self.search_tree.selection_set(iid)
            self.search_menu.tk_popup(event.x_root, event.y_root)

    def _search_view_file(self) -> None:
        sel = self.search_tree.selection()
        if sel:
            self.txt_path.set(sel[0])
            self._select_tab("Text Tools")
            self.run_text_open()

    def _search_copy_path(self) -> None:
        sel = self.search_tree.selection()
        if sel:
            self.master.clipboard_clear()
            self.master.clipboard_append("\n".join(sel))

    def _search_delete(self) -> None:
        sel = list(self.search_tree.selection())
        if not sel:
            return
        if not messagebox.askyesno(APP_TITLE, f"Delete {len(sel)} item(s)?", icon="warning"):
            return
        def job():
            n = 0
            for s in sel:
                try:
                    core.remove(s, recursive=resolve(s).is_dir(), force=False)
                    n += 1
                except (OSError, FileForgeError):
                    pass
            return n
        self.runner.run(job, lambda n: self.run_search() if n else None)

    def _search_hash(self) -> None:
        sel = [s for s in self.search_tree.selection() if os.path.isfile(s)]
        if not sel:
            return
        def job():
            return [(s, utils.hash_file(resolve(s), "sha256")) for s in sel]
        def done(rows):
            self._select_tab("Integrity")
            self._text_out(self.integrity_out,
                           "\n".join(f"{d}  {p}" for p, d in rows))
        self.runner.run(job, done)

    # ------------------------------------------------------------------ #
    # Grep tab logic
    # ------------------------------------------------------------------ #

    def run_grep(self) -> None:
        pattern = self.gv["pattern"].get()
        if not pattern:
            messagebox.showwarning(APP_TITLE, "Enter a search pattern.")
            return
        # capture Tk state on the main thread
        root = self.gv["root"].get()
        include = [g for g in (self.gv["include"].get().strip(),) if g]
        exclude = [g for g in (self.gv["exclude"].get().strip(),) if g]
        use_regex = self.g_regex.get()
        ignore_case = not self.g_case.get()
        skip_binary = self.g_binary.get()

        def job():
            return search.grep(pattern, [root], regex=use_regex,
                               ignore_case=ignore_case, include=include,
                               exclude=exclude, binary_skip=skip_binary)
        self.runner.run(job, self._show_grep_results, "Grepping")

    def _show_grep_results(self, matches) -> None:
        tree = self.grep_tree
        tree.delete(*tree.get_children(""))
        for m in matches:
            tree.insert("", "end", values=(str(m.path), m.line_no, m.line[:400]))
        self.set_status(f"grep: {len(matches)} match(es)")

    def _on_grep_double(self, _event) -> None:
        sel = self.grep_tree.selection()
        if not sel:
            return
        path, line_no, _ = self.grep_tree.item(sel[0], "values")
        self.txt_path.set(path)
        self._select_tab("Text Tools")
        self.run_text_open()
        # jump to line
        try:
            idx = f"{int(line_no)}.0"
            self.txt_area.see(idx)
            self.txt_area.mark_set("insert", idx)
            self.txt_area.tag_remove("hit", "1.0", "end")
            self.txt_area.tag_add("hit", f"{idx} linestart", f"{idx} lineend+1c")
        except (ValueError, tk.TclError):
            pass

    # ------------------------------------------------------------------ #
    # Integrity tab logic
    # ------------------------------------------------------------------ #

    def run_hash(self) -> None:
        path = self.hash_path.get()
        if not path:
            return
        algo = self.hash_algo.get()
        self.runner.run(lambda: utils.hash_file(resolve(path), algo),
                        lambda d: self._text_out(self.integrity_out,
                                                 f"{algo}:{d}  {path}"))

    def run_compare(self) -> None:
        a, b = self.cmp_a.get(), self.cmp_b.get()
        if not (a and b):
            return
        def job():
            r = hashutil.compare_files(a, b)
            lines = [
                f"A: {a}  ({human_size(r.size_a)})",
                f"B: {b}  ({human_size(r.size_b)})",
                f"identical : {r.identical}",
                f"digest A  : {r.digest_a}",
                f"digest B  : {r.digest_b}",
            ]
            if r.first_diff is not None:
                lines.append(f"first difference at byte {r.first_diff}")
            return "\n".join(lines)
        self.runner.run(job, lambda t: self._text_out(self.integrity_out, t))

    def run_manifest_create(self) -> None:
        root = self.man_root.get()
        def job():
            out = hashutil.create_manifest(root)
            return str(out)
        self.runner.run(job, lambda o: self._text_out(
            self.integrity_out, f"Manifest created: {o}"), "Creating manifest")

    def run_manifest_verify(self) -> None:
        root = resolve(self.man_root.get())
        manifest = root / f".fileforge-manifest-sha256.json"
        if not manifest.exists():
            candidates = list(root.glob(".fileforge-manifest-*.json")) + \
                         list(root.glob("manifest.json"))
            if not candidates:
                messagebox.showwarning(APP_TITLE, "No manifest found under root.")
                return
            manifest = candidates[0]
        def job():
            rep = hashutil.verify_manifest(str(manifest), detect_extra=True)
            lines = [f"manifest : {manifest}",
                     f"checked  : {rep.checked}",
                     f"ok       : {rep.ok}"]
            for label, items in (("modified", rep.modified), ("missing", rep.missing),
                                 ("extra", rep.extra)):
                if items:
                    lines.append(f"{label:<9}: {len(items)}")
                    lines += [f"   {m}" for m in items[:10]]
            return "\n".join(lines)
        self.runner.run(job, lambda t: self._text_out(self.integrity_out, t),
                        "Verifying")

    def run_dupes(self) -> None:
        root = self.dup_root.get()
        try:
            min_size = search.parse_size(self.dup_min.get() or "1B")
        except FileForgeError:
            min_size = 1
        def job():
            return hashutil.find_duplicates(root, min_size=min_size)
        self.runner.run(job, self._show_dupes, "Finding duplicates")

    def _show_dupes(self, groups) -> None:
        tree = self.dup_tree
        tree.delete(*tree.get_children(""))
        wasted_total = 0
        for i, g in enumerate(groups, 1):
            wasted_total += g.wasted
            parent = tree.insert("", "end", open=True,
                                 text=f"#{i}  {human_size(g.size)} x {len(g.files)}",
                                 values=(human_size(g.size), g.digest[:16] + "...", ""))
            for f in g.files:
                tree.insert(parent, "end", text="", values=("", "", str(f)))
        self.set_status(f"{len(groups)} duplicate group(s), "
                        f"reclaimable {human_size(wasted_total)}")

    def _on_dup_context(self, event) -> None:
        iid = self.dup_tree.identify_row(event.y)
        if iid:
            self.dup_tree.selection_set(iid)
            self.dup_menu.tk_popup(event.x_root, event.y_root)

    def _dup_delete(self) -> None:
        sel = self.dup_tree.selection()
        targets = [s for s in sel if self.dup_tree.parent(s)]
        if not targets:
            return
        if not messagebox.askyesno(APP_TITLE, f"Delete {len(targets)} duplicate file(s)?",
                                   icon="warning"):
            return
        def job():
            n = 0
            for s in targets:
                try:
                    core.remove(s, force=True)
                    n += 1
                except (OSError, FileForgeError):
                    pass
            return n
        self.runner.run(job, lambda n: (self.set_status(f"Deleted {n} duplicate(s)"),
                                        self.run_dupes()))

    def _dup_locate(self) -> None:
        sel = self.dup_tree.selection()
        if sel:
            p = resolve(self.dup_tree.set(sel[0], "path") or sel[0])
            if p.parent.is_dir():
                self.navigate(p.parent)

    # ------------------------------------------------------------------ #
    # Archive tab logic
    # ------------------------------------------------------------------ #

    def pick_arc_files(self) -> None:
        files = filedialog.askopenfilenames()
        if files:
            self.arc_sources = list(files)
            self.arc_src_var.set(f"{len(files)} file(s) selected")

    def pick_arc_dir(self) -> None:
        d = filedialog.askdirectory()
        if d:
            self.arc_sources = [d]
            self.arc_src_var.set(d)

    def run_archive_create(self) -> None:
        if not self.arc_sources or not self.arc_out.get():
            messagebox.showwarning(APP_TITLE, "Pick sources and an output path first.")
            return
        out, fmt = self.arc_out.get(), self.arc_fmt.get()
        srcs = list(self.arc_sources)
        def job():
            p = archive.create_archive(srcs, out, fmt=fmt)
            return f"Created {p} ({human_size(p.stat().st_size)})"
        self.runner.run(job, lambda t: self._text_out(self.archive_out, t),
                        "Archiving")

    def run_archive_extract(self) -> None:
        arc, dest = self.arc_file.get(), self.arc_dest.get()
        if not arc:
            return
        def job():
            p = archive.extract_archive(arc, dest or ".")
            return f"Extracted to {p}"
        self.runner.run(job, lambda t: self._text_out(self.archive_out, t),
                        "Extracting")

    def run_archive_list(self) -> None:
        arc = self.arc_file.get()
        if not arc:
            return
        def job():
            return "\n".join(
                f"{'d' if it['is_dir'] else '-'} {human_size(it['size']):>10}  "
                f"{it['date']}  {it['name']}" for it in archive.list_archive(arc))
        self.runner.run(job, lambda t: self._text_out(self.archive_out, t),
                        "Listing")

    def run_gzip(self, decompress: bool) -> None:
        path = self.gz_path.get()
        if not path:
            return
        def job():
            out = archive.gunzip_file(path, keep=True) if decompress \
                else archive.gzip_file(path, keep=True)
            return f"Done -> {out}"
        self.runner.run(job, lambda t: self._text_out(self.archive_out, t))

    def run_split(self) -> None:
        path = self.split_path.get() or self.gz_path.get()
        if not path:
            messagebox.showwarning(APP_TITLE, "Choose a file to split first.")
            return
        try:
            size = search.parse_size(self.split_size.get())
        except FileForgeError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        def job():
            parts = archive.split_file(path, size)
            return "Parts:\n" + "\n".join(f"  {p}  ({human_size(p.stat().st_size)})"
                                         for p in parts)
        self.runner.run(job, lambda t: self._text_out(self.archive_out, t), "Splitting")

    def run_merge(self) -> None:
        parts = filedialog.askopenfilenames(title="Select parts in order")
        if not parts:
            return
        out = filedialog.asksaveasfilename(title="Merge into")
        if not out:
            return
        self.runner.run(lambda: f"Merged -> {archive.merge_files(list(parts), out)}",
                        lambda t: self._text_out(self.archive_out, t), "Merging")

    def run_sync(self) -> None:
        src, dst = self.sync_src.get(), self.sync_dst.get()
        if not (src and dst):
            messagebox.showwarning(APP_TITLE, "Choose source and destination.")
            return
        delete = self.sync_delete.get()
        def job():
            rep = archive.sync_tree(src, dst, delete=delete)
            return (f"sync done: copied={rep.copied} updated={rep.updated} "
                    f"skipped={rep.skipped} removed={rep.removed}")
        self.runner.run(job, lambda t: self._text_out(self.archive_out, t), "Syncing")

    # ------------------------------------------------------------------ #
    # Analytics tab logic
    # ------------------------------------------------------------------ #

    def _ana_lines(self, entries) -> str:
        return "\n".join(f"{human_size(e.size):>12}  {human_time(e.mtime)}  {e.rel}"
                         for e in entries)

    def run_summary(self) -> None:
        root = self.ana_root.get()
        def job():
            s = analytics.summarize(root)
            lines = [f"Summary of {s.root}",
                     f"files={s.files}  dirs={s.dirs}  links={s.links}  "
                     f"total={human_size(s.total_bytes)}",
                     f"empty files={s.empty_files}  empty dirs={s.empty_dirs}  "
                     f"broken links={s.broken_links}",
                     "", "Top extensions:"]
            lines += [f"  {ext:<12} {count:>6}  {human_size(size):>10}"
                      for ext, count, size in s.top_ext]
            lines += ["", "Largest files:"] + [f"  {human_size(e.size):>10}  {e.rel}"
                                               for e in s.largest]
            lines += ["", "Newest files:"] + [f"  {human_time(e.mtime)}  {e.rel}"
                                              for e in s.newest]
            return "\n".join(lines)
        self.runner.run(job, lambda t: self._text_out(self.ana_out, t), "Summarizing")

    def run_ext_summary(self) -> None:
        root = self.ana_root.get()
        self.runner.run(
            lambda: "\n".join(f"{ext:<12} {count:>6}  {human_size(size):>10}"
                              for ext, count, size in analytics.extension_summary(root)),
            lambda t: self._text_out(self.ana_out, t), "Scanning extensions")

    def run_largest(self) -> None:
        root = self.ana_root.get()
        self.runner.run(
            lambda: self._ana_lines(analytics.largest_files(root, limit=50)),
            lambda t: self._text_out(self.ana_out, t), "Scanning")

    def run_newest(self) -> None:
        root = self.ana_root.get()
        self.runner.run(
            lambda: self._ana_lines(analytics.newest_files(root, limit=50)),
            lambda t: self._text_out(self.ana_out, t), "Scanning")

    def run_oldest(self) -> None:
        root = self.ana_root.get()
        self.runner.run(
            lambda: self._ana_lines(analytics.oldest_files(root, limit=50)),
            lambda t: self._text_out(self.ana_out, t), "Scanning")

    def run_empty(self) -> None:
        root = self.ana_root.get()

        def job():
            rep = analytics.find_empty(root)
            lines = [f"Empty files ({len(rep.empty_files)}):"]
            lines += [f"  {p}" for p in rep.empty_files[:50]]
            lines.append(f"Empty directories ({len(rep.empty_dirs)}):")
            lines += [f"  {p}" for p in rep.empty_dirs[:50]]
            return "\n".join(lines)
        self.runner.run(job, lambda t: self._text_out(self.ana_out, t), "Scanning")

    def run_broken(self) -> None:
        root = self.ana_root.get()
        self.runner.run(
            lambda: "\n".join(str(p) for p in analytics.find_broken_links(root))
                    or "No broken links.",
            lambda t: self._text_out(self.ana_out, t), "Scanning")

    def run_chart(self) -> None:
        root = self.ana_root.get()
        def job():
            return analytics.extension_summary(root)[:12]
        self.runner.run(job, self._draw_chart, "Scanning")

    def _draw_chart(self, rows) -> None:
        c = self.chart
        c.delete("all")
        t = self.theme
        w = max(int(c.winfo_width()), 400)
        h = 220
        if not rows:
            c.create_text(w // 2, h // 2, text="no data", fill=t["muted"])
            return
        label_w, pad = 90, 30
        chart_w = w - label_w - 40
        max_size = max(r[2] for r in rows) or 1
        bar_h = min(16, (h - 20) // len(rows) - 4)
        for i, (ext, count, size) in enumerate(rows):
            y = 10 + i * (bar_h + 6)
            bw = int(chart_w * size / max_size)
            c.create_rectangle(label_w, y, label_w + max(bw, 1), y + bar_h,
                               fill=t["accent"] if i == 0 else t["muted"],
                               outline="")
            c.create_text(label_w - 8, y + bar_h // 2, text=ext, anchor="e",
                          fill=t["fg"])
            c.create_text(label_w + max(bw, 1) + 8, y + bar_h // 2,
                          text=human_size(size), anchor="w", fill=t["fg"])

    # ------------------------------------------------------------------ #
    # Security tab logic
    # ------------------------------------------------------------------ #

    def run_encrypt(self) -> None:
        path, pwd = self.sec_path.get(), self.sec_pass.get()
        if not (path and pwd):
            messagebox.showwarning(APP_TITLE, "Choose a file and enter a password.")
            return
        def job():
            out = security.encrypt_file(path, pwd)
            return f"Encrypted -> {out}"
        self.runner.run(job, lambda t: (self._text_out(self.sec_out, t),
                                        self.refresh_all()), "Encrypting")

    def run_decrypt(self) -> None:
        path, pwd = self.sec_path.get(), self.sec_pass.get()
        if not (path and pwd):
            messagebox.showwarning(APP_TITLE, "Choose a file and enter a password.")
            return
        def job():
            out = security.decrypt_file(path, pwd)
            return f"Decrypted -> {out}"
        self.runner.run(job, lambda t: (self._text_out(self.sec_out, t),
                                        self.refresh_all()), "Decrypting")

    def run_chmod(self) -> None:
        path, mode = self.perm_path.get(), self.perm_mode.get()
        recursive = self.perm_recursive.get()
        if not (path and mode):
            return
        def job():
            n = security.chmod(path, mode, recursive=recursive)
            return f"Changed {n} path(s)"
        self.runner.run(job, lambda t: self._text_out(self.sec_out, t))

    def run_perms(self) -> None:
        path = self.perm_path.get()
        recursive = self.perm_recursive.get()
        if not path:
            return
        self.runner.run(
            lambda: "\n".join(f"{e.mode}  {e.octal:>6}  {e.path}"
                              for e in security.list_permissions(path, recursive=recursive)),
            lambda t: self._text_out(self.sec_out, t))

    def run_world_writable(self) -> None:
        root = self.ana_root.get()
        self.runner.run(
            lambda: "\n".join(str(p) for p in security.find_world_writable(root))
                    or "No world-writable entries.",
            lambda t: self._text_out(self.sec_out, t), "Auditing")

    # ------------------------------------------------------------------ #
    # Text tab logic
    # ------------------------------------------------------------------ #

    def run_text_open(self) -> None:
        path = self.txt_path.get()
        encoding = self.txt_encoding.get()
        if not path:
            return
        def job():
            return core.read_text(path, encoding=encoding, errors="replace")
        def done(text):
            self.txt_area.tag_remove("hit", "1.0", "end")
            self.txt_area.delete("1.0", "end")
            self.txt_area.insert("1.0", text)
            self.txt_area.tag_configure("hit", background=self.theme["select"])
            self.set_status(f"Opened {path}")
        self.runner.run(job, done)

    def run_text_save(self) -> None:
        path = self.txt_path.get()
        encoding = self.txt_encoding.get()
        content = self.txt_area.get("1.0", "end-1c")
        if not path:
            return
        try:
            core.write_text(path, content, encoding=encoding)
            self.set_status(f"Saved {path}")
        except (OSError, FileForgeError) as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def run_wc(self) -> None:
        path = self.txt_path.get()
        if not path:
            return
        self.runner.run(lambda: core.word_count(path),
                        lambda s: self.set_status(
                            f"{path}: lines={s.lines} words={s.words} "
                            f"chars={s.chars} bytes={s.bytes}"))

    def run_convert_enc(self) -> None:
        path = self.txt_path.get()
        if not path:
            return
        to = self._ask(APP_TITLE, "Convert to encoding:", "utf-8")
        if not to:
            return
        def job():
            out = core.convert_encoding(path, to)
            return f"Converted -> {out}"
        self.runner.run(job, lambda t: self.set_status(t))

    def run_replace(self) -> None:
        path = self.txt_path.get()
        old, new = self.rep_old.get(), self.rep_new.get()
        use_regex = self.rep_regex.get()
        ignore_case = self.rep_case.get()
        dry_run = self.rep_dry.get()
        if not (path and old):
            return
        def job():
            return core.replace_in_file(path, old, new, regex=use_regex,
                                        ignore_case=ignore_case, dry_run=dry_run)
        def done(n):
            msg = f"{n} replacement(s)" + (" (dry run)" if dry_run else "")
            self.set_status(f"{path}: {msg}")
            if not dry_run:
                self.run_text_open()
        self.runner.run(job, done)

    # ------------------------------------------------------------------ #
    # Misc
    # ------------------------------------------------------------------ #

    def refresh_all(self) -> None:
        self.load_file_table()
        self.load_dir_tree()
        self.update_status()

    def show_help(self) -> None:
        win = tk.Toplevel(self)
        win.title("Command Reference")
        win.geometry("720x520")
        txt = tk.Text(win, wrap="word")
        txt.pack(fill="both", expand=True, padx=8, pady=8)
        from .cli import build_parser
        txt.insert("end", "All CLI commands (also usable from a terminal):\n\n")
        parser = build_parser()
        for action in parser._subparsers._group_actions[0].choices.items():  # type: ignore[attr-defined]
            name, sub = action
            txt.insert("end", f"{name:<18} {sub.description or ''}\n")
        txt.configure(state="disabled")

    def show_about(self) -> None:
        messagebox.showinfo(
            "About",
            f"{APP_TITLE} {APP_VERSION}\n\n"
            f"Portable file-system toolkit for Linux, Windows and macOS.\n"
            f"Python {platform.python_version()} | Tk {tk.TkVersion} | "
            f"{utils.platform_name()}\n\n"
            "Pure standard library - no third-party dependencies.")


def _num(text: str) -> float:
    try:
        return float(text.split()[0].replace(",", ""))
    except (ValueError, IndexError):
        return 0.0


def main() -> int:
    root = tk.Tk()
    FileForgeApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
