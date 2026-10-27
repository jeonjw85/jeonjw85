"""Render the XERJ contributor badge in the strip's own visual language.

The upstream badge at hub.xerj.org is a stock shields.io template: Verdana
11px, 20px tall, 3px radius. Next to a 45px strip with Pretendard outlines and
an 8.75px radius it reads as a sticker from a different design system, and no
amount of scaling fixes the mismatch. Drawing it with the same primitives keeps
the credit, its link, and its distinct colour while making the block cohesive.
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from .render import (
    BASELINE,
    BORDER,
    HEIGHT,
    PAD,
    RADIUS,
    Face,
    _glyphs,
)

# XERJ's accent colour is kept so the credit stays recognisable; the neutral
# tones come from the strip so the two badges read as one block.
XERJ_LEFT_BG = "#121e2c"
XERJ_RIGHT_BG = "#7c3aed"
LABEL_COLOR = "#8b9cb2"
VALUE_COLOR = "#ffffff"

LABEL_SIZE = 15.0
LABEL_TRACKING = 0.9
LABEL_VALUE_GAP = 6.25
VALUE_SIZE = 17.5
VALUE_TRACKING = 0.125


def build_xerj_badge(
    label_face: Face,
    value_face: Face,
    *,
    label: str = "XERJ CORPUS HUB",
    value: str = "CONTRIBUTOR",
) -> str:
    lp, lw = label_face.layout(label, LABEL_SIZE, LABEL_TRACKING)
    vp, vw = value_face.layout(value, VALUE_SIZE, VALUE_TRACKING)

    left_w = lw + PAD * 2
    right_w = vw + PAD * 2
    width = left_w + right_w

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{HEIGHT}" '
        f'viewBox="0 0 {width:.2f} {HEIGHT}" role="img" '
        f'aria-label="{escape(label.title())}: {escape(value.lower())}">',
        "<defs>",
        f'<clipPath id="xerj"><rect width="{width:.2f}" height="{HEIGHT}" rx="{RADIUS}"/></clipPath>',
        "</defs>",
        '<g clip-path="url(#xerj)">',
        f'<rect width="{left_w:.2f}" height="{HEIGHT}" fill="{XERJ_LEFT_BG}"/>',
        f'<rect x="{left_w:.2f}" width="{right_w:.2f}" height="{HEIGHT}" fill="{XERJ_RIGHT_BG}"/>',
        "</g>",
        f'<rect x="0.5" y="0.5" width="{width - 1:.2f}" height="{HEIGHT - 1}" '
        f'rx="{RADIUS - 0.5:.1f}" fill="none" stroke="{BORDER}" stroke-width="1"/>',
    ]

    out.append(f'<g fill="{LABEL_COLOR}">{_glyphs(lp, PAD, BASELINE, LABEL_SIZE)}</g>')
    out.append(
        f'<g fill="{VALUE_COLOR}">{_glyphs(vp, left_w + PAD, BASELINE, VALUE_SIZE)}</g>'
    )
    out.append("</svg>")
    return "\n".join(out)
