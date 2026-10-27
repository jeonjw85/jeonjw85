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
        render.Segment("XERJ", "CONTRIBUTOR", "#a78bfa"),
    ]


def svg_width(svg):
    return float(re.search(r'width="([\d.]+)"', svg).group(1))


def test_strip_width_counts_padding_gaps_and_dividers():
    face = FakeFace()
    svg = render.build_strip(segments(), face, face)

    seg_w = 0.0
    for s in segments():
        _, lw = face.layout(s.label, render.LABEL_SIZE, render.LABEL_TRACKING)
        _, vw = face.layout(s.value, render.VALUE_SIZE, render.VALUE_TRACKING)
        seg_w += lw + render.LABEL_VALUE_GAP + vw

    n = len(segments())
    expected = (
        render.PAD
        + seg_w
        + (n - 1) * (render.GAP + render.DIVIDER_W + render.GAP)
        + render.PAD
    )
    assert svg_width(svg) == pytest.approx(round(expected), abs=0.01)


def test_strip_does_not_repeat_the_profile_name():
    """The profile header already shows the name; spending width on it twice
    made the metrics read as fine print."""
    face = FakeFace()
    svg = render.build_strip(segments(), face, face)
    assert "JEONGWAN" not in svg
    assert "SEOUL" not in svg


def test_type_is_large_enough_to_read_at_1x():
    """Guards the regression that started this: labels had shrunk to 9.5px."""
    assert render.LABEL_SIZE >= 12
    assert render.VALUE_SIZE >= 13
    assert render.VALUE_SIZE > render.LABEL_SIZE


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
    assert svg.count('fill="#a78bfa"') >= 1
    assert f'fill="{render.VALUE_NEUTRAL}"' in svg


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
