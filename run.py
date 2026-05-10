#!/usr/bin/env python3
"""CLI entrypoint. Usage: python run.py --window {morning,midday,evening} [--dry-run]"""
import argparse
import logging
import sys

from news_digest.config import WINDOWS
from news_digest.digest import run


def main() -> int:
    parser = argparse.ArgumentParser(description="Personal news digest")
    parser.add_argument("--window", required=True, choices=sorted(WINDOWS.keys()))
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch and filter only — no Claude or Telegram calls")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    return run(args.window, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
