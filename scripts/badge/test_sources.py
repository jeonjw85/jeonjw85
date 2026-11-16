"""Tests for metric sources.

Network is stubbed: each test supplies canned payloads so the suite stays
hermetic and fast.
"""
import json
from datetime import date, timedelta

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


def docker_page(counts, next_url=None):
    return json.dumps(
        {
            "count": len(counts),
            "next": next_url,
            "results": [
                {"name": f"image-{index}", "pull_count": count}
                for index, count in enumerate(counts)
            ],
        }
    )


def crates_list(names, next_page=None):
    return json.dumps(
        {"crates": [{"name": name} for name in names], "meta": {"next_page": next_page}}
    )


def crate_downloads(days):
    """Build a ``version_downloads`` payload from ``{days_ago: downloads}``."""
    today = date.today()
    return json.dumps(
        {
            "version_downloads": [
                {
                    "version": 1,
                    "date": (today - timedelta(days=ago)).isoformat(),
                    "downloads": downloads,
                }
                for ago, downloads in days.items()
            ]
        }
    )


def payloads(stars=72, pypi=211, npm=475, docker=(111,), crates=(("e2ee-kit", {0: 28}),)):
    mapping = {
        "api.github.com/repos/jeonjw85/kenfold": gh_stars(stars),
        "pypistats.org/api/packages/aij/recent": pypi_recent(pypi),
        "api.npmjs.org/downloads/point/": npm_total(npm),
        "hub.docker.com/v2/repositories/jeonjw/": docker_page(list(docker)),
        "user_id=": crates_list([name for name, _ in crates]),
    }
    for name, days in crates:
        mapping[f"crates/{name}/downloads"] = crate_downloads(days)
    return mapping


def test_collect_reads_every_source():
    http = FakeHttp(payloads())
    values = sources.collect(http)

    assert values["kenfold_stars"] == 72
    assert values["pkg_month"] == 239
    assert values["docker_pulls"] == 111
    assert values["npm_total"] == 950


def test_collect_sums_pypi_and_crates_downloads():
    http = FakeHttp(payloads(pypi=200, crates=(("e2ee-kit", {0: 40, 3: 2}),)))
    values = sources.collect(http)

    assert values["pkg_month"] == 242


def test_crates_window_ignores_downloads_older_than_the_pypi_month():
    http = FakeHttp(payloads(pypi=0, crates=(("e2ee-kit", {0: 5, 29: 7, 30: 100}),)))
    values = sources.collect(http)

    assert values["pkg_month"] == 12


def test_crates_total_sums_every_owned_crate_across_pages():
    http = FakeHttp(
        {
            "page=2": crates_list(["second"]),
            "page=1": crates_list(["first"], next_page=2),
            "crates/first/downloads": crate_downloads({0: 10}),
            "crates/second/downloads": crate_downloads({0: 3}),
            **payloads(pypi=1),
        }
    )
    values = sources.collect(http)

    assert values["pkg_month"] == 14
    assert any("page=2" in url for url in http.calls)


def test_collect_keeps_previous_value_when_a_source_fails():
    mapping = payloads()
    mapping["pypistats.org/api/packages/aij/recent"] = ('{"error":"boom"}', 503)
    http = FakeHttp(mapping)
    previous = {"pkg_month": 240}
    warnings = []
    values = sources.collect(http, previous=previous, warn=warnings.append)

    assert values["pkg_month"] == 240
    assert any("pkg" in w for w in warnings)


def test_collect_raises_when_a_source_fails_and_no_previous_value():
    mapping = payloads()
    mapping["api.github.com/repos/jeonjw85/kenfold"] = (gh_stars(72), 500)
    http = FakeHttp(mapping)

    with pytest.raises(sources.SourceError):
        sources.collect(http)


def test_collect_rejects_non_integer_payloads():
    mapping = payloads()
    mapping["api.github.com/repos/jeonjw85/kenfold"] = json.dumps({"stargazers_count": "72"})
    http = FakeHttp(mapping)

    with pytest.raises(sources.SourceError):
        sources.collect(http)


def test_collect_rejects_a_crates_payload_without_version_downloads():
    mapping = payloads()
    mapping["crates/e2ee-kit/downloads"] = json.dumps({"errors": []})
    http = FakeHttp(mapping)

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
        "pkg_month": 239,
        "npm_total": 780,
        "docker_pulls": 111,
    }
    segs = sources.segments_from(values)
    assert [s.label for s in segs] == [
        "KENFOLD",
        "PY+RS",
        "NPM",
        "DOCKER",
    ]
    assert segs[0].value == "★72"
    assert segs[1].value == "239/MO"
    assert segs[2].value == "780"
    assert segs[3].value == "111"
    assert segs[0].accent is not None


def test_segments_do_not_include_third_party_membership():
    values = {
        "kenfold_stars": 72,
        "pkg_month": 239,
        "npm_total": 780,
        "docker_pulls": 111,
    }
    labels = [s.label for s in sources.segments_from(values)]
    assert "XERJ" not in labels


def test_collect_falls_back_to_committed_npm_total_when_one_package_fails():
    mapping = payloads()
    mapping["api.npmjs.org/downloads/point/"] = ('{"error":"boom"}', 503)
    http = FakeHttp(mapping)
    warnings = []
    values = sources.collect(http, previous={"npm_total": 780}, warn=warnings.append)

    assert values["npm_total"] == 780
    assert any("npm" in w for w in warnings)


def test_collect_falls_back_to_committed_pkg_total_when_crates_fail():
    mapping = payloads()
    mapping["crates/e2ee-kit/downloads"] = ('{"error":"boom"}', 503)
    http = FakeHttp(mapping)
    warnings = []
    values = sources.collect(http, previous={"pkg_month": 300}, warn=warnings.append)

    assert values["pkg_month"] == 300
    assert any("pkg" in w for w in warnings)


def test_read_previous_recovers_the_combined_totals():
    svg = (
        '<svg><g aria-label="KENFOLD ★72 | PY+RS 239/MO | NPM 781 | '
        'DOCKER 111"></g></svg>'
    )
    previous = sources.read_previous(svg)
    assert previous["npm_total"] == 781
    assert previous["kenfold_stars"] == 72
    assert previous["pkg_month"] == 239
    assert previous["docker_pulls"] == 111


def test_docker_total_sums_pull_counts_across_public_images():
    http = FakeHttp(payloads(docker=(100, 12)))
    values = sources.collect(http)

    assert values["docker_pulls"] == 112


def test_docker_total_follows_pagination():
    second_page = "https://hub.docker.com/v2/repositories/jeonjw/?page=2&page_size=100"
    mapping = {"page=2": docker_page([12, 3])}
    mapping.update(payloads())
    mapping["hub.docker.com/v2/repositories/jeonjw/"] = docker_page([100], next_url=second_page)
    http = FakeHttp(mapping)
    values = sources.collect(http)

    assert values["docker_pulls"] == 115


def test_docker_total_rejects_a_payload_without_results():
    mapping = payloads()
    mapping["hub.docker.com/v2/repositories/jeonjw/"] = json.dumps({"count": 0})
    http = FakeHttp(mapping)

    with pytest.raises(sources.SourceError):
        sources.collect(http)
