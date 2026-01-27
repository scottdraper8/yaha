"""Domain processing for YAHA.

Zero-knowledge module for domain validation and extraction.
No knowledge of blocklists, NSFW categories, or source purposes.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import re

from curl_cffi import requests

# Public Suffix List configuration
PSL_FILE = Path("public_suffix_list.dat")
PSL_URL = "https://publicsuffix.org/list/public_suffix_list.dat"
PSL_STALE_DAYS = 30
REQUEST_TIMEOUT = 30


@dataclass(frozen=True)
class PublicSuffixList:
    """
    Parsed Public Suffix List data structure.

    Supports exact suffixes, wildcard rules, and exception rules.
    """

    exact: frozenset[str]
    wildcards: frozenset[str]
    exceptions: frozenset[str]


def download_psl(psl_path: Path) -> None:
    """Download the Public Suffix List from Mozilla."""
    response = requests.get(
        PSL_URL,
        timeout=REQUEST_TIMEOUT,
        impersonate="chrome120",
        verify=True,
    )
    response.raise_for_status()
    psl_path.write_text(response.text, encoding="utf-8")


def load_public_suffix_list(psl_path: Path) -> PublicSuffixList:
    """
    Parse the Public Suffix List file into lookup structures.

    Format:
    - Lines starting with // are comments
    - Blank lines are ignored
    - *.suffix indicates wildcard (all subdomains are public suffixes)
    - !exception indicates an exception to a wildcard rule
    - Other lines are exact public suffixes
    """
    exact: set[str] = set()
    wildcards: set[str] = set()
    exceptions: set[str] = set()

    with psl_path.open(encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()

            if not line or line.startswith("//"):
                continue

            if line.startswith("!"):
                exceptions.add(line[1:].lower())
            elif line.startswith("*."):
                wildcards.add(line[2:].lower())
            else:
                exact.add(line.lower())

    return PublicSuffixList(
        exact=frozenset(exact),
        wildcards=frozenset(wildcards),
        exceptions=frozenset(exceptions),
    )


def ensure_psl_and_load(psl_path: Path = PSL_FILE, quiet: bool = False) -> PublicSuffixList:
    """
    Ensure PSL file exists and is fresh, then load and parse it.

    Downloads the PSL if missing or stale (>30 days old).
    """
    stale = False
    if not psl_path.exists():
        stale = True
    else:
        mtime = datetime.fromtimestamp(psl_path.stat().st_mtime, tz=UTC)
        age_days = (datetime.now(UTC) - mtime).days
        stale = age_days >= PSL_STALE_DAYS

    if stale:
        if not quiet:
            print("  Downloading fresh Public Suffix List...")
        download_psl(psl_path)
        if not quiet:
            print(f"  Saved to {psl_path}")
    elif not quiet:
        print(f"  Using cached {psl_path}")

    return load_public_suffix_list(psl_path)


def get_registrable_domain(domain: str, psl: PublicSuffixList) -> str:
    """
    Extract the registrable (base) domain respecting public suffixes.

    The registrable domain is the public suffix plus one label.
    For public suffixes like github.io, this preserves user.github.io
    rather than incorrectly stripping to github.io.

    Examples:
        www.example.com -> example.com
        api.foo.github.io -> foo.github.io (github.io is public suffix)
        www.example.co.uk -> example.co.uk (co.uk is public suffix)
        sub.example.ck -> example.ck (*.ck wildcard rule)
        www.ck -> www.ck (!www.ck exception)
    """
    labels = domain.split(".")
    num_labels = len(labels)

    if num_labels < 2:
        return domain

    for i in range(num_labels):
        candidate = ".".join(labels[i:])

        # Check exception rules first (highest priority)
        # Exception means this candidate is NOT a public suffix - skip it
        if candidate in psl.exceptions:
            continue

        # Check exact match
        if candidate in psl.exact:
            if i == 0:
                return domain
            return ".".join(labels[i - 1 :])

        # Check wildcard rules
        if len(labels) > i + 1:
            parent = ".".join(labels[i + 1 :])
            is_wildcard_match = parent in psl.wildcards and candidate not in psl.exceptions
            if is_wildcard_match:
                if i == 0:
                    return domain
                return ".".join(labels[i - 1 :])

    # No public suffix found - treat TLD as suffix
    return ".".join(labels[-2:])


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


def extract_domains_from_lines(lines: Iterator[str], psl: PublicSuffixList) -> Iterator[str]:
    """
    Extract domains from line iterator, strip to base domain.

    Supports hosts files, raw domain lists, and Adblock Plus filters.
    Domains are stripped to their registrable base domain.
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
                    base_domain = get_registrable_domain(domain, psl)
                    yield base_domain
                break
