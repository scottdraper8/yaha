"""Domain processing for YAHA.

Zero-knowledge module for domain validation and extraction.
No knowledge of blocklists, NSFW categories, or source purposes.
"""

from __future__ import annotations

from collections.abc import Iterator
import re


def is_valid_domain(domain: str) -> bool:
    """
    Validate domain structure per RFC 1035.

    Max 253 chars total, 63 per label. No leading/trailing hyphens.
    """
    if not domain or len(domain) > 253:
        return False

    if "." not in domain or domain.startswith(".") or domain.endswith("."):
        return False

    if ".." in domain:
        return False

    labels = domain.split(".")
    for label in labels:
        if not label or len(label) > 63:
            return False
        if label.startswith("-") or label.endswith("-"):
            return False

    return True


# Domain validation regex per RFC 1035
_DOMAIN_REGEX = (
    r"[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*"
)

HOSTS_PATTERN = re.compile(rf"^(?:0\.0\.0\.0|127\.0\.0\.1|::1?)[\s\t]+({_DOMAIN_REGEX})")
RAW_DOMAIN_PATTERN = re.compile(rf"^({_DOMAIN_REGEX})$")
ADBLOCK_PATTERN = re.compile(rf"^\|\|({_DOMAIN_REGEX})\^")

LOCALHOST_PREFIXES = (
    "127.0.0.1 localhost",
    "::1 localhost",
    "0.0.0.0 localhost",
    "::1 ip6-localhost",
    "::1 ip6-loopback",
)


def extract_domains_from_lines(lines: Iterator[str]) -> Iterator[str]:
    """
    Extract domains from line iterator.

    Supports hosts files, raw domain lists, and Adblock Plus filters.
    Domains are preserved exactly as specified by the source list maintainer.
    """
    patterns = [ADBLOCK_PATTERN, HOSTS_PATTERN, RAW_DOMAIN_PATTERN]

    for raw_line in lines:
        if not raw_line:
            continue
        line = raw_line.strip()

        if not line or line.startswith(("#", "!", "[")):
            continue

        if any(line.startswith(prefix) for prefix in LOCALHOST_PREFIXES):
            continue

        for pattern in patterns:
            match = pattern.match(line)
            if match:
                domain = match.group(1).lower()
                if is_valid_domain(domain):
                    yield domain
                break
