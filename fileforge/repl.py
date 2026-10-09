"""
fileforge.repl
==============

A small interactive shell on top of the CLI. It keeps a current working
directory, supports `cd`, `pwd`, `history`, `!<shell command>`, `help`
and forwards everything else to the argparse dispatcher.

Windows users: run `python fileforge.py shell` (this module is invoked
through the package, so relative imports work).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from . import utils
from .cli import build_parser, main as cli_main
from .utils import FileForgeError, error, heading, ok, paint, warn, _Style

BANNER = r"""
 _____.__.__             _____
_|__|  |  |  |   ____   / ____/___  ________  ____ ______   ____
|  |  |  |  | _/ __ \ / /_  / __ \/ ___/ _ \/ __ `/ ___/ _ \_/ __ \
|  |  |_|  |_|\  ___// __/ / /_/ / /  /  __/ /_/ / /  /  __/  ___/
|__|____/____/ \___/ /_/    \____/_/   \___/\__, /_/   \___/\___/
                                           /____/
"""


def _shell_split(line: str) -> List[str]:
    """
    Split a command line, honouring single/double quotes while keeping
    backslashes intact (important for Windows paths).
    """
    tokens: List[str] = []
    buf: List[str] = []
    quote: Optional[str] = None
    for ch in line:
        if quote:
            if ch == quote:
                quote = None
            else:
                buf.append(ch)
        elif ch in ("'", '"'):
            quote = ch
        elif ch.isspace():
            if buf:
                tokens.append("".join(buf))
                buf = []
        else:
            buf.append(ch)
    if buf:
        tokens.append("".join(buf))
    return tokens


HELP_TEXT = """\
Available commands (run any command with -h for details):

  Navigation      : cd, pwd, ls, tree, stat, filetype, free
  Files           : cat, write, touch, cp, mv, rm, mkdir, symlink, readlink
  Search          : find, grep
  Rename          : rename, rename-batch
  Integrity       : hash, manifest, verify, compare, dupes
  Analytics       : du, largest, newest, oldest, empty, broken-links,
                    ext-summary, summary
  Archives        : archive-create, archive-extract, archive-list, gzip,
                    split, merge, sync
  Permissions     : chmod, perms, world-writable
  Security        : shred, encrypt, decrypt
  Text            : wc, replace, convert-encoding

Shell builtins  : help, exit / quit, history, clear, !<cmd> (run shell cmd)
"""


def run(initial_dir: Optional[str] = None) -> int:
    cwd = utils.resolve(initial_dir or os.getcwd())
    parser = build_parser()
    history: List[str] = []

    print(paint(BANNER, _Style.CYAN))
    print(paint(f" fileforge shell {utils.platform_name()}  |  type 'help' or 'exit'", _Style.BOLD))
    print(paint(f" cwd: {cwd}", _Style.DIM))
    print()

    while True:
        try:
            raw = input(paint("ff", _Style.GREEN, _Style.BOLD) +
                        paint(":", _Style.DIM) +
                        paint(f"{_short(cwd)}", _Style.CYAN) + "> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break

        line = raw.strip()
        if not line:
            continue
        history.append(line)

        # shell passthrough
        if line.startswith("!"):
            subprocess.call(line[1:], shell=True, cwd=str(cwd))
            continue

        tokens = _shell_split(line)
        if not tokens:
            continue
        cmd, rest = tokens[0].lower(), tokens[1:]

        if cmd in ("exit", "quit", "q"):
            break
        if cmd == "help":
            print(HELP_TEXT)
            continue
        if cmd == "clear":
            os.system("cls" if utils.IS_WINDOWS else "clear")
            continue
        if cmd == "history":
            for i, h in enumerate(history, 1):
                print(f"{i:>4}  {h}")
            continue
        if cmd == "cd":
            cwd = _do_cd(cwd, rest)
            continue
        if cmd == "pwd":
            print(cwd)
            continue

        # Patch os.getcwd for the duration of the command so relative
        # paths resolve against the shell's cwd.
        old = os.getcwd()
        try:
            os.chdir(cwd)
            code = cli_main([cmd] + rest)
        except FileForgeError as exc:
            error(str(exc))
        except SystemExit:
            pass
        except Exception as exc:  # noqa: BLE001 - keep the shell alive
            error(f"{type(exc).__name__}: {exc}")
        finally:
            try:
                os.chdir(old)
            except OSError:
                pass

    print(paint("bye.", _Style.DIM))
    return 0


def _do_cd(cwd: Path, args: List[str]) -> Path:
    if not args:
        target = Path.home()
    elif args[0] == "-":
        target = Path(os.environ.get("FF_OLDPWD", str(cwd)))
    else:
        target = utils.resolve(args[0])
    if not target.is_absolute():
        target = (cwd / target)
    if not target.exists() or not target.is_dir():
        warn(f"No such directory: {target}")
        return cwd
    os.environ["FF_OLDPWD"] = str(cwd)
    return target.resolve()


def _short(path: Path, width: int = 40) -> str:
    s = str(path)
    if len(s) <= width:
        return s
    return "..." + s[-(width - 3):]
