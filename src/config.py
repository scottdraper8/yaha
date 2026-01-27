"""Configuration loading for YAHA.

Handles loading and validation of source configurations from blocklists.json
and whitelist from whitelist.txt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any


@dataclass
class SourceConfig:
    """Configuration for a single source list."""

    name: str
    url: str
    nsfw: bool = False
    preserve: bool = False
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
            preserve=data.get("preserve", False),
            maintainer_name=data.get("maintainer_name"),
            maintainer_url=data.get("maintainer_url"),
            maintainer_description=data.get("maintainer_description"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {"name": self.name, "url": self.url}
        if self.nsfw:
            result["nsfw"] = self.nsfw
        if self.preserve:
            result["preserve"] = self.preserve
        if self.maintainer_name:
            result["maintainer_name"] = self.maintainer_name
        if self.maintainer_url:
            result["maintainer_url"] = self.maintainer_url
        if self.maintainer_description:
            result["maintainer_description"] = self.maintainer_description
        return result


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
    for idx, entry in enumerate(data, 1):
        if not isinstance(entry, dict):
            raise ValueError(f"Entry {idx} must be a JSON object")
        if "name" not in entry or "url" not in entry:
            raise ValueError(f"Entry {idx} missing 'name' or 'url' field")
        if "nsfw" in entry and not isinstance(entry["nsfw"], bool):
            raise ValueError(f"Entry {idx}: 'nsfw' field must be a boolean value")

        sources.append(SourceConfig.from_dict(entry))

    return sources


def save_sources(sources: list[SourceConfig], config_path: Path = Path("blocklists.json")) -> None:
    """Save source configurations to JSON file."""
    data = [source.to_dict() for source in sources]
    with config_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def load_whitelist(whitelist_path: Path = Path("whitelist.txt")) -> Whitelist:
    """
    Load whitelist from file.

    Format: one domain per line, supports wildcards (*.example.com)
    Lines starting with # are comments.
    """
    exact: set[str] = set()
    wildcards: list[str] = []

    if not whitelist_path.exists():
        return Whitelist(exact=exact, wildcards=wildcards)

    with whitelist_path.open(encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            domain = line.lower()
            if domain.startswith("*."):
                wildcards.append(domain)
            else:
                exact.add(domain)

    return Whitelist(exact=exact, wildcards=wildcards)
