"""State management for YAHA.

Handles persistence of analysis state, change detection, and source health checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from src.config import SourceConfig

STATE_FILE = Path("state.json")
STALE_THRESHOLD_DAYS = 30
ANALYSIS_INTERVAL_DAYS = 7


@dataclass
class SourceState:
    """State tracking for a single source."""

    url: str
    content_hash: str
    last_fetch_date: str
    last_changed_date: str
    fetch_count: int
    change_count: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "url": self.url,
            "content_hash": self.content_hash,
            "last_fetch_date": self.last_fetch_date,
            "last_changed_date": self.last_changed_date,
            "fetch_count": self.fetch_count,
            "change_count": self.change_count,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceState:
        """Create from dictionary."""
        return cls(
            url=data.get("url", ""),
            content_hash=data.get("content_hash", ""),
            last_fetch_date=data.get("last_fetch_date", ""),
            last_changed_date=data.get("last_changed_date", ""),
            fetch_count=data.get("fetch_count", 0),
            change_count=data.get("change_count", 0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class AnalysisState:
    """Persistent state for recurring host-list analysis."""

    sources: dict[str, SourceState] = field(default_factory=dict)
    last_analysis: str = ""
    analysis_count: int = 0
    skipped_analyses: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "sources": {name: s.to_dict() for name, s in self.sources.items()},
            "last_analysis": self.last_analysis,
            "analysis_count": self.analysis_count,
            "skipped_analyses": self.skipped_analyses,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnalysisState:
        """Create from dictionary."""
        sources = {
            name: SourceState.from_dict(state_dict)
            for name, state_dict in data.get("sources", {}).items()
        }
        return cls(
            sources=sources,
            last_analysis=data.get("last_analysis", ""),
            analysis_count=data.get("analysis_count", 0),
            skipped_analyses=data.get("skipped_analyses", 0),
        )


def load_state(state_path: Path = STATE_FILE) -> AnalysisState:
    """Load state from disk, create new if missing or corrupt."""
    if not state_path.exists():
        return AnalysisState()

    try:
        with state_path.open(encoding="utf-8") as f:
            data = json.load(f)
        return AnalysisState.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError):
        return AnalysisState()


def save_state(state: AnalysisState, state_path: Path = STATE_FILE) -> None:
    """Persist state to disk."""
    with state_path.open("w", encoding="utf-8") as f:
        json.dump(state.to_dict(), f, indent=2)
        f.write("\n")


def get_stale_sources(
    state: AnalysisState,
    sources: list[SourceConfig],
    current_time: datetime,
    threshold_days: int = STALE_THRESHOLD_DAYS,
) -> dict[str, int]:
    """
    Identify sources whose fetched content has not changed recently.

    Args:
        state: Current analysis state
        sources: List of source configurations
        current_time: Current UTC datetime
        threshold_days: Number of days without updates to consider stale
    Returns:
        Mapping of source names to whole days since their last observed change.
    """
    stale_sources: dict[str, int] = {}

    for source in sources:
        source_state = state.sources.get(source.name)

        if source_state and source_state.last_changed_date:
            try:
                last_changed = datetime.fromisoformat(
                    source_state.last_changed_date.replace("Z", "+00:00")
                )
                if last_changed.tzinfo is None and current_time.tzinfo is not None:
                    last_changed = last_changed.replace(tzinfo=current_time.tzinfo)
                days_stale = int((current_time - last_changed).total_seconds() // 86400)

                if days_stale >= threshold_days:
                    stale_sources[source.name] = days_stale
            except ValueError:
                pass

    return stale_sources


def should_force_analysis(state: AnalysisState, current_time: datetime) -> bool:
    """
    Check if analysis should run regardless of source changes.

    Forces analysis if:
    - First run (no previous analysis)
    - More than 7 days since the last analysis

    Args:
        state: Current analysis state
        current_time: Current UTC datetime

    Returns:
        True if analysis should be forced
    """
    if not state.last_analysis:
        return True

    try:
        last_analysis = datetime.fromisoformat(state.last_analysis.replace("Z", "+00:00"))
    except ValueError:
        return True

    hours_since = (current_time - last_analysis).total_seconds() / 3600
    return hours_since >= ANALYSIS_INTERVAL_DAYS * 24


def update_source_state(
    state: AnalysisState,
    source: SourceConfig,
    content_hash: str,
    current_time: datetime,
) -> bool:
    """
    Update state for a fetched source.

    Args:
        state: Analysis state to update
        source: Source configuration
        content_hash: SHA256 hash of fetched content
        current_time: Current UTC datetime

    Returns:
        True if content changed, False otherwise
    """
    existing = state.sources.get(source.name)

    if existing:
        changed = existing.content_hash != content_hash
        existing.last_fetch_date = current_time.isoformat()
        existing.fetch_count += 1

        if changed:
            existing.content_hash = content_hash
            existing.last_changed_date = current_time.isoformat()
            existing.change_count += 1
            existing.metadata.pop("stale_candidate_reported", None)

        return changed
    else:
        state.sources[source.name] = SourceState(
            url=source.url,
            content_hash=content_hash,
            last_fetch_date=current_time.isoformat(),
            last_changed_date=current_time.isoformat(),
            fetch_count=1,
            change_count=1,
        )
        return True
