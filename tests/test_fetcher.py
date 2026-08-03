"""Tests for the HTTP boundary used by source analysis."""

import hashlib
from pathlib import Path
from typing import Any

from curl_cffi import requests
import pytest

from src.fetcher import DownloadBudget, FetchError, FetchLimitError, fetch_url_with_hash


class _Response:
    def __init__(
        self,
        content: bytes = b"one.example\ntwo.example\n",
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.content = content
        self.status_code = status_code
        self.headers = headers or {}
        self.closed = False

    def raise_for_status(self) -> None:
        """Represent a successful HTTP response."""

    def iter_content(self, chunk_size: int) -> list[bytes]:
        """Return bounded chunks like curl-cffi."""
        return [
            self.content[index : index + chunk_size]
            for index in range(0, len(self.content), chunk_size)
        ]

    def close(self) -> None:
        """Record response cleanup."""
        self.closed = True


def test_fetch_returns_stable_hash_file_and_lines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fetch boundary should preserve content and hash exactly what was received."""
    request: dict[str, Any] = {}
    response = _Response()

    def fake_get(url: str, **kwargs: Any) -> _Response:
        request.update({"url": url, **kwargs})
        return response

    monkeypatch.setattr("src.fetcher.requests.get", fake_get)
    monkeypatch.setattr("src.fetcher.resolve_public_addresses", lambda _url: ("93.184.216.34",))

    fetched = fetch_url_with_hash("https://example.com/list", tmp_path / "source.list")

    assert request == {
        "url": "https://example.com/list",
        "timeout": (10, 90),
        "impersonate": "chrome120",
        "verify": True,
        "stream": True,
        "allow_redirects": False,
        "accept_encoding": "identity",
    }
    assert fetched.content_hash == hashlib.sha256(response.content).hexdigest()
    assert fetched.byte_count == len(response.content)
    assert fetched.line_count == 2
    assert list(fetched.iter_lines()) == ["one.example", "two.example"]
    assert response.closed is True


def test_transport_failure_is_wrapped_with_source_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transport errors should identify the source that could not be analyzed."""
    monkeypatch.setattr("src.fetcher.time.sleep", lambda _seconds: None)
    monkeypatch.setattr("src.fetcher.resolve_public_addresses", lambda _url: ("93.184.216.34",))

    def fail_get(_url: str, **_kwargs: Any) -> None:
        raise requests.RequestsError("timed out")

    monkeypatch.setattr("src.fetcher.requests.get", fail_get)

    with pytest.raises(
        FetchError,
        match=r"https://example.com/list after 5 attempts: timed out",
    ):
        fetch_url_with_hash("https://example.com/list", tmp_path / "source.list")


def test_transient_failure_is_retried(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transient source failure should not abort an otherwise valid analysis."""
    attempts = 0
    delays: list[int] = []
    response = _Response()

    def flaky_get(_url: str, **_kwargs: Any) -> _Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise requests.RequestsError("timed out")
        return response

    monkeypatch.setattr("src.fetcher.requests.get", flaky_get)
    monkeypatch.setattr("src.fetcher.time.sleep", delays.append)
    monkeypatch.setattr("src.fetcher.resolve_public_addresses", lambda _url: ("93.184.216.34",))

    fetched = fetch_url_with_hash("https://example.com/list", tmp_path / "source.list")

    assert fetched.path.read_bytes() == response.content
    assert attempts == 3
    assert delays == [2, 4]


def test_programming_error_is_not_retried(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected implementation errors must surface immediately."""
    attempts = 0

    def broken_get(_url: str, **_kwargs: Any) -> None:
        nonlocal attempts
        attempts += 1
        raise TypeError("programming error")

    monkeypatch.setattr("src.fetcher.requests.get", broken_get)
    monkeypatch.setattr("src.fetcher.resolve_public_addresses", lambda _url: ("93.184.216.34",))

    with pytest.raises(TypeError, match="programming error"):
        fetch_url_with_hash("https://example.com/list", tmp_path / "source.list")

    assert attempts == 1


def test_source_byte_limit_removes_partial_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Oversized source bodies must fail without leaving a partial download."""
    destination = tmp_path / "source.list"
    monkeypatch.setattr("src.fetcher.MAX_SOURCE_BYTES", 4)
    monkeypatch.setattr("src.fetcher.requests.get", lambda _url, **_kwargs: _Response(b"12345"))
    monkeypatch.setattr("src.fetcher.resolve_public_addresses", lambda _url: ("93.184.216.34",))

    with pytest.raises(FetchLimitError, match="exceeds 4 bytes"):
        fetch_url_with_hash("https://example.com/list", destination)

    assert not destination.exists()


def test_aggregate_budget_is_enforced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Concurrent callers share a strict aggregate byte budget."""
    monkeypatch.setattr("src.fetcher.requests.get", lambda _url, **_kwargs: _Response(b"12345"))
    monkeypatch.setattr("src.fetcher.resolve_public_addresses", lambda _url: ("93.184.216.34",))

    with pytest.raises(FetchLimitError, match="aggregate download limit"):
        fetch_url_with_hash(
            "https://example.com/list",
            tmp_path / "source.list",
            budget=DownloadBudget(maximum=4),
        )


def test_line_length_limit_is_enforced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single hostile line cannot grow without bound."""
    monkeypatch.setattr("src.fetcher.MAX_LINE_BYTES", 4)
    monkeypatch.setattr("src.fetcher.requests.get", lambda _url, **_kwargs: _Response(b"12345\n"))
    monkeypatch.setattr("src.fetcher.resolve_public_addresses", lambda _url: ("93.184.216.34",))

    with pytest.raises(FetchLimitError, match="line longer than 4 bytes"):
        fetch_url_with_hash("https://example.com/list", tmp_path / "source.list")


def test_redirect_destination_is_revalidated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Redirects must not escape to loopback or private destinations."""
    response = _Response(status_code=302, headers={"Location": "https://127.0.0.1/list"})
    monkeypatch.setattr("src.fetcher.requests.get", lambda _url, **_kwargs: response)
    monkeypatch.setattr("src.fetcher.resolve_public_addresses", lambda _url: ("93.184.216.34",))

    with pytest.raises(FetchError, match="Unsafe source URL"):
        fetch_url_with_hash("https://example.com/list", tmp_path / "source.list")

    assert response.closed is True


def test_invalid_utf8_is_rejected_when_consumed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Host lists are required to decode as UTF-8."""
    monkeypatch.setattr("src.fetcher.requests.get", lambda _url, **_kwargs: _Response(b"\xff\n"))
    monkeypatch.setattr("src.fetcher.resolve_public_addresses", lambda _url: ("93.184.216.34",))
    fetched = fetch_url_with_hash("https://example.com/list", tmp_path / "source.list")

    with pytest.raises(FetchError, match="not valid UTF-8"):
        list(fetched.iter_lines())
