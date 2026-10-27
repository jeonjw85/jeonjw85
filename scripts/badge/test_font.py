"""Tests for the outline font loader."""
import pytest

from scripts.badge import font


class _StubGlyphs:
    def __getitem__(self, name):
        class Glyph:
            def draw(self, pen):
                pen.moveTo((0, 0))
                pen.lineTo((100, 0))

        return Glyph()


def make_face(cmap_chars="AB ", advance=1000):
    face = object.__new__(font.OutlineFace)
    face._glyph_set = _StubGlyphs()
    face._cmap = {ord(c): "g" for c in cmap_chars}
    face._hmtx = {"g": (advance, 0)}
    face._upm = 1000
    face._path_cache = {}
    face.path = font.Path("stub.ttf")
    return face


def test_missing_font_raises_helpful_error(tmp_path):
    with pytest.raises(font.FontError) as exc:
        font.load(tmp_path / "nope.ttf")
    assert "pretendard" in str(exc.value).lower()


def test_layout_returns_one_entry_per_character():
    face = make_face()
    parts, width = face.layout("AB", 10)
    assert len(parts) == 2
    assert width == pytest.approx(20)


def test_layout_applies_tracking_between_glyphs_only():
    face = make_face()
    _, width = face.layout("AB", 10, tracking=2)
    assert width == pytest.approx(22)


def test_layout_of_empty_text_is_zero():
    face = make_face()
    assert face.layout("", 10) == ([], 0.0)


def test_layout_rejects_unsupported_characters():
    face = make_face()
    with pytest.raises(font.FontError, match="missing glyph"):
        face.layout("A★", 10)


def test_paths_are_cached_per_glyph():
    face = make_face()
    face.layout("A", 10)
    first = dict(face._path_cache)
    face.layout("A", 12)
    assert face._path_cache == first
