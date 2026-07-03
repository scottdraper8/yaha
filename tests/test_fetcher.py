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
    monkeypatch.setattr("src.fetcher.time.sleep", lambda _seconds: None)

    def fail_get(_url: str, **_kwargs: Any) -> None:
        raise TimeoutError("timed out")

    monkeypatch.setattr("src.fetcher.requests.get", fail_get)

    with pytest.raises(
        FetchError,
        match=r"https://example.com/list after 3 attempts: timed out",
    ):
        fetch_url_with_hash("https://example.com/list")


def test_transient_failure_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    """A transient source failure should not abort an otherwise valid analysis."""
    attempts = 0
    delays: list[int] = []

    def flaky_get(_url: str, **_kwargs: Any) -> _Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TimeoutError("timed out")
        return _Response()

    monkeypatch.setattr("src.fetcher.requests.get", flaky_get)
    monkeypatch.setattr("src.fetcher.time.sleep", delays.append)

    _, content, _ = fetch_url_with_hash("https://example.com/list")

    assert content == _Response.text
    assert attempts == 3
    assert delays == [2, 4]
