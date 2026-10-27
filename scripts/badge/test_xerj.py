"""Tests for the XERJ contributor badge renderer."""
import re

import pytest

from scripts.badge import render, xerj


class FakeFace:
    def __init__(self, advance=6.0):
        self.advance = advance

    def layout(self, text, size, tracking=0.0):
        parts = []
        x = 0.0
        for _ in text:
            parts.append((x, "M0 0H1V1H0Z"))
            x += self.advance * size + tracking
        return parts, (x - tracking if text else 0.0)


def build(label="XERJ CORPUS HUB", value="CONTRIBUTOR"):
    face = FakeFace()
    return xerj.build_xerj_badge(face, face, label=label, value=value)


def test_badge_matches_the_strip_height_and_radius():
    svg = build()
    assert f'height="{render.HEIGHT}"' in svg
    assert f'rx="{render.RADIUS}"' in svg


def test_badge_uses_the_strips_type_sizes():
    face = FakeFace()
    svg = xerj.build_xerj_badge(face, face)
    _, lw = face.layout("XERJ CORPUS HUB", xerj.LABEL_SIZE, xerj.LABEL_TRACKING)
    _, vw = face.layout("CONTRIBUTOR", xerj.VALUE_SIZE, xerj.VALUE_TRACKING)
    expected = lw + xerj.PAD * 2 + vw + xerj.PAD * 2
    width = float(re.search(r'width="([\d.]+)"', svg).group(1))
    assert width == pytest.approx(round(expected), abs=0.01)


def test_badge_keeps_the_upstream_accent():
    svg = build()
    assert xerj.XERJ_RIGHT_BG in svg


def test_badge_neutral_tones_come_from_the_strip():
    """A warm grey made the credit look pasted on next to the cool strip."""
    assert xerj.LABEL_COLOR == render.LABEL_COLOR
    assert xerj.XERJ_LEFT_BG == render.BG_TOP


def test_badge_has_a_single_clip_and_no_duplicate_ids():
    svg = build()
    ids = re.findall(r'id="([^"]+)"', svg)
    assert len(ids) == len(set(ids))


def test_badge_declares_an_accessible_label():
    svg = build()
    label = re.search(r'aria-label="([^"]*)"', svg).group(1)
    assert label == "Xerj Corpus Hub: contributor"


def test_badge_is_wellformed():
    svg = build()
    assert svg.startswith("<svg xmlns=")
    assert svg.rstrip().endswith("</svg>")
    assert 'role="img"' in svg
