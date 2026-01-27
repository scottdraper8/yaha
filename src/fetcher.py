"""HTTP fetching for YAHA.

Minimal-knowledge module for fetching URLs and computing content hashes.
Generic URL fetching - no knowledge of blocklists or their purpose.
"""

from __future__ import annotations

from collections.abc import Iterator
import hashlib

from curl_cffi import requests

REQUEST_TIMEOUT = 30


class FetchError(Exception):
    """Raised when URL fetch fails."""

    pass


def fetch_url_with_hash(url: str, timeout: int = REQUEST_TIMEOUT) -> tuple[str, Iterator[str]]:
    """
    Fetch URL content and compute SHA256 hash.

    Uses curl_cffi with browser impersonation to handle anti-bot measures.

    Args:
        url: URL to fetch
        timeout: Request timeout in seconds

    Returns:
        Tuple of (content_hash, line_iterator)

    Raises:
        FetchError: If request fails
    """
    try:
        response = requests.get(
            url,
            timeout=timeout,
            impersonate="chrome120",
            verify=True,
        )
        response.raise_for_status()

        response_text = response.text
        content_hash = hashlib.sha256(response_text.encode("utf-8")).hexdigest()

        def line_generator() -> Iterator[str]:
            for line in response_text.split("\n"):
                yield line.rstrip("\r")

        return content_hash, line_generator()

    except Exception as e:
        raise FetchError(f"Failed to fetch {url}: {e}") from e


def compute_content_hash(content: str) -> str:
    """Compute SHA256 hash of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
