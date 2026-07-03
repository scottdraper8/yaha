"""Tests for outbound URL validation and destination resolution."""

import socket

import pytest

from src.url_security import URLSecurityError, resolve_public_addresses, validate_https_url


def test_validate_https_url_accepts_canonical_public_hostname() -> None:
    parsed = validate_https_url("https://example.com/path?value=1")

    assert parsed.hostname == "example.com"


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com./path",
        "https://bad_host.example/path",
        "https://-bad.example/path",
        "https://example.com\\@127.0.0.1/path",
        "https://example.com/line\nbreak",
    ],
)
def test_validate_https_url_rejects_ambiguous_or_invalid_hosts(url: str) -> None:
    with pytest.raises(URLSecurityError):
        validate_https_url(url)


def test_resolve_public_addresses_returns_all_global_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (
                socket.AF_INET6,
                socket.SOCK_STREAM,
                6,
                "",
                ("2606:2800:220:1:248:1893:25c8:1946", 443, 0, 0),
            ),
        ],
    )

    assert resolve_public_addresses("https://example.com") == (
        "2606:2800:220:1:248:1893:25c8:1946",
        "93.184.216.34",
    )


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1"])
def test_resolve_public_addresses_rejects_non_global_results(
    address: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    socket_address: tuple[object, ...] = (
        (address, 443, 0, 0) if family == socket.AF_INET6 else (address, 443)
    )
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(family, socket.SOCK_STREAM, 6, "", socket_address)],
    )

    with pytest.raises(URLSecurityError, match="non-public address"):
        resolve_public_addresses("https://example.com")


def test_resolve_public_addresses_rejects_empty_dns_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_args, **_kwargs: [])

    with pytest.raises(URLSecurityError, match="did not resolve"):
        resolve_public_addresses("https://example.com")
