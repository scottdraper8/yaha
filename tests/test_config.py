"""Tests for src/config.py.

Tests configuration loading, validation, and whitelist matching.
"""

from pathlib import Path

import pytest

from src.config import SourceConfig, Whitelist, load_sources, load_whitelist, save_sources


class TestSourceConfig:
    """Tests for SourceConfig dataclass serialization."""

    def test_roundtrip(self) -> None:
        """Test from_dict and to_dict preserve data."""
        data = {
            "name": "Test List",
            "url": "https://example.com/list.txt",
            "nsfw": True,
            "preserve": True,
        }
        config = SourceConfig.from_dict(data)
        result = config.to_dict()

        assert result["name"] == "Test List"
        assert result["nsfw"] is True

    def test_defaults(self) -> None:
        """Test default values for optional fields."""
        config = SourceConfig.from_dict({"name": "Test", "url": "https://x.com"})

        assert config.nsfw is False
        assert config.preserve is False
        assert config.maintainer_name is None


class TestWhitelist:
    """Tests for Whitelist matching logic - core functionality."""

    def test_exact_match(self) -> None:
        """Test exact domain matching."""
        whitelist = Whitelist(exact={"example.com"}, wildcards=[])

        assert whitelist.is_whitelisted("example.com") is True
        assert whitelist.is_whitelisted("other.com") is False

    def test_wildcard_match(self) -> None:
        """Test wildcard matching for subdomains."""
        whitelist = Whitelist(exact=set(), wildcards=["*.example.com"])

        assert whitelist.is_whitelisted("foo.example.com") is True
        assert whitelist.is_whitelisted("example.com") is True  # Base domain matches
        assert whitelist.is_whitelisted("notexample.com") is False
        assert whitelist.is_whitelisted("fooexample.com") is False  # Not a subdomain

    def test_empty_whitelist(self) -> None:
        """Test empty whitelist matches nothing."""
        assert Whitelist().is_whitelisted("anything.com") is False


class TestLoadSources:
    """Tests for load_sources validation logic."""

    def test_load_valid_config(self, tmp_path: Path, sample_blocklists_json: str) -> None:
        """Test loading valid config file."""
        config_file = tmp_path / "blocklists.json"
        config_file.write_text(sample_blocklists_json)

        sources = load_sources(config_file)

        assert len(sources) == 3
        assert sources[0].name == "Test List 1"

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        """Test missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_sources(tmp_path / "nonexistent.json")

    def test_not_array_raises(self, tmp_path: Path) -> None:
        """Test non-array JSON raises ValueError."""
        config_file = tmp_path / "blocklists.json"
        config_file.write_text('{"name": "test"}')

        with pytest.raises(ValueError, match="must contain a JSON array"):
            load_sources(config_file)

    def test_missing_required_field_raises(self, tmp_path: Path) -> None:
        """Test missing required field raises ValueError."""
        config_file = tmp_path / "blocklists.json"
        config_file.write_text('[{"name": "Test"}]')  # Missing 'url'

        with pytest.raises(ValueError, match="missing 'name' or 'url'"):
            load_sources(config_file)


class TestSaveSources:
    """Tests for save_sources."""

    def test_roundtrip(self, tmp_path: Path) -> None:
        """Test save and reload preserves data."""
        config_file = tmp_path / "blocklists.json"
        sources = [
            SourceConfig(name="List 1", url="https://example.com/1.txt"),
            SourceConfig(name="List 2", url="https://example.com/2.txt", nsfw=True),
        ]

        save_sources(sources, config_file)
        loaded = load_sources(config_file)

        assert len(loaded) == 2
        assert loaded[1].nsfw is True


class TestLoadWhitelist:
    """Tests for load_whitelist parsing."""

    def test_load_valid_whitelist(self, tmp_path: Path) -> None:
        """Test loading whitelist file."""
        whitelist_file = tmp_path / "whitelist.txt"
        whitelist_file.write_text("example.com\n*.wildcard.org\n# comment\n")

        whitelist = load_whitelist(whitelist_file)

        assert "example.com" in whitelist.exact
        assert "*.wildcard.org" in whitelist.wildcards

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        """Test missing whitelist returns empty (graceful)."""
        whitelist = load_whitelist(tmp_path / "nonexistent.txt")

        assert len(whitelist.exact) == 0
        assert len(whitelist.wildcards) == 0

    def test_lowercases_domains(self, tmp_path: Path) -> None:
        """Test domains are lowercased."""
        whitelist_file = tmp_path / "whitelist.txt"
        whitelist_file.write_text("EXAMPLE.COM")

        whitelist = load_whitelist(whitelist_file)

        assert "example.com" in whitelist.exact
