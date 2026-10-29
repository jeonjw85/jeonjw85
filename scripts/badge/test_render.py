"""Tests for badge rendering and value formatting.

Run with: python -m pytest scripts/badge -q
"""
import re

import pytest

from scripts.badge import render


class FakeFace:
    """Stand-in for a font face; every glyph is 6 units wide at 1px size."""

    def __init__(self, advance=6.0):
        self.advance = advance

    def layout(self, text, size, tracking=0.0):
        parts = []
        x = 0.0
        for _ in text:
            parts.append((x, "M0 0H1V1H0Z"))
            x += self.advance * size + tracking
        width = x - tracking if text else 0.0
        return parts, width


def segments():
    return [
        render.Segment("KENFOLD", "★72", "#6bb3e8"),
        render.Segment("AIJ", "211/MO", None),
        render.Segment("NPM", "781", None),
    ]


def svg_width(svg):
    return float(re.search(r'width="([\d.]+)"', svg).group(1))


def test_strip_width_is_fixed_to_match_the_stats_card():
    face = FakeFace()
    svg = render.build_strip(segments(), face, face)
    assert svg_width(svg) == pytest.approx(render.WIDTH, abs=0.01)
    assert render.WIDTH == 450


def test_narrow_content_is_centred_instead_of_left_padded():
    face = FakeFace()
    svg = render.build_strip([render.Segment("AIJ", "1")], face, face)
    assert svg_width(svg) == pytest.approx(render.WIDTH, abs=0.01)

    first_text_x = min(
        float(x) for x in re.findall(r'translate\(([\d.]+) ', svg)
    )
    assert first_text_x > render.PAD


def test_oversized_numbers_shrink_instead_of_widening_the_strip():
    face = FakeFace(advance=30.0)
    segments_ = [render.Segment("KENFOLD", "★100K"), render.Segment("AIJ", "100K/MO")]
    svg = render.build_strip(segments_, face, face)
    assert svg_width(svg) == pytest.approx(render.WIDTH, abs=0.01)

    scales = [float(s) for s in re.findall(r'scale\(([\d.]+) ', svg)]
    assert scales and all(scale <= render.LABEL_SIZE for scale in scales)


def test_strip_does_not_repeat_the_profile_name():
    face = FakeFace()
    svg = render.build_strip(segments(), face, face)
    assert "JEONGWAN" not in svg
    assert "SEOUL" not in svg


def test_type_is_large_enough_to_read_at_1x():
    assert render.LABEL_SIZE >= 11
    assert render.VALUE_SIZE >= 13
    assert render.VALUE_SIZE > render.LABEL_SIZE


def test_strip_stays_compact():
    assert render.HEIGHT <= 32


def _contrast(foreground, background):
    def luminance(colour):
        channels = [int(colour.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4)]
        linear = [
            c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    high, low = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def test_text_stays_readable_on_the_dark_page():
    for colour in (render.LABEL_COLOR, render.VALUE_NEUTRAL, render.DIVIDER):
        assert _contrast(colour, render.BG) >= 1.5, colour
    assert _contrast(render.LABEL_COLOR, render.BG) >= 4.5
    assert _contrast(render.VALUE_NEUTRAL, render.BG) >= 4.5


def test_strip_has_no_outline_or_gradient():
    face = FakeFace()
    svg = render.build_strip(segments(), face, face)
    assert "stroke" not in svg
    assert 'id="line"' not in svg
    assert "linearGradient" not in svg
    assert not hasattr(render, "LINE_FROM")
    assert not hasattr(render, "BG_MID")


def test_background_is_one_flat_colour():
    assert render.BG == "#0d1117"


def test_strip_svg_is_valid_root_and_has_accessible_label():
    face = FakeFace()
    svg = render.build_strip(segments(), face, face)
    assert svg.startswith("<svg xmlns=")
    assert svg.rstrip().endswith("</svg>")
    assert 'role="img"' in svg
    label = re.search(r'aria-label="([^"]*)"', svg).group(1)
    assert "KENFOLD ★72" in label
    assert "AIJ 211/MO" in label


def test_strip_uses_accent_for_highlighted_values_and_neutral_otherwise():
    face = FakeFace()
    svg = render.build_strip(segments(), face, face)
    assert svg.count('fill="#6bb3e8"') >= 1
    assert f'fill="{render.VALUE_NEUTRAL}"' in svg
    assert 'fill="#a78bfa"' not in svg


def test_strip_has_single_gradient_ids_and_no_duplicate_ids():
    face = FakeFace()
    svg = render.build_strip(segments(), face, face)
    ids = re.findall(r'id="([^"]+)"', svg)
    assert len(ids) == len(set(ids))


def test_strip_height_matches_declared_constant():
    face = FakeFace()
    svg = render.build_strip(segments(), face, face)
    assert f'height="{render.HEIGHT}"' in svg


@pytest.mark.parametrize(
    "value,expected",
    [
        (0, "0"),
        (7, "7"),
        (72, "72"),
        (999, "999"),
        (1000, "1K"),
        (1200, "1.2K"),
        (9999, "10K"),
        (11770, "12K"),
        (100000, "100K"),
    ],
)
def test_compact_number(value, expected):
    assert render.compact_number(value) == expected


def test_compact_number_rejects_negative():
    with pytest.raises(ValueError):
        render.compact_number(-1)
