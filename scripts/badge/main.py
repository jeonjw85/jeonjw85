"""Regenerate the README badge strip from live project metrics.

Usage:
    python -m scripts.badge.main            # write badges/header.svg
    python -m scripts.badge.main --check    # fail if the file is out of date

The committed strip doubles as the fallback cache: when a metric source is down
the previous value is read back out of it, so a transient API failure never
blanks a number.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import font, render, sources

REPO_ROOT = Path(__file__).resolve().parents[2]
BADGE_DIR = REPO_ROOT / "badges"
DEFAULT_OUTPUT = BADGE_DIR / "header.svg"


def generate(output: Path, http=None, warn=None) -> str:
    http = http or sources.UrllibHttp()
    warn = warn or (lambda message: print(f"warning: {message}", file=sys.stderr))

    previous = {}
    if output.exists():
        previous = sources.read_previous(output.read_text())

    values = sources.collect(http, previous=previous, warn=warn)
    segments = sources.segments_from(values)
    svg = render.build_strip(segments, font.load("Medium"), font.load("SemiBold"))
    return svg


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the committed SVG differs from freshly generated output",
    )
    args = parser.parse_args(argv)

    svg = generate(args.output)

    if args.check:
        if not args.output.exists():
            print(f"{args.output} is missing; run `python -m scripts.badge.main`", file=sys.stderr)
            return 1
        if args.output.read_text() != svg:
            print(
                f"{args.output} is out of date; run `python -m scripts.badge.main`",
                file=sys.stderr,
            )
            return 1
        print("badge is up to date")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(svg)
    print(f"wrote {args.output} ({len(svg)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
