"""Tests for the regenerate/check entrypoint."""
import json

import pytest

from scripts.badge import font, main, sources


@pytest.fixture
def faces(monkeypatch):
    class Face:
        def layout(self, text, size, tracking=0.0):
            return [(0.0, "M0 0H1V1H0Z")] * len(text), 6.0 * size * len(text)

    monkeypatch.setattr(font, "load", lambda weight: Face())


def canned_http(monkeypatch, stars=72, month=211, npm=475, pulls=111):
    payloads = {
        "api.github.com": {"stargazers_count": stars},
        "pypistats.org": {"data": {"last_month": month}},
        "api.npmjs.org": {"downloads": npm},
        "hub.docker.com": {"pull_count": pulls},
    }

    class Response:
        status = 200

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return json.loads(json.dumps(self.payload))

    class Http:
        def get(self, url, timeout=15):
            for fragment, payload in payloads.items():
                if fragment in url:
                    return Response(payload)
            raise AssertionError(url)

    return Http()


def test_generate_writes_svg_with_metrics(monkeypatch, tmp_path, faces):
    out = tmp_path / "header.svg"
    svg = main.generate(out, http=canned_http(monkeypatch))
    assert svg.startswith("<svg")
    assert "KENFOLD" in (svg.split("aria-label=")[1])
    assert "★72" in svg or "72" in svg


def test_check_reports_stale_file(monkeypatch, tmp_path, faces):
    out = tmp_path / "header.svg"
    out.write_text("<svg>stale</svg>")
    monkeypatch.setattr(main, "generate", lambda output, **_: "<svg>fresh</svg>")
    assert main.main(["--output", str(out), "--check"]) == 1


def test_check_reports_up_to_date_file(monkeypatch, tmp_path, faces):
    out = tmp_path / "header.svg"
    out.write_text("<svg>same</svg>")
    monkeypatch.setattr(main, "generate", lambda output, **_: "<svg>same</svg>")
    assert main.main(["--output", str(out), "--check"]) == 0


def test_generate_reuses_previous_values_when_source_fails(monkeypatch, tmp_path, faces):
    out = tmp_path / "header.svg"
    out.write_text(main.generate(out, http=canned_http(monkeypatch, stars=50)))
    base = canned_http(monkeypatch)

    class FlakyHttp:
        def get(self, url, timeout=15):
            if "api.github.com" in url:
                raise sources.URLError("down")
            return base.get(url, timeout)

    warnings = []
    svg = main.generate(out, http=FlakyHttp(), warn=warnings.append)
    assert "★50" in svg
    assert warnings
