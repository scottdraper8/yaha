"""Tests for src/state_manager.py.

Tests state persistence, staleness detection, and force compile logic.
"""

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

from src.config import SourceConfig
from src.state_manager import (
    CompilationState,
    SourceState,
    check_stale_sources,
    load_state,
    save_state,
    should_force_compile,
    update_source_state,
)


class TestStatePersistence:
    """Tests for state save/load roundtrip."""

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        """Test state survives save/load cycle."""
        state_file = tmp_path / "state.json"
        state = CompilationState(
            sources={
                "Source1": SourceState(
                    url="https://example.com",
                    content_hash="abc123",
                    last_fetch_date="2026-01-26",
                    last_changed_date="2026-01-26",
                    fetch_count=5,
                    change_count=3,
                )
            },
            compilation_count=50,
        )

        save_state(state, state_file)
        loaded = load_state(state_file)

        assert loaded.sources["Source1"].content_hash == "abc123"
        assert loaded.compilation_count == 50

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        """Test missing state file returns empty state."""
        state = load_state(tmp_path / "nonexistent.json")

        assert state.sources == {}
        assert state.compilation_count == 0

    def test_corrupt_json_returns_empty(self, tmp_path: Path) -> None:
        """Test corrupt JSON returns empty state (graceful recovery)."""
        state_file = tmp_path / "state.json"
        state_file.write_text("{ invalid json }")

        state = load_state(state_file)

        assert state.sources == {}

    def test_legacy_format_migration(self, tmp_path: Path) -> None:
        """Test loading legacy 'lists' format migrates to 'sources'."""
        state_file = tmp_path / "state.json"
        state_file.write_text(
            json.dumps(
                {
                    "lists": {  # Old key
                        "Source1": {
                            "url": "https://example.com",
                            "content_hash": "abc",
                            "last_fetch_date": "2026-01-26",
                            "last_changed_date": "2026-01-26",
                            "fetch_count": 1,
                            "change_count": 1,
                        }
                    },
                    "compilation_count": 5,
                }
            )
        )

        state = load_state(state_file)

        assert "Source1" in state.sources


class TestCheckStaleSources:
    """Tests for staleness detection logic."""

    def test_fresh_source_not_purged(self) -> None:
        """Test recently-updated sources are kept."""
        now = datetime.now(UTC)
        state = CompilationState(
            sources={
                "Fresh": SourceState(
                    url="https://example.com",
                    content_hash="abc",
                    last_fetch_date=now.isoformat(),
                    last_changed_date=now.isoformat(),
                    fetch_count=1,
                    change_count=1,
                )
            }
        )
        sources = [SourceConfig(name="Fresh", url="https://example.com")]

        active, purged = check_stale_sources(state, sources, now, quiet=True)

        assert len(active) == 1
        assert purged is False

    def test_stale_source_purged(self) -> None:
        """Test sources without updates for 180+ days are purged."""
        now = datetime.now(UTC)
        old_date = (now - timedelta(days=200)).isoformat()
        state = CompilationState(
            sources={
                "Stale": SourceState(
                    url="https://example.com",
                    content_hash="abc",
                    last_fetch_date=old_date,
                    last_changed_date=old_date,
                    fetch_count=1,
                    change_count=1,
                )
            }
        )
        sources = [SourceConfig(name="Stale", url="https://example.com")]

        active, purged = check_stale_sources(state, sources, now, quiet=True)

        assert len(active) == 0
        assert purged is True
        assert "Stale" not in state.sources

    def test_preserved_source_never_purged(self) -> None:
        """Test sources with preserve=True are never purged."""
        now = datetime.now(UTC)
        old_date = (now - timedelta(days=200)).isoformat()
        state = CompilationState(
            sources={
                "Preserved": SourceState(
                    url="https://example.com",
                    content_hash="abc",
                    last_fetch_date=old_date,
                    last_changed_date=old_date,
                    fetch_count=1,
                    change_count=1,
                )
            }
        )
        sources = [SourceConfig(name="Preserved", url="https://example.com", preserve=True)]

        active, purged = check_stale_sources(state, sources, now, quiet=True)

        assert len(active) == 1
        assert purged is False


class TestShouldForceCompile:
    """Tests for force compile decision logic."""

    def test_first_run_forces(self) -> None:
        """Test first run (no prior compilation) forces compile."""
        state = CompilationState()
        now = datetime.now(UTC)

        assert should_force_compile(state, now) is True

    def test_recent_compile_skips(self) -> None:
        """Test recent compilation doesn't force."""
        now = datetime.now(UTC)
        recent = (now - timedelta(hours=1)).isoformat()
        state = CompilationState(last_compilation=recent)

        assert should_force_compile(state, now) is False

    def test_old_compile_forces(self) -> None:
        """Test >7 days since last compile forces."""
        now = datetime.now(UTC)
        old = (now - timedelta(days=8)).isoformat()
        state = CompilationState(last_compilation=old)

        assert should_force_compile(state, now) is True


class TestUpdateSourceState:
    """Tests for source state update logic."""

    def test_new_source_marks_changed(self) -> None:
        """Test new source is marked as changed."""
        state = CompilationState()
        source = SourceConfig(name="New", url="https://example.com")
        now = datetime.now(UTC)

        changed = update_source_state(state, source, "hash123", now)

        assert changed is True
        assert "New" in state.sources
        assert state.sources["New"].content_hash == "hash123"

    def test_unchanged_hash_not_changed(self) -> None:
        """Test same hash doesn't mark changed."""
        now = datetime.now(UTC)
        state = CompilationState(
            sources={
                "Existing": SourceState(
                    url="https://example.com",
                    content_hash="hash123",
                    last_fetch_date=(now - timedelta(hours=12)).isoformat(),
                    last_changed_date=(now - timedelta(days=1)).isoformat(),
                    fetch_count=5,
                    change_count=2,
                )
            }
        )
        source = SourceConfig(name="Existing", url="https://example.com")

        changed = update_source_state(state, source, "hash123", now)

        assert changed is False
        assert state.sources["Existing"].fetch_count == 6
        assert state.sources["Existing"].change_count == 2  # Unchanged

    def test_different_hash_marks_changed(self) -> None:
        """Test different hash marks changed."""
        now = datetime.now(UTC)
        state = CompilationState(
            sources={
                "Existing": SourceState(
                    url="https://example.com",
                    content_hash="old_hash",
                    last_fetch_date=(now - timedelta(hours=12)).isoformat(),
                    last_changed_date=(now - timedelta(days=1)).isoformat(),
                    fetch_count=5,
                    change_count=2,
                )
            }
        )
        source = SourceConfig(name="Existing", url="https://example.com")

        changed = update_source_state(state, source, "new_hash", now)

        assert changed is True
        assert state.sources["Existing"].change_count == 3
