"""Cache management for source content.

Stores fetched source content locally to enable compile-only mode
without network requests.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, TypedDict, cast

CACHE_DIR = Path("cache")
MANIFEST_FILE = CACHE_DIR / "manifest.json"


class CachedSourceData(TypedDict):
    """Type definition for cached source data in manifest."""

    cache_file: str
    url: str
    content_hash: str


class ManifestData(TypedDict):
    """Type definition for manifest.json structure."""

    cached_at: str | None
    sources: dict[str, CachedSourceData]


class CacheStatsData(TypedDict):
    """Type definition for cache statistics."""

    exists: bool
    source_count: int
    cached_at: str | None


@dataclass
class CachedSource:
    """Cached source metadata."""

    cache_file: str
    url: str
    content_hash: str


def cache_exists() -> bool:
    """Check if cache directory and manifest exist."""
    return CACHE_DIR.exists() and MANIFEST_FILE.exists()


def ensure_cache_dir() -> None:
    """Create cache directory if it doesn't exist."""
    CACHE_DIR.mkdir(exist_ok=True)


def get_cache_file_path(source_index: int) -> Path:
    """Get the cache file path for a source by index."""
    return CACHE_DIR / f"source_{source_index}.txt"


def save_to_cache(
    source_name: str,
    source_index: int,
    content: str,
    url: str,
    content_hash: str,
) -> None:
    """
    Save fetched source content to cache.

    Updates the manifest with source metadata.
    """
    ensure_cache_dir()

    cache_file = get_cache_file_path(source_index)
    cache_file.write_text(content, encoding="utf-8")

    manifest = load_manifest()
    manifest["cached_at"] = datetime.now(UTC).isoformat()
    manifest["sources"][source_name] = {
        "cache_file": cache_file.name,
        "url": url,
        "content_hash": content_hash,
    }

    save_manifest(manifest)


def load_from_cache(source_name: str) -> Iterator[str]:
    """
    Load source content from cache as a line iterator.

    Raises:
        FileNotFoundError: If cache or source not found
        KeyError: If source not in manifest
    """
    if not cache_exists():
        raise FileNotFoundError("Cache not found")

    manifest = load_manifest()
    if source_name not in manifest["sources"]:
        raise KeyError(f"Source '{source_name}' not found in cache")

    cache_file_name = manifest["sources"][source_name]["cache_file"]
    cache_file = CACHE_DIR / cache_file_name

    if not cache_file.exists():
        raise FileNotFoundError(f"Cache file '{cache_file_name}' not found")

    with cache_file.open("r", encoding="utf-8") as f:
        for line in f:
            yield line.rstrip("\r\n")


def load_manifest() -> ManifestData:
    """Load the cache manifest file."""
    if not MANIFEST_FILE.exists():
        return {"cached_at": None, "sources": {}}

    with MANIFEST_FILE.open("r", encoding="utf-8") as f:
        data: Any = json.load(f)
        return cast(ManifestData, data)


def save_manifest(manifest: ManifestData) -> None:
    """Save the cache manifest file."""
    ensure_cache_dir()
    with MANIFEST_FILE.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")


def get_cached_sources() -> dict[str, CachedSource]:
    """
    Load manifest and return cached sources.

    Returns:
        Dictionary mapping source names to CachedSource objects
    """
    if not cache_exists():
        return {}

    manifest = load_manifest()
    result: dict[str, CachedSource] = {}

    for name, data in manifest.get("sources", {}).items():
        result[name] = CachedSource(
            cache_file=data["cache_file"],
            url=data["url"],
            content_hash=data["content_hash"],
        )

    return result


def validate_cache(source_names: list[str]) -> tuple[bool, list[str]]:
    """
    Validate that cache contains all required sources.

    Args:
        source_names: List of source names that should be cached

    Returns:
        Tuple of (is_valid, missing_sources)
    """
    if not cache_exists():
        return False, source_names

    cached = get_cached_sources()
    missing = [name for name in source_names if name not in cached]

    return len(missing) == 0, missing


def get_cache_stats() -> CacheStatsData:
    """Get statistics about the current cache."""
    if not cache_exists():
        return {"exists": False, "source_count": 0, "cached_at": None}

    manifest = load_manifest()
    return {
        "exists": True,
        "source_count": len(manifest.get("sources", {})),
        "cached_at": manifest.get("cached_at"),
    }
