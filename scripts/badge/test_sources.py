"""Tests for metric sources.

Network is stubbed: each test supplies canned payloads so the suite stays
hermetic and fast.
"""
import json

import pytest

from scripts.badge import sources


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status = status

    def json(self):
        return json.loads(self._payload)


class FakeHttp:
    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = []

    def get(self, url, timeout=15):
        self.calls.append(url)
        for fragment, payload in self.mapping.items():
            if fragment in url:
                status = payload[1] if isinstance(payload, tuple) else 200
                body = payload[0] if isinstance(payload, tuple) else payload
                return FakeResponse(body, status)
        raise AssertionError(f"unexpected url: {url}")


def gh_stars(count):
    return json.dumps({"stargazers_count": count})


def npm_total(count):
    return json.dumps({"downloads": count})


def pypi_recent(count):
    return json.dumps({"data": {"last_month": count}})


def docker_pulls(count):
    return json.dumps({"pull_count": count})


def test_collect_reads_every_source():
    http = FakeHttp(
        {
            "api.github.com/repos/jeonjw85/kenfold": gh_stars(72),
            "pypistats.org/api/packages/aij/recent": pypi_recent(211),
            "api.npmjs.org/downloads/point/": npm_total(475),
            "hub.docker.com/v2/repositories/jeonjw/rapid-photo-web/": docker_pulls(111),
        }
    )
    values = sources.collect(http)

    assert values["kenfold_stars"] == 72
    assert values["aij_month"] == 211
    assert values["rapid_photo_web_pulls"] == 111
    assert values["npm_totals"]["grassmaker"] == 475
    assert values["npm_totals"]["refpin"] == 475


def test_collect_keeps_previous_value_when_a_source_fails():
    http = FakeHttp(
        {
            "api.github.com/repos/jeonjw85/kenfold": (gh_stars(72), 200),
            "pypistats.org/api/packages/aij/recent": ('{"error":"boom"}', 503),
            "api.npmjs.org/downloads/point/": npm_total(475),
            "hub.docker.com/v2/repositories/jeonjw/rapid-photo-web/": docker_pulls(111),
        }
    )
    previous = {"aij_month": 190}
    warnings = []
    values = sources.collect(http, previous=previous, warn=warnings.append)

    assert values["aij_month"] == 190
    assert any("aij" in w for w in warnings)


def test_collect_raises_when_a_source_fails_and_no_previous_value():
    http = FakeHttp(
        {
            "api.github.com/repos/jeonjw85/kenfold": (gh_stars(72), 500),
            "pypistats.org/api/packages/aij/recent": pypi_recent(211),
            "api.npmjs.org/downloads/point/": npm_total(475),
            "hub.docker.com/v2/repositories/jeonjw/rapid-photo-web/": docker_pulls(111),
        }
    )
    with pytest.raises(sources.SourceError):
        sources.collect(http)


def test_collect_rejects_non_integer_payloads():
    http = FakeHttp(
        {
            "api.github.com/repos/jeonjw85/kenfold": json.dumps({"stargazers_count": "72"}),
            "pypistats.org/api/packages/aij/recent": pypi_recent(211),
            "api.npmjs.org/downloads/point/": npm_total(475),
            "hub.docker.com/v2/repositories/jeonjw/rapid-photo-web/": docker_pulls(111),
        }
    )
    with pytest.raises(sources.SourceError):
        sources.collect(http)


def test_urllib_http_exposes_json_from_the_response_body():
    class Raw:
        status = 200

        def read(self):
            return b'{"stargazers_count": 72}'

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    captured = {}

    def fake_urlopen(request, timeout=15):
        captured["url"] = request.full_url
        captured["ua"] = request.get_header("User-agent")
        return Raw()

    http = sources.UrllibHttp()
    original = sources.urllib.request.urlopen
    sources.urllib.request.urlopen = fake_urlopen
    try:
        response = http.get("https://api.github.com/repos/jeonjw85/kenfold")
    finally:
        sources.urllib.request.urlopen = original

    assert response.status == 200
    assert response.json() == {"stargazers_count": 72}
    assert captured["ua"]
    assert captured["url"].startswith("https://api.github.com/")


def test_segments_from_values_orders_projects_as_declared():
    values = {
        "kenfold_stars": 72,
        "aij_month": 211,
        "npm_totals": {"grassmaker": 475, "refpin": 305},
        "rapid_photo_web_pulls": 111,
    }
    segs = sources.segments_from(values)
    assert [s.label for s in segs] == [
        "KENFOLD",
        "AIJ",
        "GRASSMAKER",
        "REFPIN",
        "RAPID-PHOTO-WEB",
    ]
    assert segs[0].value == "★72"
    assert segs[1].value == "211/MO"
    assert segs[0].accent is not None


def test_segments_do_not_include_third_party_membership():
    """XERJ is rendered by its own service and stays a separate badge."""
    values = {
        "kenfold_stars": 72,
        "aij_month": 211,
        "npm_totals": {"grassmaker": 475, "refpin": 305},
        "rapid_photo_web_pulls": 111,
    }
    labels = [s.label for s in sources.segments_from(values)]
    assert "XERJ" not in labels
