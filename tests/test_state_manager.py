"""Tests for src/state_manager.py.

Tests state persistence, staleness detection, and analysis scheduling.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from src.config import SourceConfig
from src.state_manager import (
    AnalysisState,
    SourceState,
    get_stale_sources,
    load_state,
    save_state,
    should_force_analysis,
    update_source_state,
)


class TestStatePersistence:
    """Tests for state save/load roundtrip."""

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        """Test state survives save/load cycle."""
        state_file = tmp_path / "state.json"
        state = AnalysisState(
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
            analysis_count=50,
        )

        save_state(state, state_file)
        loaded = load_state(state_file)

        assert loaded.sources["Source1"].content_hash == "abc123"
        assert loaded.analysis_count == 50

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        """Test missing state file returns empty state."""
        state = load_state(tmp_path / "nonexistent.json")

        assert state.sources == {}
        assert state.analysis_count == 0

    def test_corrupt_json_returns_empty(self, tmp_path: Path) -> None:
        """Test corrupt JSON returns empty state (graceful recovery)."""
        state_file = tmp_path / "state.json"
        state_file.write_text("{ invalid json }")

        state = load_state(state_file)

        assert state.sources == {}


class TestGetStaleSources:
    """Tests for staleness detection logic."""

    def test_fresh_source_not_flagged(self) -> None:
        """Test recently-updated sources are not flagged."""
        now = datetime.now(UTC)
        state = AnalysisState(
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

        stale = get_stale_sources(state, sources, now)

        assert stale == {}

    def test_stale_source_flagged_without_mutation(self) -> None:
        """Test sources unchanged for 30 days are flagged but retained."""
        now = datetime.now(UTC)
        old_date = (now - timedelta(days=30)).isoformat()
        state = AnalysisState(
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

        stale = get_stale_sources(state, sources, now)

        assert stale == {"Stale": 30}
        assert "Stale" in state.sources

    def test_source_just_under_threshold_not_flagged(self) -> None:
        """Test a source just under the threshold is not flagged."""
        now = datetime.now(UTC)
        old_date = (now - timedelta(days=29, hours=23)).isoformat()
        state = AnalysisState(
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
        sources = [SourceConfig(name="Preserved", url="https://example.com")]

        stale = get_stale_sources(state, sources, now)

        assert stale == {}


class TestShouldForceAnalysis:
    """Tests for forced analysis scheduling."""

    def test_first_run_forces(self) -> None:
        """Test first run without prior analysis forces execution."""
        state = AnalysisState()
        now = datetime.now(UTC)

        assert should_force_analysis(state, now) is True

    def test_recent_analysis_skips(self) -> None:
        """Test recent analysis doesn't force."""
        now = datetime.now(UTC)
        recent = (now - timedelta(hours=1)).isoformat()
        state = AnalysisState(last_analysis=recent)

        assert should_force_analysis(state, now) is False

    def test_old_analysis_forces(self) -> None:
        """Test more than seven days since analysis forces a new run."""
        now = datetime.now(UTC)
        old = (now - timedelta(days=8)).isoformat()
        state = AnalysisState(last_analysis=old)

        assert should_force_analysis(state, now) is True


class TestUpdateSourceState:
    """Tests for source state update logic."""

    def test_new_source_marks_changed(self) -> None:
        """Test new source is marked as changed."""
        state = AnalysisState()
        source = SourceConfig(name="New", url="https://example.com")
        now = datetime.now(UTC)

        changed = update_source_state(state, source, "hash123", now)

        assert changed is True
        assert "New" in state.sources
        assert state.sources["New"].content_hash == "hash123"

    def test_unchanged_hash_not_changed(self) -> None:
        """Test same hash doesn't mark changed."""
        now = datetime.now(UTC)
        state = AnalysisState(
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
        assert state.sources["Existing"].change_count == 2

    def test_different_hash_marks_changed(self) -> None:
        """Test different hash marks changed."""
        now = datetime.now(UTC)
        state = AnalysisState(
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
