"""Tests for src/fetcher.py.

Minimal tests for fetch wrapper integration. Most functionality is from curl_cffi
which is not controlled by this codebase - only the specific integration is tested.
"""

import pytest

from src.fetcher import FetchError, fetch_url_with_hash


class TestFetchUrlWithHash:
    """Tests for fetch_url_with_hash integration with curl_cffi."""

    def test_fetch_returns_hash_content_and_lines(self) -> None:
        """Test basic fetch returns valid hash, raw content, and iterable lines."""
        url = "https://httpbin.org/robots.txt"
        content_hash, raw_content, lines = fetch_url_with_hash(url)

        # SHA256 hash format verification
        assert len(content_hash) == 64
        assert all(c in "0123456789abcdef" for c in content_hash)

        # Raw content verification
        assert isinstance(raw_content, str)
        assert len(raw_content) > 0

        # Iterator consumption verification
        lines_list = list(lines)
        assert len(lines_list) > 0

    def test_http_error_raises_fetch_error(self) -> None:
        """Test that HTTP errors are wrapped in FetchError."""
        url = "https://httpbin.org/status/404"
        with pytest.raises(FetchError):
            fetch_url_with_hash(url)

    def test_timeout_raises_fetch_error(self) -> None:
        """Test that timeouts are wrapped in FetchError."""
        url = "https://httpbin.org/delay/5"
        with pytest.raises(FetchError):
            fetch_url_with_hash(url, timeout=1)
