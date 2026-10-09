"""
fileforge
=========

A portable, dependency-free local file-system toolkit for Linux, Windows
and macOS. It bundles file / directory management, search, integrity
checking, archives, permissions, security helpers and tree analytics
behind a single command line (and an interactive shell).

Quick start
-----------
    python fileforge.py --help
    python fileforge.py ls -l .
    python fileforge.py find . --ext .py --newer 7d
    python fileforge.py summary .
    python fileforge.py shell
"""

from __future__ import annotations

from .utils import FileForgeError

__version__ = "2.1.0"
__all__ = ["FileForgeError", "__version__", "main"]


def main(argv=None):
    """Console-script entry point (delegates to :mod:`fileforge.dispatch`)."""
    from .dispatch import main as _main
    return _main(argv)
