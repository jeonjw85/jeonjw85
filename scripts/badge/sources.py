"""Read live project metrics for the profile badge strip.

Every source is read over plain HTTPS with ``urllib`` so the generator has no
third-party dependencies. If a source is unavailable the previous committed
value is reused and a warning is emitted; a missing value with no fallback is a
hard error, because silently dropping a metric would misrepresent the profile.

Run with: python -m pytest scripts/badge -q
"""
from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
from typing import Callable, Protocol
from urllib.error import URLError

from .render import Segment

NPM_TOTAL_SINCE = "2015-01-10"
GITHUB_USER = "jeonjw85"
DOCKER_IMAGE = "jeonjw/rapid-photo-web"

SEGMENT_ACCENT = "#6bb3e8"

# Project order is a presentation decision: strongest signal first.
NPM_PACKAGES = ("grassmaker", "refpin")


class SourceError(RuntimeError):
    """A metric could not be read and no fallback was available."""


class HttpResponse(Protocol):
    status: int

    def json(self): ...


class Http(Protocol):
    def get(self, url: str, timeout: int = 15) -> HttpResponse: ...


@dataclass
class UrllibResponse:
    """Wrap ``urlopen``'s response with the ``.json()`` the sources expect."""

    _response: object
    body: bytes
    status: int

    def json(self):
        return json.loads(self.body)


@dataclass
class UrllibHttp:
    user_agent: str = "jeonjw85-profile-badges"

    def get(self, url: str, timeout: int = 15) -> UrllibResponse:
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            return UrllibResponse(response, body, response.status)


def _int_field(payload, key: str) -> int:
    value = payload.get(key) if isinstance(payload, dict) else None
    if isinstance(value, bool) or not isinstance(value, int):
        raise SourceError(f"expected integer at {key!r}, got {value!r}")
    return value


def _fetch(http: Http, url: str) -> dict:
    try:
        response = http.get(url)
    except (URLError, OSError) as exc:
        raise SourceError(f"{url}: {exc}") from exc
    status = getattr(response, "status", 200)
    if status >= 400:
        raise SourceError(f"{url}: HTTP {status}")
    try:
        return response.json()
    except ValueError as exc:
        raise SourceError(f"{url}: invalid JSON") from exc


def _github_stars(http: Http) -> int:
    payload = _fetch(http, f"https://api.github.com/repos/{GITHUB_USER}/kenfold")
    return _int_field(payload, "stargazers_count")


def _pypi_monthly(http: Http) -> int:
    payload = _fetch(http, "https://pypistats.org/api/packages/aij/recent")
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise SourceError("pypistats: missing data object")
    return _int_field(data, "last_month")


def _npm_total(http: Http, package: str) -> int:
    payload = _fetch(
        http,
        f"https://api.npmjs.org/downloads/point/{NPM_TOTAL_SINCE}:"
        f"{_today()}/{package}",
    )
    return _int_field(payload, "downloads")


def _docker_pulls(http: Http) -> int:
    payload = _fetch(http, f"https://hub.docker.com/v2/repositories/{DOCKER_IMAGE}/")
    return _int_field(payload, "pull_count")


def _today() -> str:
    from datetime import date

    return date.today().isoformat()


SIMPLE_SOURCES = {
    "kenfold_stars": _github_stars,
    "aij_month": _pypi_monthly,
    "rapid_photo_web_pulls": _docker_pulls,
}


def collect(
    http: Http,
    previous: dict | None = None,
    warn: Callable[[str], None] | None = None,
) -> dict:
    """Read every metric, falling back to ``previous`` for any that fail."""
    previous = previous or {}
    warn = warn or (lambda _message: None)
    values: dict = {}

    for name, reader in SIMPLE_SOURCES.items():
        try:
            values[name] = reader(http)
        except SourceError as exc:
            if name not in previous:
                raise
            warn(f"{name}: {exc}; keeping previous value {previous[name]}")
            values[name] = previous[name]

    npm_total = 0
    npm_errors = []
    for package in NPM_PACKAGES:
        try:
            npm_total += _npm_total(http, package)
        except SourceError as exc:
            npm_errors.append(exc)

    if npm_errors:
        # The strip shows one combined npm figure, so a failed package falls back
        # to the committed total rather than blanking or overstating it.
        if previous.get("npm_total") is None:
            raise npm_errors[0]
        warn(f"npm: {npm_errors[0]}; keeping previous total {previous['npm_total']}")
        values["npm_total"] = previous["npm_total"]
    else:
        values["npm_total"] = npm_total

    return values


def segments_from(values: dict, compact: Callable[[int], str] | None = None) -> list[Segment]:
    """Turn collected metrics into the strip's segments, in display order."""
    from .render import compact_number

    compact = compact or compact_number
    return [
        Segment("KENFOLD", f"★{compact(values['kenfold_stars'])}", SEGMENT_ACCENT),
        Segment("AIJ", f"{compact(values['aij_month'])}/MO"),
        Segment("NPM", compact(values["npm_total"])),
        Segment("RAPID-PHOTO-WEB", compact(values["rapid_photo_web_pulls"])),
    ]


def read_previous(svg_text: str) -> dict:
    """Recover the metric values baked into a previously rendered strip.

    The SVG carries them in ``aria-label`` as ``LABEL value | ...`` which makes
    the committed file itself the fallback cache, so no extra state file can
    drift out of sync with what readers actually see.
    """
    match = re.search(r'aria-label="([^"]*)"', svg_text)
    if not match:
        return {}
    tokens = {}
    for chunk in match.group(1).split("|"):
        parts = chunk.strip().split(" ", 1)
        if len(parts) == 2:
            tokens[parts[0]] = parts[1]

    previous: dict = {}
    if "KENFOLD" in tokens:
        previous["kenfold_stars"] = _parse_compact(tokens["KENFOLD"].lstrip("★"))
    if "AIJ" in tokens:
        previous["aij_month"] = _parse_compact(tokens["AIJ"].replace("/MO", ""))
    if "NPM" in tokens:
        previous["npm_total"] = _parse_compact(tokens["NPM"])
    if "RAPID-PHOTO-WEB" in tokens:
        previous["rapid_photo_web_pulls"] = _parse_compact(tokens["RAPID-PHOTO-WEB"])
    return {k: v for k, v in previous.items() if v is not None}


def _parse_compact(text: str) -> int | None:
    text = text.strip()
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([KMB]?)", text)
    if not match:
        return None
    number = float(match.group(1))
    multiplier = {"": 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[match.group(2)]
    return int(round(number * multiplier))
