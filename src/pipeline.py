"""Streaming domain deduplication and contribution analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import subprocess

from src.config import Whitelist


@dataclass(frozen=True)
class PipelineFiles:
    """Temporary file paths for annotated domain processing pipeline."""

    annotated: Path
    sorted: Path

    @classmethod
    def create(cls, base_dir: Path = Path()) -> PipelineFiles:
        """Create temp file paths for the processing pipeline."""
        return cls(
            annotated=base_dir / "temp_annotated.txt",
            sorted=base_dir / "temp_sorted.txt",
        )

    def cleanup(self) -> None:
        """Remove all temporary files."""
        self.annotated.unlink(missing_ok=True)
        self.sorted.unlink(missing_ok=True)


@dataclass
class ContributionStats:
    """Per-source contribution statistics for each category."""

    contrib_all: dict[str, int] = field(default_factory=dict)
    contrib_general: dict[str, int] = field(default_factory=dict)


def process_annotated_pipeline(
    pipeline: PipelineFiles,
    id_to_name: dict[int, str],
    whitelist: Whitelist,
    quiet: bool = False,
) -> tuple[int, int, ContributionStats, int]:
    """
    Process annotated stream through sort and streaming group-by pipeline.

    Single external sort by domain, then streaming group-by that:
    - Counts deduplicated domains for all configured sources
    - Counts deduplicated domains for general sources
    - Computes per-source contribution counters for both aggregates
    - Filters out whitelisted domains

    Contribution metric: domains appearing in exactly one source within each aggregate.
    This matches "how many domains would disappear if source were removed."

    Input format: domain<TAB>source_id<TAB>is_general (1 or 0)

    Args:
        pipeline: PipelineFiles containing input/output paths
        id_to_name: Mapping of source IDs to names
        whitelist: Whitelist object for domain filtering
        quiet: If True, suppress progress output

    Returns:
        Tuple of (all_count, general_count, ContributionStats, whitelisted_count)
    """
    if not quiet:
        print("  Sorting annotated stream...")

    subprocess.run(
        [
            "sort",
            "-t",
            "\t",
            "-k1,1",
            "-k2,2n",
            str(pipeline.annotated),
            "-o",
            str(pipeline.sorted),
        ],
        check=True,
    )

    if not quiet:
        print("  Streaming group-by with contribution calculation...")

    all_count = 0
    general_count = 0
    whitelisted_count = 0
    contrib_all: dict[str, int] = dict.fromkeys(id_to_name.values(), 0)
    contrib_general: dict[str, int] = dict.fromkeys(id_to_name.values(), 0)

    with pipeline.sorted.open("r", encoding="utf-8") as f_in:
        current_domain: str | None = None
        sources_all: set[int] = set()
        sources_general: set[int] = set()

        def flush_domain() -> None:
            """Process accumulated data for current domain and write outputs."""
            nonlocal all_count, general_count, whitelisted_count
            if current_domain is None:
                return

            if whitelist.is_whitelisted(current_domain):
                whitelisted_count += 1
                return

            all_count += 1

            if sources_general:
                general_count += 1

            if len(sources_all) == 1:
                only_source_id = next(iter(sources_all))
                contrib_all[id_to_name[only_source_id]] += 1

            if len(sources_general) == 1:
                only_source_id = next(iter(sources_general))
                contrib_general[id_to_name[only_source_id]] += 1

        for line in f_in:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 3:
                continue

            domain, source_id_str, is_general_str = parts
            source_id = int(source_id_str)
            is_general = is_general_str == "1"

            if domain != current_domain:
                flush_domain()
                current_domain = domain
                sources_all.clear()
                sources_general.clear()

            sources_all.add(source_id)
            if is_general:
                sources_general.add(source_id)

        flush_domain()

    stats = ContributionStats(contrib_all=contrib_all, contrib_general=contrib_general)
    return all_count, general_count, stats, whitelisted_count
