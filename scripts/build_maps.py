#!/usr/bin/env python3
"""Build data/elections.json and data/elections.embed.js from elections/*.txt."""

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent


def main() -> None:
    sys.path.insert(0, str(SCRIPT_DIR))
    from result_compiler import update_all

    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else REPO_ROOT
    update_all(root)


if __name__ == "__main__":
    main()
