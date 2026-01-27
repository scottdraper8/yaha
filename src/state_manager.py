"""State management for YAHA.

Handles persistence of compilation state, change detection, and staleness checks.
Minimal knowledge of business logic - treats source metadata as opaque.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from src.config import SourceConfig

STATE_FILE = Path("state.json")
STALE_THRESHOLD_DAYS = 180


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
class CompilationState:
    """Overall compilation state."""

    sources: dict[str, SourceState] = field(default_factory=dict)
    last_compilation: str = ""
    compilation_count: int = 0
    skipped_compilations: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "sources": {name: s.to_dict() for name, s in self.sources.items()},
            "last_compilation": self.last_compilation,
            "compilation_count": self.compilation_count,
            "skipped_compilations": self.skipped_compilations,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CompilationState:
        """Create from dictionary."""
        sources = {
            name: SourceState.from_dict(state_dict)
            for name, state_dict in data.get("sources", {}).items()
        }
        # Handle legacy "lists" key for backwards compatibility during migration
        if not sources and "lists" in data:
            sources = {
                name: SourceState.from_dict(state_dict)
                for name, state_dict in data.get("lists", {}).items()
            }
        return cls(
            sources=sources,
            last_compilation=data.get("last_compilation", ""),
            compilation_count=data.get("compilation_count", 0),
            skipped_compilations=data.get("skipped_compilations", 0),
        )


def load_state(state_path: Path = STATE_FILE) -> CompilationState:
    """Load state from disk, create new if missing or corrupt."""
    if not state_path.exists():
        return CompilationState()

    try:
        with state_path.open(encoding="utf-8") as f:
            data = json.load(f)
        return CompilationState.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError):
        # Corrupt state file - start fresh
        return CompilationState()


def save_state(state: CompilationState, state_path: Path = STATE_FILE) -> None:
    """Persist state to disk."""
    with state_path.open("w", encoding="utf-8") as f:
        json.dump(state.to_dict(), f, indent=2)


def check_stale_sources(
    state: CompilationState,
    sources: list[SourceConfig],
    current_time: datetime,
    threshold_days: int = STALE_THRESHOLD_DAYS,
    quiet: bool = False,
) -> tuple[list[SourceConfig], bool]:
    """
    Identify stale sources (no updates for threshold_days) and remove them.

    Sources with preserve=True are never considered stale.

    Args:
        state: Current compilation state
        sources: List of source configurations
        current_time: Current UTC datetime
        threshold_days: Number of days without updates to consider stale
        quiet: If True, suppress output

    Returns:
        Tuple of (active_sources, purge_occurred)
    """
    active_sources: list[SourceConfig] = []
    purged_any = False

    for source in sources:
        if source.preserve:
            active_sources.append(source)
            continue

        source_state = state.sources.get(source.name)

        if source_state and source_state.last_changed_date:
            try:
                last_changed = datetime.fromisoformat(
                    source_state.last_changed_date.replace("Z", "+00:00")
                )
                days_stale = (current_time - last_changed).days

                if days_stale > threshold_days:
                    if not quiet:
                        print(f"WARNING: Purging stale source: {source.name}")
                        print(
                            f"         No updates for {days_stale} days "
                            f"(threshold: {threshold_days})"
                        )

                    del state.sources[source.name]
                    purged_any = True
                    continue
            except ValueError:
                pass  # Invalid date format - don't purge

        active_sources.append(source)

    return active_sources, purged_any


def should_force_compile(state: CompilationState, current_time: datetime) -> bool:
    """
    Check if compilation should be forced regardless of changes.

    Forces compilation if:
    - First run (no previous compilation)
    - More than 7 days since last compilation
    - Sunday at midnight UTC (weekly schedule)

    Args:
        state: Current compilation state
        current_time: Current UTC datetime

    Returns:
        True if compilation should be forced
    """
    if not state.last_compilation:
        return True

    try:
        last_compile = datetime.fromisoformat(state.last_compilation.replace("Z", "+00:00"))
    except ValueError:
        return True  # Invalid date - force compile

    hours_since = (current_time - last_compile).total_seconds() / 3600
    is_sunday_midnight = current_time.weekday() == 6 and current_time.hour == 0

    return hours_since >= 168 or is_sunday_midnight  # 168 hours = 7 days


def update_source_state(
    state: CompilationState,
    source: SourceConfig,
    content_hash: str,
    current_time: datetime,
) -> bool:
    """
    Update state for a fetched source.

    Args:
        state: Compilation state to update
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
