"""Outline font loading for the badge strip.

The strip ships text as paths, so the generator needs the Pretendard outlines at
build time only. Fetch them with ``python -m scripts.badge.font --fetch`` which
reads the pinned npm tarball; nothing font-related is committed except the
rendered SVG.
"""
from __future__ import annotations

import argparse
import io
import os
import tarfile
import urllib.request
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

PRETENDARD_VERSION = "1.3.9"
PRETENDARD_TARBALL = (
    f"https://registry.npmjs.org/pretendard/-/pretendard-{PRETENDARD_VERSION}.tgz"
)
CACHE_DIR = Path(__file__).resolve().parent / ".font-cache"
WEIGHTS = {"Medium": "Pretendard-Medium.ttf", "SemiBold": "Pretendard-SemiBold.ttf"}


class FontError(RuntimeError):
    """A font file is missing or cannot satisfy a layout request."""


class OutlineFace:
    """A font face that turns text into SVG path data."""

    def __init__(self, path: os.PathLike | str):
        self.path = Path(path)
        if not self.path.exists():
            raise FontError(
                f"font not found: {self.path}. Run `python -m scripts.badge.font --fetch` "
                "to download the Pretendard outlines."
            )
        font = TTFont(self.path)
        self._glyph_set = font.getGlyphSet()
        self._cmap = font.getBestCmap()
        self._hmtx = font["hmtx"]
        self._upm = font["head"].unitsPerEm
        self._path_cache: dict[str, str] = {}

    def _path_for(self, glyph_name: str) -> str:
        cached = self._path_cache.get(glyph_name)
        if cached is not None:
            return cached
        # three decimals keeps the SVG small without visible deviation
        pen = SVGPathPen(self._glyph_set, ntos=lambda v: f"{v:.3f}".rstrip("0").rstrip(".") or "0")
        # normalise to a 1-em box so callers scale by the pixel size alone
        transform = TransformPen(pen, (1 / self._upm, 0, 0, 1 / self._upm, 0, 0))
        self._glyph_set[glyph_name].draw(transform)
        self._path_cache[glyph_name] = pen.getCommands()
        return self._path_cache[glyph_name]

    def layout(self, text: str, size: float, tracking: float = 0.0):
        if not text:
            return [], 0.0
        scale = size / self._upm
        parts: list[tuple[float, str]] = []
        x = 0.0
        for character in text:
            glyph_name = self._cmap.get(ord(character))
            if glyph_name is None:
                raise FontError(
                    f"missing glyph for {character!r} in {self.path.name}; "
                    "extend the subset or drop the character"
                )
            parts.append((x, self._path_for(glyph_name)))
            x += self._hmtx[glyph_name][0] * scale + tracking
        return parts, x - tracking


def cache_path(weight: str) -> Path:
    return CACHE_DIR / WEIGHTS[weight]


def load(weight_or_path) -> OutlineFace:
    """Load a face by weight name (``"Medium"``) or by explicit path."""
    if isinstance(weight_or_path, (str, os.PathLike)) and str(weight_or_path) in WEIGHTS:
        return OutlineFace(cache_path(str(weight_or_path)))
    return OutlineFace(weight_or_path)


def fetch(destination: Path = CACHE_DIR, opener=urllib.request.urlopen) -> list[Path]:
    """Download the pinned Pretendard tarball and extract the two used weights."""
    destination.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        PRETENDARD_TARBALL, headers={"User-Agent": "jeonjw85-profile-badges"}
    )
    with opener(request) as response:
        payload = response.read()

    written = []
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        for weight, filename in WEIGHTS.items():
            member_name = f"package/dist/public/static/alternative/{filename}"
            member = archive.extractfile(member_name)
            if member is None:
                raise FontError(f"{member_name} missing from {PRETENDARD_TARBALL}")
            target = destination / filename
            target.write_bytes(member.read())
            written.append(target)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="download the Pretendard outlines")
    parser.add_argument("--dest", type=Path, default=CACHE_DIR, help="cache directory")
    args = parser.parse_args(argv)

    if args.fetch:
        for path in fetch(args.dest):
            print(f"wrote {path} ({path.stat().st_size} bytes)")
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
