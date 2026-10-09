"""
fileforge.cli
=============

Command line interface. Every capability of the toolkit is exposed as a
sub-command, e.g.::

    python -m fileforge ls -l .
    python -m fileforge find . --ext .py --min-size 1k
    python -m fileforge grep TODO src --include "*.py"
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import shlex
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from . import (analytics, archive, core, hashutil, search, security, utils,
               __version__ as _PKG_VERSION)
from .utils import (FileForgeError, PathError, error, heading, human_size,
                    human_time, info, ok, paint, warn, _Style)

PROG = "fileforge"
# Single source of truth: the package version. It used to be a hard-coded
# "1.0.0" here, which made `fileforge --version` report 1.0.0 no matter which
# release was actually installed.
VERSION = _PKG_VERSION


# --------------------------------------------------------------------------- #
# Rendering helpers
# --------------------------------------------------------------------------- #

def _print_entries(entries, long: bool = False, show_tree_prefix: bool = False) -> None:
    if not entries:
        warn("No matches.")
        return
    for e in entries:
        if long:
            kind = "d" if e.is_dir else ("l" if e.is_link else "-")
            size = "-" if e.is_dir else human_size(e.size)
            print(f"{kind} {utils.octal_mode(e.mode):>6} {size:>10} "
                  f"{human_time(e.mtime)}  {e.rel}")
        else:
            suffix = "/" if e.is_dir else ""
            print(paint(e.rel + suffix, _Style.BOLD if e.is_dir else _Style.RESET))
    if long:
        print(paint(f"({len(entries)} items)", _Style.DIM))


def _print_kv(data: dict, indent: str = "  ") -> None:
    width = max((len(k) for k in data), default=0)
    for k, v in data.items():
        print(f"{indent}{paint(k + ':', _Style.BOLD):<{width + 10}} {v}")


def _get_password(args, confirm: bool = False) -> str:
    pwd = getattr(args, "password", None)
    if pwd:
        return pwd
    pwd = getpass.getpass("Password: ")
    if confirm:
        again = getpass.getpass("Confirm : ")
        if pwd != again:
            raise PathError("Passwords do not match")
    return pwd


# --------------------------------------------------------------------------- #
# Command implementations
# --------------------------------------------------------------------------- #

def cmd_ls(args) -> int:
    entries = core.list_dir(args.path, show_hidden=args.hidden,
                            long=args.long, sort=args.sort)
    if args.long and not entries:
        warn("Directory is empty.")
        return 0
    _print_entries(entries, long=args.long)
    return 0


def cmd_tree(args) -> int:
    node = core.build_tree(args.path, max_depth=args.depth, include_hidden=args.hidden)
    for line in core.render_tree(node, show_size=not args.no_size):
        print(line)
    return 0


def cmd_find(args) -> int:
    criteria = search.FindCriteria(
        root=args.root,
        name=args.name or [],
        regex=args.regex,
        extensions=args.ext or [],
        min_size=search.parse_size(args.min_size) if args.min_size else None,
        max_size=search.parse_size(args.max_size) if args.max_size else None,
        newer_than=search.parse_duration(args.newer) if args.newer else None,
        older_than=search.parse_duration(args.older) if args.older else None,
        content=args.content,
        files_only=args.files_only,
        dirs_only=args.dirs_only,
        empty=args.empty,
        include_hidden=args.hidden,
        max_depth=args.depth,
        follow_symlinks=args.follow,
        limit=args.limit,
    )
    results = search.find(criteria)
    _print_entries(results, long=args.long)
    return 0 if results else 1


def cmd_grep(args) -> int:
    matches = search.grep(
        args.pattern, args.paths, regex=args.regex,
        ignore_case=not args.case_sensitive, include=args.include or [],
        exclude=args.exclude or [], recursive=not args.no_recursive,
        max_matches=args.max,
    )
    for m in matches:
        print(f"{paint(str(m.path), _Style.MAGENTA)}:{paint(str(m.line_no), _Style.CYAN)}: {m.line}".rstrip())
    if not matches:
        warn("No matches.")
        return 1
    print(paint(f"({len(matches)} matches)", _Style.DIM))
    return 0


def cmd_cat(args) -> int:
    p = utils.ensure_exists(utils.resolve(args.path))
    text = p.read_text(encoding=args.encoding, errors="replace")
    lines = text.splitlines()
    if args.head is not None:
        lines = lines[: args.head]
    elif args.tail is not None:
        lines = lines[-args.tail:]
    for i, line in enumerate(lines, 1):
        if args.number:
            print(f"{paint(f'{i:>6}', _Style.DIM)}\t{line}")
        else:
            print(line)
    return 0


def cmd_write(args) -> int:
    if args.stdin:
        content = sys.stdin.read()
    elif args.content is not None:
        content = args.content
    elif args.file:
        content = utils.resolve(args.file).read_text(encoding="utf-8")
    else:
        raise PathError("Provide --content, --stdin or --file")
    n = core.write_text(args.path, content, encoding=args.encoding,
                        append=args.append, newline=args.newline)
    ok(f"{'Appended' if args.append else 'Wrote'} {n} chars to {args.path}")
    return 0


def cmd_touch(args) -> int:
    p = core.touch(args.path)
    ok(f"Touched {p}")
    return 0


def cmd_cp(args) -> int:
    dst = core.copy(args.src, args.dest, overwrite=args.overwrite,
                    recursive=not args.no_recursive, preserve=not args.no_preserve)
    ok(f"Copied -> {dst}")
    return 0


def cmd_mv(args) -> int:
    dst = core.move(args.src, args.dest, overwrite=args.overwrite)
    ok(f"Moved -> {dst}")
    return 0


def cmd_rm(args) -> int:
    if args.secure:
        n = security.secure_delete(args.path, passes=args.passes)
        ok(f"Securely deleted {args.path} ({human_size(n)} overwritten)")
        return 0
    removed = core.remove(args.path, recursive=args.recursive, force=args.force)
    if removed:
        ok(f"Removed {len(removed)} path(s)")
    else:
        warn("Nothing to remove.")
    return 0


def cmd_mkdir(args) -> int:
    p = core.make_dir(args.path, parents=not args.no_parents, exist_ok=args.exist_ok)
    ok(f"Created {p}")
    return 0


def cmd_rename(args) -> int:
    p = core.rename(args.path, args.new_name)
    ok(f"Renamed -> {p}")
    return 0


def cmd_rename_batch(args) -> int:
    res = core.batch_rename(args.paths, args.pattern, args.replacement,
                            use_regex=args.regex, dry_run=args.dry_run,
                            ignore_case=args.ignore_case)
    for old, new in res.mapping:
        prefix = "[dry] " if args.dry_run else ""
        print(f"{prefix}{old}  ->  {new}")
    ok(f"{res.changed} renamed, {res.skipped} skipped"
       + (" (dry run)" if args.dry_run else ""))
    return 0


def cmd_hash(args) -> int:
    results = hashutil.hash_paths(args.paths, algorithm=args.algo,
                                  recursive=args.recursive)
    for r in results:
        print(f"{r.digest}  {human_size(r.size):>10}  {r.path}")
    return 0


def cmd_manifest(args) -> int:
    out = hashutil.create_manifest(args.root, algorithm=args.algo,
                                   include_hidden=args.hidden, out=args.out)
    ok(f"Manifest written: {out}")
    return 0


def cmd_verify(args) -> int:
    rep = hashutil.verify_manifest(args.manifest, detect_extra=args.extra)
    info(f"Checked : {rep.checked}")
    ok(f"OK      : {rep.ok}")
    if rep.modified:
        error(f"Modified: {len(rep.modified)}")
        for m in rep.modified:
            print(f"  ~ {m}")
    if rep.missing:
        error(f"Missing : {len(rep.missing)}")
        for m in rep.missing:
            print(f"  - {m}")
    if rep.extra:
        warn(f"Extra   : {len(rep.extra)}")
        for m in rep.extra:
            print(f"  + {m}")
    return 0 if not (rep.modified or rep.missing) else 2


def cmd_compare(args) -> int:
    r = hashutil.compare_files(args.a, args.b, algorithm=args.algo)
    if r.identical:
        ok("Files are identical")
    else:
        warn("Files differ")
    print(f"  size A/B     : {human_size(r.size_a)} / {human_size(r.size_b)}")
    print(f"  {args.algo} A     : {r.digest_a}")
    print(f"  {args.algo} B     : {r.digest_b}")
    if r.first_diff is not None:
        print(f"  first diff at: byte {r.first_diff}")
    return 0 if r.identical else 1


def cmd_dupes(args) -> int:
    groups = hashutil.find_duplicates(args.root, algorithm=args.algo,
                                      min_size=search.parse_size(args.min_size)
                                      if args.min_size else 1,
                                      include_hidden=args.hidden)
    if not groups:
        ok("No duplicates found.")
        return 0
    wasted = 0
    for g in groups:
        wasted += g.wasted
        heading(f"--- {human_size(g.size)} x {len(g.files)}  ({g.digest[:16]}...) ---")
        for f in g.files:
            print(f"  {f}")
    ok(f"{len(groups)} duplicate group(s), reclaimable: {human_size(wasted)}")
    return 0


def cmd_du(args) -> int:
    rep = analytics.disk_usage(args.root, include_hidden=not args.no_hidden)
    print(f"Files: {rep.files}   Dirs: {rep.dirs}   Links: {rep.links}")
    print(f"Total: {human_size(rep.total_bytes)}")
    heading("By extension:")
    for ext, count, size in analytics.extension_summary(args.root)[: args.top]:
        print(f"  {ext:<12} {count:>6} file(s)  {human_size(size):>12}")
    heading("By top-level entry:")
    for name, size in sorted(rep.by_dir.items(), key=lambda kv: kv[1], reverse=True)[: args.top]:
        print(f"  {name:<24} {human_size(size):>12}")
    return 0


def cmd_largest(args) -> int:
    for e in analytics.largest_files(args.root, limit=args.limit, include_hidden=args.hidden):
        print(f"{human_size(e.size):>12}  {human_time(e.mtime)}  {e.rel}")
    return 0


def cmd_newest(args) -> int:
    for e in analytics.newest_files(args.root, limit=args.limit, include_hidden=args.hidden):
        print(f"{human_time(e.mtime)}  {human_size(e.size):>12}  {e.rel}")
    return 0


def cmd_oldest(args) -> int:
    for e in analytics.oldest_files(args.root, limit=args.limit, include_hidden=args.hidden):
        print(f"{human_time(e.mtime)}  {human_size(e.size):>12}  {e.rel}")
    return 0


def cmd_empty(args) -> int:
    rep = analytics.find_empty(args.root, include_hidden=args.hidden)
    heading(f"Empty files ({len(rep.empty_files)}):")
    for p in rep.empty_files:
        print(f"  {p}")
    heading(f"Empty directories ({len(rep.empty_dirs)}):")
    for p in rep.empty_dirs:
        print(f"  {p}")
    return 0


def cmd_broken(args) -> int:
    links = analytics.find_broken_links(args.root)
    if not links:
        ok("No broken symlinks.")
        return 0
    for p in links:
        print(f"  {p}")
    warn(f"{len(links)} broken symlink(s)")
    return 1


def cmd_ext(args) -> int:
    for ext, count, size in analytics.extension_summary(args.root, include_hidden=args.hidden):
        print(f"{ext:<12} {count:>6}  {human_size(size):>12}")
    return 0


def cmd_summary(args) -> int:
    s = analytics.summarize(args.root, include_hidden=args.hidden)
    heading(f"Summary of {s.root}")
    print(f"  files={s.files}  dirs={s.dirs}  links={s.links}  total={human_size(s.total_bytes)}")
    print(f"  empty files={s.empty_files}  empty dirs={s.empty_dirs}  broken links={s.broken_links}")
    heading("Top extensions:")
    for ext, count, size in s.top_ext:
        print(f"  {ext:<12} {count:>6}  {human_size(size):>12}")
    heading("Largest files:")
    for e in s.largest:
        print(f"  {human_size(e.size):>12}  {e.rel}")
    heading("Newest files:")
    for e in s.newest:
        print(f"  {human_time(e.mtime)}  {e.rel}")
    return 0


def cmd_arc_create(args) -> int:
    out = archive.create_archive(args.sources, args.output, fmt=args.format,
                                 base_dir=args.base_dir)
    ok(f"Created archive: {out} ({human_size(out.stat().st_size)})")
    return 0


def cmd_arc_extract(args) -> int:
    dest = archive.extract_archive(args.archive, args.dest, members=args.member)
    ok(f"Extracted to: {dest}")
    return 0


def cmd_arc_list(args) -> int:
    items = archive.list_archive(args.archive)
    total = 0
    for it in items:
        total += it["size"]
        kind = "d" if it["is_dir"] else "-"
        print(f"{kind} {human_size(it['size']):>10}  {it['date']}  {it['name']}")
    ok(f"{len(items)} entries, uncompressed {human_size(total)}")
    return 0


def cmd_gzip(args) -> int:
    if args.decompress:
        out = archive.gunzip_file(args.path, keep=args.keep)
        ok(f"Decompressed -> {out}")
    else:
        out = archive.gzip_file(args.path, keep=args.keep)
        ok(f"Compressed -> {out}")
    return 0


def cmd_split(args) -> int:
    parts = archive.split_file(args.path, search.parse_size(args.size), out_dir=args.out_dir)
    for p in parts:
        print(f"  {p}  ({human_size(p.stat().st_size)})")
    ok(f"Split into {len(parts)} part(s)")
    return 0


def cmd_merge(args) -> int:
    out = archive.merge_files(args.parts, args.output)
    ok(f"Merged -> {out} ({human_size(out.stat().st_size)})")
    return 0


def cmd_sync(args) -> int:
    rep = archive.sync_tree(args.src, args.dest, delete=args.delete, dry_run=args.dry_run)
    prefix = "[dry] " if args.dry_run else ""
    ok(f"{prefix}copied={rep.copied} updated={rep.updated} "
       f"skipped={rep.skipped} removed={rep.removed}")
    return 0


def cmd_chmod(args) -> int:
    n = security.chmod(args.path, args.mode, recursive=args.recursive)
    ok(f"Changed permissions on {n} path(s)")
    return 0


def cmd_perms(args) -> int:
    for e in security.list_permissions(args.path, recursive=args.recursive):
        print(f"{e.mode}  {e.octal:>6}  {e.path}")
    return 0


def cmd_worldwritable(args) -> int:
    hits = security.find_world_writable(args.root)
    if not hits:
        ok("No world-writable entries.")
        return 0
    for p in hits:
        print(f"  {p}")
    warn(f"{len(hits)} world-writable entries")
    return 1


def cmd_shred(args) -> int:
    n = security.secure_delete(args.path, passes=args.passes)
    ok(f"Shredded {args.path} ({human_size(n)} overwritten)")
    return 0


def cmd_encrypt(args) -> int:
    pwd = _get_password(args, confirm=True)
    out = security.encrypt_file(args.path, pwd, out=args.out,
                                remove_source=args.remove_source)
    ok(f"Encrypted -> {out}")
    return 0


def cmd_decrypt(args) -> int:
    pwd = _get_password(args)
    out = security.decrypt_file(args.path, pwd, out=args.out,
                                remove_source=args.remove_source)
    ok(f"Decrypted -> {out}")
    return 0


def cmd_wc(args) -> int:
    st = core.word_count(args.path, encoding=args.encoding)
    print(f"lines={st.lines}  words={st.words}  chars={st.chars}  bytes={st.bytes}")
    return 0


def cmd_replace(args) -> int:
    n = core.replace_in_file(args.path, args.old, args.new, regex=args.regex,
                             ignore_case=args.ignore_case, dry_run=args.dry_run)
    ok(f"{n} replacement(s)" + (" (dry run)" if args.dry_run else ""))
    return 0


def cmd_enc(args) -> int:
    out = core.convert_encoding(args.path, to_encoding=args.to,
                                from_encoding=args.from_enc,
                                in_place=not args.out, out_path=args.out)
    ok(f"Converted -> {out}")
    return 0


def cmd_symlink(args) -> int:
    p = core.make_symlink(args.target, args.link)
    ok(f"Created symlink {p} -> {args.target}")
    return 0


def cmd_readlink(args) -> int:
    print(core.read_symlink(args.path))
    return 0


def cmd_stat(args) -> int:
    data = core.stat_info(args.path)
    if args.json:
        print(json.dumps(data, indent=2, default=str))
    else:
        _print_kv(data)
    return 0


def cmd_types(args) -> int:
    p = utils.ensure_exists(utils.resolve(args.path))
    print(f"path       : {p}")
    print(f"mime       : {utils.sniff_type(p)}")
    print(f"binary     : {utils.is_binary(p)}")
    return 0


def cmd_free(args) -> int:
    total, used, free = utils.free_space(utils.resolve(args.path))
    print(f"total={human_size(total)}  used={human_size(used)}  free={human_size(free)}")
    return 0


# --------------------------------------------------------------------------- #
# Argument parser
# --------------------------------------------------------------------------- #

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="fileforge - a portable local file-system toolkit for Linux, Windows and macOS.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-V", "--version", action="version",
                        version=f"{PROG} {VERSION}  ({utils.platform_name()})")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    # ls
    p = sub.add_parser("ls", help="list directory contents")
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("-l", "--long", action="store_true")
    p.add_argument("-a", "--hidden", action="store_true")
    p.add_argument("--sort", choices=["name", "size", "time", "ext"], default="name")
    p.set_defaults(func=cmd_ls)

    # tree
    p = sub.add_parser("tree", help="print an ASCII directory tree")
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("-L", "--depth", type=int, default=None)
    p.add_argument("-a", "--hidden", action="store_true")
    p.add_argument("--no-size", action="store_true")
    p.set_defaults(func=cmd_tree)

    # find
    p = sub.add_parser("find", help="search files by name/size/date/content")
    p.add_argument("root", nargs="?", default=".")
    p.add_argument("-name", "--name", action="append", metavar="GLOB")
    p.add_argument("--regex", metavar="REGEX")
    p.add_argument("--ext", action="append", metavar="EXT")
    p.add_argument("--min-size", metavar="SIZE")
    p.add_argument("--max-size", metavar="SIZE")
    p.add_argument("--newer", metavar="DUR", help="modified within e.g. 7d")
    p.add_argument("--older", metavar="DUR", help="modified before e.g. 30d")
    p.add_argument("--content", metavar="TEXT")
    p.add_argument("--files-only", action="store_true")
    p.add_argument("--dirs-only", action="store_true")
    p.add_argument("--empty", action="store_true")
    p.add_argument("-a", "--hidden", action="store_true")
    p.add_argument("--depth", type=int, default=None)
    p.add_argument("--follow", action="store_true")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("-l", "--long", action="store_true")
    p.set_defaults(func=cmd_find)

    # grep
    p = sub.add_parser("grep", help="search text inside files")
    p.add_argument("pattern")
    p.add_argument("paths", nargs="*", default=["."])
    p.add_argument("--regex", action="store_true")
    p.add_argument("-s", "--case-sensitive", action="store_true")
    p.add_argument("--include", action="append", metavar="GLOB")
    p.add_argument("--exclude", action="append", metavar="GLOB")
    p.add_argument("--no-recursive", action="store_true")
    p.add_argument("--max", type=int, default=0)
    p.set_defaults(func=cmd_grep)

    # cat
    p = sub.add_parser("cat", help="print a text file")
    p.add_argument("path")
    p.add_argument("-n", "--number", action="store_true")
    p.add_argument("--encoding", default="utf-8")
    p.add_argument("--head", type=int)
    p.add_argument("--tail", type=int)
    p.set_defaults(func=cmd_cat)

    # write
    p = sub.add_parser("write", help="write or append text to a file")
    p.add_argument("path")
    p.add_argument("-c", "--content")
    p.add_argument("-f", "--file", help="read content from this file")
    p.add_argument("--stdin", action="store_true")
    p.add_argument("-a", "--append", action="store_true")
    p.add_argument("--encoding", default="utf-8")
    p.add_argument("--newline", action="store_true", help="force LF newlines")
    p.set_defaults(func=cmd_write)

    # touch
    p = sub.add_parser("touch", help="create an empty file / update mtime")
    p.add_argument("path")
    p.set_defaults(func=cmd_touch)

    # cp
    p = sub.add_parser("cp", help="copy a file or directory")
    p.add_argument("src")
    p.add_argument("dest")
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--no-recursive", action="store_true")
    p.add_argument("--no-preserve", action="store_true")
    p.set_defaults(func=cmd_cp)

    # mv
    p = sub.add_parser("mv", help="move or rename")
    p.add_argument("src")
    p.add_argument("dest")
    p.add_argument("--overwrite", action="store_true")
    p.set_defaults(func=cmd_mv)

    # rm
    p = sub.add_parser("rm", help="remove a file or directory")
    p.add_argument("path")
    p.add_argument("-r", "--recursive", action="store_true")
    p.add_argument("-f", "--force", action="store_true")
    p.add_argument("--secure", action="store_true", help="overwrite before deleting")
    p.add_argument("--passes", type=int, default=3)
    p.set_defaults(func=cmd_rm)

    # mkdir
    p = sub.add_parser("mkdir", help="create a directory")
    p.add_argument("path")
    p.add_argument("--no-parents", action="store_true")
    p.add_argument("--exist-ok", action="store_true")
    p.set_defaults(func=cmd_mkdir)

    # rename
    p = sub.add_parser("rename", help="rename a single path")
    p.add_argument("path")
    p.add_argument("new_name")
    p.set_defaults(func=cmd_rename)

    # rename-batch
    p = sub.add_parser("rename-batch", help="rename many files with a pattern")
    p.add_argument("paths", nargs="+")
    p.add_argument("--pattern", required=True)
    p.add_argument("--replacement", required=True)
    p.add_argument("--regex", action="store_true")
    p.add_argument("-i", "--ignore-case", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_rename_batch)

    # hash
    p = sub.add_parser("hash", help="compute checksums")
    p.add_argument("paths", nargs="+")
    p.add_argument("-a", "--algo", default="sha256", choices=list(utils.HASH_ALGOS))
    p.add_argument("-r", "--recursive", action="store_true")
    p.set_defaults(func=cmd_hash)

    # manifest
    p = sub.add_parser("manifest", help="create a checksum manifest")
    p.add_argument("root")
    p.add_argument("-a", "--algo", default="sha256", choices=list(utils.HASH_ALGOS))
    p.add_argument("-a-hidden", dest="hidden", action="store_true")
    p.add_argument("-o", "--out")
    p.set_defaults(func=cmd_manifest)

    # verify
    p = sub.add_parser("verify", help="verify a checksum manifest")
    p.add_argument("manifest")
    p.add_argument("--extra", action="store_true", help="also report new files")
    p.set_defaults(func=cmd_verify)

    # compare
    p = sub.add_parser("compare", help="compare two files")
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("-a", "--algo", dest="algo", default="sha256")
    p.set_defaults(func=cmd_compare)

    # dupes
    p = sub.add_parser("dupes", help="find duplicate files")
    p.add_argument("root")
    p.add_argument("-a", "--algo", dest="algo", default="sha256")
    p.add_argument("--min-size", metavar="SIZE")
    p.add_argument("--hidden", action="store_true")
    p.set_defaults(func=cmd_dupes)

    # du
    p = sub.add_parser("du", help="disk usage breakdown")
    p.add_argument("root", nargs="?", default=".")
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--no-hidden", action="store_true")
    p.set_defaults(func=cmd_du)

    # largest / newest / oldest
    p = sub.add_parser("largest", help="list largest files")
    p.add_argument("root", nargs="?", default=".")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--hidden", action="store_true")
    p.set_defaults(func=cmd_largest)

    p = sub.add_parser("newest", help="list most recently modified files")
    p.add_argument("root", nargs="?", default=".")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--hidden", action="store_true")
    p.set_defaults(func=cmd_newest)

    p = sub.add_parser("oldest", help="list least recently modified files")
    p.add_argument("root", nargs="?", default=".")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--hidden", action="store_true")
    p.set_defaults(func=cmd_oldest)

    # empty / broken / ext / summary
    p = sub.add_parser("empty", help="find empty files and directories")
    p.add_argument("root", nargs="?", default=".")
    p.add_argument("--hidden", action="store_true")
    p.set_defaults(func=cmd_empty)

    p = sub.add_parser("broken-links", help="find broken symbolic links")
    p.add_argument("root", nargs="?", default=".")
    p.set_defaults(func=cmd_broken)

    p = sub.add_parser("ext-summary", help="extension based summary")
    p.add_argument("root", nargs="?", default=".")
    p.add_argument("--hidden", action="store_true")
    p.set_defaults(func=cmd_ext)

    p = sub.add_parser("summary", help="full tree summary report")
    p.add_argument("root", nargs="?", default=".")
    p.add_argument("--hidden", action="store_true")
    p.set_defaults(func=cmd_summary)

    # archive
    p = sub.add_parser("archive-create", help="create a zip/tar archive")
    p.add_argument("output")
    p.add_argument("sources", nargs="+")
    p.add_argument("--format", choices=["zip", "tar"], default=None)
    p.add_argument("--base-dir")
    p.set_defaults(func=cmd_arc_create)

    p = sub.add_parser("archive-extract", help="extract an archive")
    p.add_argument("archive")
    p.add_argument("-d", "--dest", default=".")
    p.add_argument("--member", action="append")
    p.set_defaults(func=cmd_arc_extract)

    p = sub.add_parser("archive-list", help="list archive contents")
    p.add_argument("archive")
    p.set_defaults(func=cmd_arc_list)

    p = sub.add_parser("gzip", help="gzip / gunzip a single file")
    p.add_argument("path")
    p.add_argument("-d", "--decompress", action="store_true")
    p.add_argument("-k", "--keep", action="store_true")
    p.set_defaults(func=cmd_gzip)

    p = sub.add_parser("split", help="split a file into parts")
    p.add_argument("path")
    p.add_argument("--size", required=True, help="e.g. 10M")
    p.add_argument("--out-dir")
    p.set_defaults(func=cmd_split)

    p = sub.add_parser("merge", help="merge split parts back together")
    p.add_argument("output")
    p.add_argument("parts", nargs="+")
    p.set_defaults(func=cmd_merge)

    p = sub.add_parser("sync", help="incremental directory mirror")
    p.add_argument("src")
    p.add_argument("dest")
    p.add_argument("--delete", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_sync)

    # permissions
    p = sub.add_parser("chmod", help="change permissions")
    p.add_argument("path")
    p.add_argument("mode")
    p.add_argument("-r", "--recursive", action="store_true")
    p.set_defaults(func=cmd_chmod)

    p = sub.add_parser("perms", help="show permissions")
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("-r", "--recursive", action="store_true")
    p.set_defaults(func=cmd_perms)

    p = sub.add_parser("world-writable", help="audit world-writable entries")
    p.add_argument("root", nargs="?", default=".")
    p.set_defaults(func=cmd_worldwritable)

    p = sub.add_parser("shred", help="securely delete a file")
    p.add_argument("path")
    p.add_argument("--passes", type=int, default=3)
    p.set_defaults(func=cmd_shred)

    # crypto
    p = sub.add_parser("encrypt", help="encrypt a file (custom cipher)")
    p.add_argument("path")
    p.add_argument("-p", "--password")
    p.add_argument("-o", "--out")
    p.add_argument("--remove-source", action="store_true")
    p.set_defaults(func=cmd_encrypt)

    p = sub.add_parser("decrypt", help="decrypt a .ffenc file")
    p.add_argument("path")
    p.add_argument("-p", "--password")
    p.add_argument("-o", "--out")
    p.add_argument("--remove-source", action="store_true")
    p.set_defaults(func=cmd_decrypt)

    # text
    p = sub.add_parser("wc", help="count lines / words / chars")
    p.add_argument("path")
    p.add_argument("--encoding", default="utf-8")
    p.set_defaults(func=cmd_wc)

    p = sub.add_parser("replace", help="replace text inside a file")
    p.add_argument("path")
    p.add_argument("old")
    p.add_argument("new")
    p.add_argument("--regex", action="store_true")
    p.add_argument("-i", "--ignore-case", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_replace)

    p = sub.add_parser("convert-encoding", help="transcode a text file")
    p.add_argument("path")
    p.add_argument("--to", required=True)
    p.add_argument("--from", dest="from_enc", default="utf-8")
    p.add_argument("-o", "--out")
    p.set_defaults(func=cmd_enc)

    # links
    p = sub.add_parser("symlink", help="create a symbolic link")
    p.add_argument("target")
    p.add_argument("link")
    p.set_defaults(func=cmd_symlink)

    p = sub.add_parser("readlink", help="show a symlink target")
    p.add_argument("path")
    p.set_defaults(func=cmd_readlink)

    # stat / type / free
    p = sub.add_parser("stat", help="show detailed information about a path")
    p.add_argument("path")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_stat)

    p = sub.add_parser("filetype", help="detect a file's MIME type")
    p.add_argument("path")
    p.set_defaults(func=cmd_types)

    p = sub.add_parser("free", help="show free space on a volume")
    p.add_argument("path", nargs="?", default=".")
    p.set_defaults(func=cmd_free)

    # shell
    p = sub.add_parser("shell", help="start the interactive shell")
    p.set_defaults(func=lambda a: __import__("fileforge.repl", fromlist=["run"]).run())

    # gui
    p = sub.add_parser("gui", help="launch the graphical interface (Tkinter)")
    p.set_defaults(func=lambda a: __import__("fileforge.gui", fromlist=["main"]).main())

    return parser


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    try:
        return int(args.func(args) or 0)
    except FileForgeError as exc:
        error(str(exc))
        return 2
    except KeyboardInterrupt:
        warn("Interrupted.")
        return 130
    except PermissionError as exc:
        error(f"Permission denied: {exc}")
        return 3
    except OSError as exc:
        error(f"OS error: {exc}")
        return 4


# ---------------------------------------------------------------------------
# Unified command surface.
#
# The original argparse entry point is preserved as ``main_classic``.  ``main``
# now routes every command through :mod:`fileforge.dispatch`, so *all* entry
# points -- the `fileforge` console script, `python -m fileforge` and the
# repository launcher -- accept the complete command set including
# `tree`, `treemap`, `drives`, `computer` and `computerui`.
# ---------------------------------------------------------------------------
main_classic = main


def main(argv: Optional[Sequence[str]] = None) -> int:  # noqa: F811
    """Dispatch every fileforge command (classic CLI + live tree + This PC)."""
    try:
        from .dispatch import main as _dispatch_main
    except ImportError:  # pragma: no cover - dispatcher missing
        return main_classic(argv)
    return _dispatch_main(argv)


if __name__ == "__main__":
    sys.exit(main())
