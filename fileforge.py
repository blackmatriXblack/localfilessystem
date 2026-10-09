#!/usr/bin/env python3
"""
fileforge - single-file launcher
================================

Runs the portable file-system toolkit from the repository root.

    python fileforge.py <command> [options]
    python fileforge.py shell
    python fileforge.py --help

Works on Linux, Windows and macOS with no third-party dependencies.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Make the package importable no matter where the script is invoked from.
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# Best effort: force UTF-8 output on Windows terminals.
if os.name == "nt":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass


def _bootstrap() -> int:
    try:
        from fileforge.cli import main
    except ImportError as exc:  # pragma: no cover
        print(f"fileforge: failed to import package: {exc}", file=sys.stderr)
        return 1
    return main(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(_bootstrap())
