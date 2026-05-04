"""Minimal CLI entry point for DiscourseKit."""

from __future__ import annotations

import sys


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        from discoursekit import __version__

        print(f"DiscourseKit {__version__}")
        return
    print("DiscourseKit CLI - use --version to check version. Full CLI available in Step 4.")


if __name__ == "__main__":
    main()
