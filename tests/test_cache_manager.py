"""Tests for src/cache_manager.py."""

from pathlib import Path

import pytest

from src.cache_manager import (
    cache_exists,
    get_cache_stats,
    get_cached_sources,
    load_from_cache,
    load_manifest,
    save_to_cache,
    validate_cache,
)


class TestCacheExistence:
    """Tests for cache existence checking."""

    def test_cache_not_exists_when_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test cache_exists returns False when no cache directory."""
        monkeypatch.setattr("src.cache_manager.CACHE_DIR", tmp_path / "cache")
        monkeypatch.setattr("src.cache_manager.MANIFEST_FILE", tmp_path / "cache" / "manifest.json")
        assert cache_exists() is False

    def test_cache_not_exists_without_manifest(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test cache_exists returns False when cache dir exists but no manifest."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        monkeypatch.setattr("src.cache_manager.CACHE_DIR", cache_dir)
        monkeypatch.setattr("src.cache_manager.MANIFEST_FILE", cache_dir / "manifest.json")
        assert cache_exists() is False

    def test_cache_exists_with_manifest(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test cache_exists returns True when manifest exists."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        manifest_file = cache_dir / "manifest.json"
        manifest_file.write_text('{"sources": {}}')
        monkeypatch.setattr("src.cache_manager.CACHE_DIR", cache_dir)
        monkeypatch.setattr("src.cache_manager.MANIFEST_FILE", manifest_file)
        assert cache_exists() is True


class TestSaveToCache:
    """Tests for saving source content to cache."""

    def test_save_creates_cache_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test save_to_cache creates cache file and updates manifest."""
        cache_dir = tmp_path / "cache"
        manifest_file = cache_dir / "manifest.json"
        monkeypatch.setattr("src.cache_manager.CACHE_DIR", cache_dir)
        monkeypatch.setattr("src.cache_manager.MANIFEST_FILE", manifest_file)

        save_to_cache(
            source_name="Test Source",
            source_index=0,
            content="line1\nline2\nline3",
            url="https://example.com/list.txt",
            content_hash="abc123",
        )

        cache_file = cache_dir / "source_0.txt"
        assert cache_file.exists()
        assert cache_file.read_text() == "line1\nline2\nline3"

        manifest = load_manifest()
        assert "Test Source" in manifest["sources"]
        assert manifest["sources"]["Test Source"]["cache_file"] == "source_0.txt"
        assert manifest["sources"]["Test Source"]["content_hash"] == "abc123"

    def test_save_multiple_sources(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test saving multiple sources to cache."""
        cache_dir = tmp_path / "cache"
        manifest_file = cache_dir / "manifest.json"
        monkeypatch.setattr("src.cache_manager.CACHE_DIR", cache_dir)
        monkeypatch.setattr("src.cache_manager.MANIFEST_FILE", manifest_file)

        save_to_cache("Source 1", 0, "content1", "url1", "hash1")
        save_to_cache("Source 2", 1, "content2", "url2", "hash2")

        assert (cache_dir / "source_0.txt").exists()
        assert (cache_dir / "source_1.txt").exists()

        manifest = load_manifest()
        assert len(manifest["sources"]) == 2


class TestLoadFromCache:
    """Tests for loading source content from cache."""

    def test_load_returns_lines(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test load_from_cache returns line iterator."""
        cache_dir = tmp_path / "cache"
        manifest_file = cache_dir / "manifest.json"
        monkeypatch.setattr("src.cache_manager.CACHE_DIR", cache_dir)
        monkeypatch.setattr("src.cache_manager.MANIFEST_FILE", manifest_file)

        save_to_cache("Test Source", 0, "line1\nline2\nline3", "url", "hash")

        lines = list(load_from_cache("Test Source"))
        assert lines == ["line1", "line2", "line3"]

    def test_load_missing_source_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test load_from_cache raises KeyError for missing source."""
        cache_dir = tmp_path / "cache"
        manifest_file = cache_dir / "manifest.json"
        cache_dir.mkdir()
        manifest_file.write_text('{"sources": {}}')
        monkeypatch.setattr("src.cache_manager.CACHE_DIR", cache_dir)
        monkeypatch.setattr("src.cache_manager.MANIFEST_FILE", manifest_file)

        with pytest.raises(KeyError):
            list(load_from_cache("Nonexistent Source"))

    def test_load_no_cache_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test load_from_cache raises FileNotFoundError when no cache."""
        monkeypatch.setattr("src.cache_manager.CACHE_DIR", tmp_path / "cache")
        monkeypatch.setattr("src.cache_manager.MANIFEST_FILE", tmp_path / "cache" / "manifest.json")

        with pytest.raises(FileNotFoundError):
            list(load_from_cache("Any Source"))


class TestValidateCache:
    """Tests for cache validation."""

    def test_validate_empty_cache(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test validate_cache returns all sources as missing when no cache."""
        monkeypatch.setattr("src.cache_manager.CACHE_DIR", tmp_path / "cache")
        monkeypatch.setattr("src.cache_manager.MANIFEST_FILE", tmp_path / "cache" / "manifest.json")

        is_valid, missing = validate_cache(["Source 1", "Source 2"])
        assert is_valid is False
        assert missing == ["Source 1", "Source 2"]

    def test_validate_complete_cache(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test validate_cache returns True when all sources present."""
        cache_dir = tmp_path / "cache"
        manifest_file = cache_dir / "manifest.json"
        monkeypatch.setattr("src.cache_manager.CACHE_DIR", cache_dir)
        monkeypatch.setattr("src.cache_manager.MANIFEST_FILE", manifest_file)

        save_to_cache("Source 1", 0, "content1", "url1", "hash1")
        save_to_cache("Source 2", 1, "content2", "url2", "hash2")

        is_valid, missing = validate_cache(["Source 1", "Source 2"])
        assert is_valid is True
        assert missing == []

    def test_validate_partial_cache(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test validate_cache returns missing sources."""
        cache_dir = tmp_path / "cache"
        manifest_file = cache_dir / "manifest.json"
        monkeypatch.setattr("src.cache_manager.CACHE_DIR", cache_dir)
        monkeypatch.setattr("src.cache_manager.MANIFEST_FILE", manifest_file)

        save_to_cache("Source 1", 0, "content1", "url1", "hash1")

        is_valid, missing = validate_cache(["Source 1", "Source 2", "Source 3"])
        assert is_valid is False
        assert missing == ["Source 2", "Source 3"]


class TestGetCachedSources:
    """Tests for getting cached source metadata."""

    def test_get_empty_when_no_cache(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test get_cached_sources returns empty dict when no cache."""
        monkeypatch.setattr("src.cache_manager.CACHE_DIR", tmp_path / "cache")
        monkeypatch.setattr("src.cache_manager.MANIFEST_FILE", tmp_path / "cache" / "manifest.json")

        result = get_cached_sources()
        assert result == {}

    def test_get_cached_sources(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test get_cached_sources returns CachedSource objects."""
        cache_dir = tmp_path / "cache"
        manifest_file = cache_dir / "manifest.json"
        monkeypatch.setattr("src.cache_manager.CACHE_DIR", cache_dir)
        monkeypatch.setattr("src.cache_manager.MANIFEST_FILE", manifest_file)

        save_to_cache("Test Source", 0, "content", "https://example.com", "hash123")

        result = get_cached_sources()
        assert "Test Source" in result
        assert result["Test Source"].cache_file == "source_0.txt"
        assert result["Test Source"].url == "https://example.com"
        assert result["Test Source"].content_hash == "hash123"


class TestGetCacheStats:
    """Tests for getting cache statistics."""

    def test_stats_when_no_cache(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test get_cache_stats returns empty stats when no cache."""
        monkeypatch.setattr("src.cache_manager.CACHE_DIR", tmp_path / "cache")
        monkeypatch.setattr("src.cache_manager.MANIFEST_FILE", tmp_path / "cache" / "manifest.json")

        stats = get_cache_stats()
        assert stats["exists"] is False
        assert stats["source_count"] == 0
        assert stats["cached_at"] is None

    def test_stats_with_cache(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test get_cache_stats returns correct stats."""
        cache_dir = tmp_path / "cache"
        manifest_file = cache_dir / "manifest.json"
        monkeypatch.setattr("src.cache_manager.CACHE_DIR", cache_dir)
        monkeypatch.setattr("src.cache_manager.MANIFEST_FILE", manifest_file)

        save_to_cache("Source 1", 0, "content1", "url1", "hash1")
        save_to_cache("Source 2", 1, "content2", "url2", "hash2")

        stats = get_cache_stats()
        assert stats["exists"] is True
        assert stats["source_count"] == 2
        assert stats["cached_at"] is not None
