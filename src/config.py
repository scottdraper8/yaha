"""Configuration loading for YAHA.

Handles loading and validation of source configurations from blocklists.json
and whitelist from whitelist.txt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from src.domain_processor import ADBLOCK_EXCEPTION_PATTERN
from src.url_security import URLSecurityError, validate_https_url

MAX_SOURCE_NAME_LENGTH = 200
MAX_METADATA_LENGTH = 500


@dataclass
class SourceConfig:
    """Configuration for a single source list."""

    name: str
    url: str
    nsfw: bool = False
    maintainer_name: str | None = None
    maintainer_url: str | None = None
    maintainer_description: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceConfig:
        """Create SourceConfig from dictionary."""
        return cls(
            name=data["name"],
            url=data["url"],
            nsfw=data.get("nsfw", False),
            maintainer_name=data.get("maintainer_name"),
            maintainer_url=data.get("maintainer_url"),
            maintainer_description=data.get("maintainer_description"),
        )


@dataclass
class Whitelist:
    """Whitelist containing exact domains and wildcard patterns."""

    exact: set[str] = field(default_factory=set)
    wildcards: list[str] = field(default_factory=list)

    def is_whitelisted(self, domain: str) -> bool:
        """
        Check if domain matches whitelist.

        Exact matches are checked first (O(1)), then wildcard patterns.
        Wildcard patterns like *.example.com match both example.com
        and any subdomain like foo.example.com.
        """
        if domain in self.exact:
            return True

        for pattern in self.wildcards:
            if pattern.startswith("*."):
                suffix = pattern[2:]
                if domain == suffix or domain.endswith("." + suffix):
                    return True
        return False


def load_sources(config_path: Path = Path("blocklists.json")) -> list[SourceConfig]:
    """
    Load and validate source configurations from JSON file.

    Raises:
        FileNotFoundError: If config file not found
        json.JSONDecodeError: If JSON is invalid
        ValueError: If JSON structure is invalid
    """
    if not config_path.exists():
        raise FileNotFoundError(
            f"{config_path} not found. Please create it with source configurations."
        )

    with config_path.open(encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(f"{config_path} must contain a JSON array")

    sources: list[SourceConfig] = []
    seen_names: set[str] = set()
    seen_urls: set[str] = set()
    for idx, entry in enumerate(data, 1):
        if not isinstance(entry, dict):
            raise ValueError(f"Entry {idx} must be a JSON object")
        if "name" not in entry or "url" not in entry:
            raise ValueError(f"Entry {idx} missing 'name' or 'url' field")
        if "nsfw" in entry and not isinstance(entry["nsfw"], bool):
            raise ValueError(f"Entry {idx}: 'nsfw' field must be a boolean value")

        name = entry["name"]
        url = entry["url"]
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Entry {idx}: 'name' must be a non-empty string")
        if name != name.strip() or len(name) > MAX_SOURCE_NAME_LENGTH:
            raise ValueError(
                f"Entry {idx}: 'name' must be trimmed and at most "
                f"{MAX_SOURCE_NAME_LENGTH} characters"
            )
        if any(ord(char) < 32 or ord(char) == 127 for char in name):
            raise ValueError(f"Entry {idx}: 'name' must not contain control characters")
        if not isinstance(url, str):
            raise ValueError(f"Entry {idx}: 'url' must be a string")

        try:
            validate_https_url(url, field_name=f"Entry {idx}: 'url'")
        except URLSecurityError as exc:
            raise ValueError(str(exc)) from exc

        normalized_name = name.casefold()
        normalized_url = url
        if normalized_name in seen_names:
            raise ValueError(f"Entry {idx}: duplicate source name {name!r}")
        if normalized_url in seen_urls:
            raise ValueError(f"Entry {idx}: duplicate source URL {url!r}")
        seen_names.add(normalized_name)
        seen_urls.add(normalized_url)

        for field_name in (
            "maintainer_name",
            "maintainer_url",
            "maintainer_description",
        ):
            value = entry.get(field_name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"Entry {idx}: '{field_name}' must be a non-empty string")
            if isinstance(value, str) and len(value) > MAX_METADATA_LENGTH:
                raise ValueError(
                    f"Entry {idx}: '{field_name}' exceeds {MAX_METADATA_LENGTH} characters"
                )
            if isinstance(value, str) and value != value.strip():
                raise ValueError(f"Entry {idx}: '{field_name}' must not contain outer whitespace")
            if isinstance(value, str) and any(ord(char) < 32 or ord(char) == 127 for char in value):
                raise ValueError(f"Entry {idx}: '{field_name}' must not contain control characters")

        maintainer_url = entry.get("maintainer_url")
        if maintainer_url is not None:
            try:
                validate_https_url(
                    maintainer_url,
                    field_name=f"Entry {idx}: 'maintainer_url'",
                )
            except URLSecurityError as exc:
                raise ValueError(str(exc)) from exc

        sources.append(SourceConfig.from_dict(entry))

    return sources


def load_whitelist(whitelist_path: Path = Path("whitelist.txt")) -> Whitelist:
    """
    Load whitelist from file.

    Supports Adblock Plus exception rules (@@||domain^) and plain domains.
    @@||domain^ matches the domain and all subdomains.
    Lines starting with # or ! are treated as comments.
    """
    exact: set[str] = set()
    wildcards: list[str] = []

    if not whitelist_path.exists():
        return Whitelist(exact=exact, wildcards=wildcards)

    with whitelist_path.open(encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith(("#", "!")):
                continue

            abp_match = ADBLOCK_EXCEPTION_PATTERN.match(line)
            if abp_match:
                wildcards.append(f"*.{abp_match.group(1).lower()}")
            elif line.startswith("*."):
                wildcards.append(line.lower())
            else:
                exact.add(line.lower())

    return Whitelist(exact=exact, wildcards=wildcards)
