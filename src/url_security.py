"""Validation helpers for URLs that cross a network trust boundary."""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import SplitResult, urlsplit

MAX_URL_LENGTH = 2_048
HOST_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


class URLSecurityError(ValueError):
    """Raised when a URL is malformed or targets an unsafe destination."""


def validate_https_url(url: str, *, field_name: str = "URL") -> SplitResult:
    """Validate an HTTPS URL without performing network I/O."""
    if not isinstance(url, str) or not url:
        raise URLSecurityError(f"{field_name} must be a non-empty string")
    if url != url.strip():
        raise URLSecurityError(f"{field_name} must not contain surrounding whitespace")
    if len(url) > MAX_URL_LENGTH:
        raise URLSecurityError(f"{field_name} exceeds {MAX_URL_LENGTH} characters")
    if "\\" in url or any(ord(char) < 32 or ord(char) == 127 for char in url):
        raise URLSecurityError(f"{field_name} contains an unsafe character")

    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise URLSecurityError(f"{field_name} is invalid: {exc}") from exc

    if parsed.scheme.lower() != "https":
        raise URLSecurityError(f"{field_name} must use HTTPS")
    if not parsed.netloc or parsed.hostname is None:
        raise URLSecurityError(f"{field_name} must include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise URLSecurityError(f"{field_name} must not contain credentials")
    if parsed.fragment:
        raise URLSecurityError(f"{field_name} must not contain a fragment")
    if port not in (None, 443):
        raise URLSecurityError(f"{field_name} must use the default HTTPS port")

    hostname = parsed.hostname.rstrip(".")
    if not hostname or hostname != parsed.hostname:
        raise URLSecurityError(f"{field_name} must use a canonical hostname")

    try:
        ascii_hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise URLSecurityError(f"{field_name} contains an invalid hostname") from exc

    try:
        address = ipaddress.ip_address(ascii_hostname)
    except ValueError:
        if len(ascii_hostname) > 253 or any(
            not HOST_LABEL_PATTERN.fullmatch(label) for label in ascii_hostname.split(".")
        ):
            raise URLSecurityError(f"{field_name} contains an invalid hostname") from None
    else:
        if not address.is_global:
            raise URLSecurityError(f"{field_name} targets a non-public IP address")

    return parsed


def resolve_public_addresses(url: str) -> tuple[str, ...]:
    """Resolve a validated URL and reject every non-global result."""
    parsed = validate_https_url(url)
    assert parsed.hostname is not None

    addresses: set[str] = set()
    for result in socket.getaddrinfo(
        parsed.hostname,
        parsed.port or 443,
        type=socket.SOCK_STREAM,
    ):
        address_text = result[4][0]
        address = ipaddress.ip_address(address_text)
        if not address.is_global:
            raise URLSecurityError(
                f"URL hostname {parsed.hostname!r} resolves to non-public address {address}"
            )
        addresses.add(address.compressed)

    if not addresses:
        raise URLSecurityError(f"URL hostname {parsed.hostname!r} did not resolve")

    return tuple(sorted(addresses))
