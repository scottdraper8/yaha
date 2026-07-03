"""HTTP source retrieval and content hashing."""

from __future__ import annotations

from collections.abc import Iterator
import hashlib
import time

from curl_cffi import requests

REQUEST_TIMEOUT = 90
MAX_FETCH_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 2


class FetchError(Exception):
    """Raised when URL fetch fails."""

    pass


def _iter_lines(content: str) -> Iterator[str]:
    for line in content.split("\n"):
        yield line.rstrip("\r")


def fetch_url_with_hash(
    url: str,
    timeout: int = REQUEST_TIMEOUT,
    max_attempts: int = MAX_FETCH_ATTEMPTS,
) -> tuple[str, str, Iterator[str]]:
    """
    Fetch URL content and compute SHA256 hash.

    Uses curl_cffi with browser impersonation to handle anti-bot measures.

    Args:
        url: URL to fetch
        timeout: Request timeout in seconds
        max_attempts: Maximum requests before reporting failure

    Returns:
        Tuple of (content_hash, raw_content, line_iterator)

    Raises:
        FetchError: If request fails
    """
    error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
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
            return content_hash, response_text, _iter_lines(response_text)
        except Exception as exc:
            error = exc
            if attempt < max_attempts:
                time.sleep(RETRY_DELAY_SECONDS * attempt)

    raise FetchError(f"Failed to fetch {url} after {max_attempts} attempts: {error}") from error


def compute_content_hash(content: str) -> str:
    """Compute SHA256 hash of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
