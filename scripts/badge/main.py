"""Regenerate the README badge SVGs from live project metrics.

Usage:
    python -m scripts.badge.main            # write both badges
    python -m scripts.badge.main --check    # fail if a file is out of date

Writes ``badges/header.svg`` (the metrics strip) and ``badges/xerj.svg`` (the
contributor credit, drawn to the same spec so the two read as one block).

The committed strip doubles as the fallback cache: when a metric source is down
the previous value is read back out of it, so a transient API failure never
blanks a number.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import font, render, sources, xerj

REPO_ROOT = Path(__file__).resolve().parents[2]
BADGE_DIR = REPO_ROOT / "badges"
DEFAULT_OUTPUT = BADGE_DIR / "header.svg"
XERJ_OUTPUT = BADGE_DIR / "xerj.svg"


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


def generate_xerj() -> str:
    return xerj.build_xerj_badge(font.load("Medium"), font.load("SemiBold"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if a committed SVG differs from freshly generated output",
    )
    args = parser.parse_args(argv)

    outputs = {
        args.output: generate(args.output),
        # the XERJ badge has no live metrics, so it is always regenerated as-is
        XERJ_OUTPUT: generate_xerj(),
    }

    if args.check:
        stale = []
        for path, svg in outputs.items():
            if not path.exists():
                stale.append(f"{path} is missing")
            elif path.read_text() != svg:
                stale.append(f"{path} is out of date")
        if stale:
            for line in stale:
                print(f"{line}; run `python -m scripts.badge.main`", file=sys.stderr)
            return 1
        print("badges are up to date")
        return 0

    for path, svg in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(svg)
        print(f"wrote {path} ({len(svg)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
