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
# Fixed to the stats card's width so the README column lines up instead of the
# strip stretching to the viewport.
WIDTH = 450.0
HEIGHT = 32
PAD = 16
GAP = 12           # space on each side of a divider
DIVIDER_W = 1
RADIUS = 6.5

LABEL_SIZE = 11.0
LABEL_TRACKING = 0.66
LABEL_VALUE_GAP = 5.0
VALUE_SIZE = 13.0
VALUE_TRACKING = 0.09
DIVIDER_H = HEIGHT * 0.5

# --- colour ------------------------------------------------------------------
# GitHub's dark page colour: the strip has no panel of its own.
BG = "#0d1117"
DIVIDER = "#ffffff1c"
LABEL_COLOR = "#7d8590"
VALUE_NEUTRAL = "#e6edf3"


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


def _layout(
    segments: list[Segment],
    label_face: Face,
    value_face: Face,
    label_size: float,
    value_size: float,
    gap: float,
) -> list[dict]:
    label_tracking = label_size * (LABEL_TRACKING / LABEL_SIZE)
    value_tracking = value_size * (VALUE_TRACKING / VALUE_SIZE)
    label_gap = value_size * (LABEL_VALUE_GAP / VALUE_SIZE)

    laid = []
    for seg in segments:
        lp, lw = label_face.layout(seg.label, label_size, label_tracking)
        vp, vw = value_face.layout(seg.value, value_size, value_tracking)
        laid.append(dict(seg=seg, lp=lp, lw=lw, vp=vp, vw=vw, gap=label_gap))
    return laid


def _content_width(laid: list[dict], gap: float) -> float:
    return sum(item["lw"] + item["gap"] + item["vw"] for item in laid) + (
        len(laid) - 1
    ) * (gap + DIVIDER_W + gap)


def build_strip(
    segments: list[Segment],
    label_face: Face,
    value_face: Face,
) -> str:
    if not segments:
        raise ValueError("at least one segment is required")

    # Oversized numbers shrink the type rather than widening the strip.
    label_size, value_size, gap = LABEL_SIZE, VALUE_SIZE, GAP
    laid = _layout(segments, label_face, value_face, label_size, value_size, gap)
    content = _content_width(laid, gap)
    limit = WIDTH - PAD * 2
    if content > limit:
        scale = limit / content
        label_size *= scale
        value_size *= scale
        gap *= scale
        laid = _layout(segments, label_face, value_face, label_size, value_size, gap)
        content = _content_width(laid, gap)

    baseline = HEIGHT / 2 + label_size * 0.375
    side = max(PAD, (WIDTH - content) / 2)

    label = " | ".join(f"{s.label} {s.value}" for s in segments)
    out: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH:.0f}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH:.2f} {HEIGHT}" role="img" aria-label="{escape(label)}">',
        f'<rect width="{WIDTH:.2f}" height="{HEIGHT}" rx="{RADIUS}" fill="{BG}"/>',
    ]

    x = side
    for index, item in enumerate(laid):
        seg: Segment = item["seg"]
        if index:
            x += gap
            out.append(
                f'<rect x="{x:.2f}" y="{(HEIGHT - DIVIDER_H) / 2:.2f}" width="{DIVIDER_W}" height="{DIVIDER_H}" '
                f'fill="{DIVIDER}"/>'
            )
            x += DIVIDER_W + gap
        out.append(f'<g fill="{LABEL_COLOR}">{_glyphs(item["lp"], x, baseline, label_size)}</g>')
        x += item["lw"] + item["gap"]
        color = seg.accent or VALUE_NEUTRAL
        out.append(f'<g fill="{color}">{_glyphs(item["vp"], x, baseline, value_size)}</g>')
        x += item["vw"]

    out.append("</svg>")
    return "\n".join(out)
