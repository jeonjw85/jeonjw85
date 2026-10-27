"""Render the profile badge strip as a self-contained SVG.

Text is converted to outlines so the result needs no font at display time and
renders identically everywhere (GitHub strips ``<text>`` styling and refuses to
load webfonts inside inline SVG). The generator only needs the Pretendard
outlines, which are derived from the ``pretendard`` npm tarball at build time.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol
from xml.sax.saxutils import escape

# --- geometry (px) -----------------------------------------------------------
# Tuned so the five metrics fill a profile README's ~888px column at 1x: the
# strip is the first thing on the page, so it must not read as fine print.
HEIGHT = 45
PAD = 22.5
GAP = 21.25        # space on each side of a divider
DIVIDER_W = 1.25
RADIUS = 8.75

LABEL_SIZE = 15.0
LABEL_TRACKING = 0.9
LABEL_VALUE_GAP = 6.25
VALUE_SIZE = 17.5
VALUE_TRACKING = 0.125
BASELINE = HEIGHT / 2 + 6.25
DIVIDER_H = HEIGHT * 0.5

# --- colour ------------------------------------------------------------------
BG_TOP = "#121e2c"
BG_BOTTOM = "#0a1420"
BORDER = "#ffffff21"
DIVIDER = "#ffffff24"
LABEL_COLOR = "#8b9cb2"
VALUE_NEUTRAL = "#e9eff7"
LINE_FROM = "#4a9bd8"
LINE_TO = "#7c3aed"


class Face(Protocol):
    """A laid-out font face: text to outlines plus advance widths.

    ``layout`` returns ``[(x_offset, path_d), ...]`` where ``path_d`` is
    normalised to a 1-em box, plus the total advance in pixels at ``size``.
    """

    def layout(self, text: str, size: float, tracking: float = 0.0) -> tuple[list[tuple[float, str]], float]:
        """Return ``[(x, path_d), ...]`` at the origin plus the total advance."""


@dataclass(frozen=True)
class Segment:
    label: str
    value: str
    accent: str | None = None


def compact_number(value: int) -> str:
    """Format a count in at most 4 characters: 999, 1K, 1.2K, 12K, 100K."""
    if value < 0:
        raise ValueError("value must not be negative")
    if value < 1000:
        return str(value)
    if value < 10_000:
        scaled = value / 1000
        text = f"{scaled:.1f}".rstrip("0").rstrip(".")
        return f"{text}K"
    return f"{round(value / 1000)}K"


def _glyphs(parts: Iterable[tuple[float, str]], x: float, baseline: float, scale: float) -> str:
    return "".join(
        f'<g transform="translate({x + gx:.2f} {baseline:.2f}) scale({scale:.5f} {-scale:.5f})">'
        f'<path d="{d}"/></g>'
        for gx, d in parts
    )


def build_strip(
    segments: list[Segment],
    label_face: Face,
    value_face: Face,
) -> str:
    if not segments:
        raise ValueError("at least one segment is required")

    laid: list[dict] = []
    for seg in segments:
        lp, lw = label_face.layout(seg.label, LABEL_SIZE, LABEL_TRACKING)
        vp, vw = value_face.layout(seg.value, VALUE_SIZE, VALUE_TRACKING)
        laid.append(
            dict(seg=seg, lp=lp, lw=lw, vp=vp, vw=vw, width=lw + LABEL_VALUE_GAP + vw)
        )

    seg_total = sum(item["width"] for item in laid)
    between = GAP + DIVIDER_W + GAP
    width = PAD + seg_total + (len(laid) - 1) * between + PAD

    label = " | ".join(f"{s.label} {s.value}" for s in segments)
    out: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{HEIGHT}" '
        f'viewBox="0 0 {width:.2f} {HEIGHT}" role="img" aria-label="{escape(label)}">',
        "<defs>",
        '<linearGradient id="bg" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="{BG_TOP}"/>'
        f'<stop offset="0.5" stop-color="#0c1723"/>'
        f'<stop offset="1" stop-color="{BG_BOTTOM}"/></linearGradient>',
        '<linearGradient id="line" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="{LINE_FROM}" stop-opacity="0"/>'
        f'<stop offset="0.25" stop-color="{LINE_FROM}" stop-opacity="0.6"/>'
        f'<stop offset="0.7" stop-color="{LINE_TO}" stop-opacity="0.5"/>'
        f'<stop offset="1" stop-color="{LINE_TO}" stop-opacity="0"/></linearGradient>',
        "</defs>",
        f'<rect width="{width:.2f}" height="{HEIGHT}" rx="{RADIUS}" fill="url(#bg)"/>',
        f'<rect x="0.5" y="0.5" width="{width - 1:.2f}" height="{HEIGHT - 1}" '
        f'rx="{RADIUS - 0.5:.1f}" fill="none" stroke="{BORDER}" stroke-width="1"/>',
        f'<rect x="{RADIUS}" y="{HEIGHT - 1}" width="{width - RADIUS * 2:.2f}" height="1" fill="url(#line)"/>',
    ]

    x = PAD
    for index, item in enumerate(laid):
        seg: Segment = item["seg"]
        if index:
            x += GAP
            out.append(
                f'<rect x="{x:.2f}" y="{(HEIGHT - DIVIDER_H) / 2:.2f}" width="{DIVIDER_W}" height="{DIVIDER_H}" '
                f'fill="{DIVIDER}"/>'
            )
            x += DIVIDER_W + GAP
        out.append(f'<g fill="{LABEL_COLOR}">{_glyphs(item["lp"], x, BASELINE, LABEL_SIZE)}</g>')
        x += item["lw"] + LABEL_VALUE_GAP
        color = seg.accent or VALUE_NEUTRAL
        out.append(f'<g fill="{color}">{_glyphs(item["vp"], x, BASELINE, VALUE_SIZE)}</g>')
        x += item["vw"]

    out.append("</svg>")
    return "\n".join(out)
