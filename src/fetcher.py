"""Bounded HTTP source retrieval and content hashing."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import socket
from threading import Lock
import time
from typing import Protocol, cast
from urllib.parse import urljoin

from curl_cffi import requests

from src.url_security import URLSecurityError, resolve_public_addresses, validate_https_url

CONNECT_TIMEOUT_SECONDS = 10
READ_TIMEOUT_SECONDS = 90
MAX_FETCH_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 2
MAX_REDIRECTS = 5
MAX_SOURCE_BYTES = 512 * 1024 * 1024
MAX_TOTAL_DOWNLOAD_BYTES = 2 * 1024 * 1024 * 1024
MAX_LINE_BYTES = 4_096
MAX_LINES_PER_SOURCE = 10_000_000
DOWNLOAD_CHUNK_BYTES = 64 * 1024
RETRYABLE_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})
REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})
SUPPORTED_CONTENT_ENCODINGS = frozenset({"", "identity", "gzip", "deflate", "br", "zstd"})


class _StreamingResponse(Protocol):
    """Typed surface used from curl-cffi's partially typed response class."""

    status_code: int
    headers: Mapping[str, str]

    def raise_for_status(self) -> None: ...

    def iter_content(self, chunk_size: int) -> Iterator[bytes]: ...

    def close(self) -> None: ...


class FetchError(Exception):
    """Raised when URL fetch fails."""


class FetchLimitError(FetchError):
    """Raised when a source exceeds a configured resource limit."""


class _RetryableFetchError(FetchError):
    """Internal marker for an HTTP response that may succeed on retry."""


@dataclass
class DownloadBudget:
    """Thread-safe aggregate download budget."""

    maximum: int = MAX_TOTAL_DOWNLOAD_BYTES
    used: int = 0
    _lock: Lock = field(default_factory=Lock, repr=False)

    def consume(self, amount: int) -> None:
        """Reserve downloaded bytes or fail before exceeding the maximum."""
        with self._lock:
            if self.used + amount > self.maximum:
                raise FetchLimitError(
                    f"aggregate download limit of {self.maximum:,} bytes exceeded"
                )
            self.used += amount


@dataclass(frozen=True)
class FetchedSource:
    """Metadata for a source body stored in a private temporary file."""

    content_hash: str
    path: Path
    byte_count: int
    line_count: int
    final_url: str

    def iter_lines(self) -> Iterator[str]:
        """Yield strictly decoded UTF-8 lines from the downloaded body."""
        try:
            with self.path.open("r", encoding="utf-8", errors="strict", newline="") as source:
                for line in source:
                    yield line.rstrip("\r\n")
        except UnicodeDecodeError as exc:
            raise FetchError(f"Source {self.final_url} is not valid UTF-8: {exc}") from exc


def _header(response: _StreamingResponse, name: str) -> str:
    """Read a response header case-insensitively."""
    return str(response.headers.get(name, "")).strip()


def _validate_response_headers(response: _StreamingResponse, url: str) -> None:
    content_encoding = _header(response, "Content-Encoding").lower()
    if content_encoding not in SUPPORTED_CONTENT_ENCODINGS:
        raise FetchError(f"Unsupported Content-Encoding {content_encoding!r} from {url}")

    content_length = _header(response, "Content-Length")
    if content_length:
        try:
            declared_length = int(content_length)
        except ValueError as exc:
            raise FetchError(f"Invalid Content-Length from {url}") from exc
        if declared_length < 0:
            raise FetchError(f"Invalid Content-Length from {url}")
        if declared_length > MAX_SOURCE_BYTES:
            raise FetchLimitError(
                f"Source {url} declares {declared_length:,} bytes; limit is {MAX_SOURCE_BYTES:,}"
            )


def _download_once(url: str, destination: Path, budget: DownloadBudget) -> FetchedSource:
    current_url = url

    for redirect_count in range(MAX_REDIRECTS + 1):
        try:
            validate_https_url(current_url)
            resolve_public_addresses(current_url)
        except socket.gaierror as exc:
            raise _RetryableFetchError(f"DNS lookup failed for {current_url}: {exc}") from exc
        except URLSecurityError as exc:
            raise FetchError(f"Unsafe source URL {current_url}: {exc}") from exc

        response = cast(
            _StreamingResponse,
            requests.get(
                current_url,
                timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
                impersonate="chrome120",
                verify=True,
                stream=True,
                allow_redirects=False,
                accept_encoding="identity",
            ),
        )
        try:
            status_code = response.status_code
            if status_code in REDIRECT_STATUS_CODES:
                if redirect_count == MAX_REDIRECTS:
                    raise FetchError(f"Too many redirects while fetching {url}")
                location = _header(response, "Location")
                if not location:
                    raise FetchError(f"Redirect from {current_url} omitted Location header")
                current_url = urljoin(current_url, location)
                continue

            if status_code in RETRYABLE_STATUS_CODES:
                raise _RetryableFetchError(f"HTTP {status_code} from {current_url}")
            response.raise_for_status()
            _validate_response_headers(response, current_url)

            digest = hashlib.sha256()
            byte_count = 0
            line_count = 0
            current_line_bytes = 0

            with destination.open("wb") as output:
                for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_BYTES):
                    if not chunk:
                        continue
                    budget.consume(len(chunk))
                    byte_count += len(chunk)
                    if byte_count > MAX_SOURCE_BYTES:
                        raise FetchLimitError(
                            f"Source {current_url} exceeds {MAX_SOURCE_BYTES:,} bytes"
                        )

                    pieces = chunk.split(b"\n")
                    for index, piece in enumerate(pieces):
                        current_line_bytes += len(piece)
                        if current_line_bytes > MAX_LINE_BYTES:
                            raise FetchLimitError(
                                f"Source {current_url} contains a line longer than "
                                f"{MAX_LINE_BYTES:,} bytes"
                            )
                        if index < len(pieces) - 1:
                            line_count += 1
                            current_line_bytes = 0
                            if line_count > MAX_LINES_PER_SOURCE:
                                raise FetchLimitError(
                                    f"Source {current_url} exceeds {MAX_LINES_PER_SOURCE:,} lines"
                                )

                    digest.update(chunk)
                    output.write(chunk)

            if current_line_bytes:
                line_count += 1
            if line_count > MAX_LINES_PER_SOURCE:
                raise FetchLimitError(
                    f"Source {current_url} exceeds {MAX_LINES_PER_SOURCE:,} lines"
                )

            return FetchedSource(
                content_hash=digest.hexdigest(),
                path=destination,
                byte_count=byte_count,
                line_count=line_count,
                final_url=current_url,
            )
        finally:
            response.close()

    raise FetchError(f"Too many redirects while fetching {url}")


def fetch_url_with_hash(
    url: str,
    destination: Path,
    max_attempts: int = MAX_FETCH_ATTEMPTS,
    budget: DownloadBudget | None = None,
) -> FetchedSource:
    """
    Fetch URL content and compute SHA256 hash.

    Uses curl_cffi with browser impersonation to handle anti-bot measures.

    Args:
        url: URL to fetch
        destination: Private temporary file for the downloaded body
        max_attempts: Maximum requests before reporting failure
        budget: Optional shared aggregate download budget

    Returns:
        Download metadata and the temporary body path

    Raises:
        FetchError: If request fails
    """
    validate_https_url(url)
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    active_budget = budget or DownloadBudget()
    error: requests.RequestsError | _RetryableFetchError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return _download_once(url, destination, active_budget)
        except (requests.RequestsError, _RetryableFetchError) as exc:
            error = exc
            destination.unlink(missing_ok=True)
            if attempt < max_attempts:
                time.sleep(RETRY_DELAY_SECONDS * attempt)
        except Exception:
            destination.unlink(missing_ok=True)
            raise

    destination.unlink(missing_ok=True)
    raise FetchError(f"Failed to fetch {url} after {max_attempts} attempts: {error}") from error


def compute_content_hash(content: str) -> str:
    """Compute SHA256 hash of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
