"""Tests for the HTTP boundary used by source analysis."""

import hashlib
from typing import Any

import pytest

from src.fetcher import FetchError, fetch_url_with_hash


class _Response:
    text = "one.example\ntwo.example\n"

    def raise_for_status(self) -> None:
        """Represent a successful HTTP response."""


def test_fetch_returns_stable_hash_content_and_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fetch boundary should preserve content and hash exactly what was received."""
    request: dict[str, Any] = {}

    def fake_get(url: str, **kwargs: Any) -> _Response:
        request.update({"url": url, **kwargs})
        return _Response()

    monkeypatch.setattr("src.fetcher.requests.get", fake_get)

    content_hash, content, lines = fetch_url_with_hash("https://example.com/list", timeout=12)

    assert request == {
        "url": "https://example.com/list",
        "timeout": 12,
        "impersonate": "chrome120",
        "verify": True,
    }
    assert content_hash == hashlib.sha256(content.encode()).hexdigest()
    assert list(lines) == ["one.example", "two.example", ""]


def test_transport_failure_is_wrapped_with_source_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Transport errors should identify the source that could not be analyzed."""

    def fail_get(_url: str, **_kwargs: Any) -> None:
        raise TimeoutError("timed out")

    monkeypatch.setattr("src.fetcher.requests.get", fail_get)

    with pytest.raises(FetchError, match=r"https://example.com/list: timed out"):
        fetch_url_with_hash("https://example.com/list")
