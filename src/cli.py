"""CLI orchestrator for YAHA.

Main entry point that knows all business logic:
- Fetching and normalizing configured host lists
- General and NSFW category analysis
- Deduplication, provenance, whitelist, and removal-candidate analysis
- README analytics generation
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

from src.config import SourceConfig, load_sources, load_whitelist
from src.domain_processor import extract_domains_from_lines
from src.fetcher import FetchError, fetch_url_with_hash
from src.pipeline import ContributionStats, PipelineFiles, process_annotated_pipeline
from src.state_manager import (
    AnalysisState,
    get_stale_sources,
    load_state,
    save_state,
    should_force_analysis,
    update_source_state,
)

MAX_WORKERS = 5
LOW_CONTRIBUTION_THRESHOLD = 50


def get_candidate_reasons(
    unique_contribution: int,
    days_since_change: int | None,
) -> list[str]:
    """Return the rules that make a source a removal candidate."""
    reasons = []
    if unique_contribution <= LOW_CONTRIBUTION_THRESHOLD:
        reasons.append(
            f"{unique_contribution:,} unique domain{'s' if unique_contribution != 1 else ''}"
        )
    if days_since_change is not None:
        reasons.append(f"unchanged {days_since_change} days")
    return reasons


def collect_sources(
    sources: list[SourceConfig],
    output_file: Path,
    state: AnalysisState,
) -> tuple[dict[str, int], dict[int, str], bool, list[str]]:
    """
    Fetch all sources, normalize domains, and update change-tracking state.

    Format per line: domain<TAB>source_id<TAB>is_general
    where is_general is 1 for non-NSFW sources and 0 otherwise.
    """
    source_stats: dict[str, int] = {}
    name_to_id = {s.name: idx for idx, s in enumerate(sources)}
    id_to_name = {idx: s.name for idx, s in enumerate(sources)}
    any_changed = False
    failed_sources: list[str] = []
    current_time = datetime.now(UTC)

    with (
        output_file.open("w", encoding="utf-8") as f_out,
        ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor,
    ):
        future_to_source = {executor.submit(fetch_url_with_hash, s.url): s for s in sources}

        for future in as_completed(future_to_source):
            source = future_to_source[future]
            is_nsfw = source.nsfw
            is_general_flag = 0 if is_nsfw else 1
            source_id = name_to_id[source.name]
            nsfw_tag = "  [NSFW]" if is_nsfw else ""

            print(f"Fetching {source.name}{nsfw_tag}...")

            try:
                content_hash, _raw_content, lines = future.result()

                changed = update_source_state(state, source, content_hash, current_time)
                if changed:
                    print("  Content CHANGED (hash mismatch)")
                    any_changed = True
                else:
                    print("  Content unchanged (hash match)")

                count = 0
                for domain in extract_domains_from_lines(lines):
                    f_out.write(f"{domain}\t{source_id}\t{is_general_flag}\n")
                    count += 1

                source_stats[source.name] = count
                print(f"  Found {count:,} domains")

            except FetchError as e:
                print(f"  Error: {e}", file=sys.stderr)
                source_stats[source.name] = 0
                failed_sources.append(source.name)

    return source_stats, id_to_name, any_changed, failed_sources


def update_readme(
    sources: list[SourceConfig],
    source_stats: dict[str, int],
    total_general: int,
    total_all: int,
    contribution_stats: ContributionStats,
    last_update: str,
    stale_sources: dict[str, int],
) -> None:
    """Update README with source statistics and removal-candidate analysis."""

    def build_table(source_list: list[SourceConfig], contributions: dict[str, int]) -> str:
        """Build HTML table for source statistics."""
        sorted_sources = sorted(
            source_list, key=lambda s: contributions.get(s.name, 0), reverse=True
        )

        rows = []
        for source in sorted_sources:
            total = source_stats.get(source.name, 0)
            unique = contributions.get(source.name, 0)
            candidate_reasons = get_candidate_reasons(
                unique,
                stale_sources.get(source.name),
            )
            candidate = (
                f"<strong>Yes</strong> — {'; '.join(candidate_reasons)}"
                if candidate_reasons
                else "No"
            )
            rows.append(
                f"<tr><td><a href='{source.url}'>{source.name}</a></td>"
                f"<td>{total:,}</td><td>{unique:,}</td><td>{candidate}</td></tr>"
            )

        return f"""<table align="center">
<!-- markdownlint-disable MD013 -->
<thead>
<tr>
<th>Source List</th>
<th>Total Domains</th>
<th>Unique Contribution</th>
<th>Removal Candidate</th>
</tr>
</thead>
<tbody>
{chr(10).join(rows)}
</tbody>
</table>
<!-- markdownlint-enable MD013 -->"""

    readme_path = Path("README.md")

    if not readme_path.exists():
        print("Warning: README.md not found", file=sys.stderr)
        return

    content = readme_path.read_text(encoding="utf-8")

    stats_start = content.find("<!-- STATS_START -->")
    stats_end = content.find("<!-- STATS_END -->")

    if stats_start == -1 or stats_end == -1:
        print("Warning: README.md missing stats markers", file=sys.stderr)
        return

    general_sources = [s for s in sources if not s.nsfw]
    nsfw_sources = [s for s in sources if s.nsfw]

    general_table = build_table(general_sources, contribution_stats.contrib_general)
    nsfw_table = build_table(nsfw_sources, contribution_stats.contrib_all)

    try:
        date_part, time_part, utc = last_update.split()
        last_update_badge = f"{date_part.replace('-', '--')}_{time_part}_{utc}"
    except ValueError:
        last_update_badge = last_update.replace(" ", "_").replace("-", "--")

    stats_section = f"""<!-- STATS_START -->

## Latest Run

<div align="center">

![General Domains](https://img.shields.io/badge/General_Domains-{total_general:,}-8be9fd?style=for-the-badge&labelColor=6272a4)
![Total Domains](https://img.shields.io/badge/Total_Domains_(with_NSFW)-{total_all:,}-ff79c6?style=for-the-badge&labelColor=6272a4)
![Last Updated](https://img.shields.io/badge/Last_Updated-{last_update_badge}-50fa7b?style=for-the-badge&labelColor=6272a4)

### General Host Lists

{general_table}

### NSFW Host Lists

{nsfw_table}

</div>

> [!NOTE]
> **Unique Contribution** is the number of domains that would disappear if a
> source were removed. A source is a **Removal Candidate** when it contributes
> 50 or fewer unique domains or has no observed content change for 30 days.
> Sources are never removed automatically.

<!-- STATS_END -->"""

    new_content = (
        content[:stats_start] + stats_section + content[stats_end + len("<!-- STATS_END -->") :]
    )

    ack_start = new_content.find("<!-- ACKNOWLEDGMENTS_START -->")
    ack_end = new_content.find("<!-- ACKNOWLEDGMENTS_END -->")

    if ack_start != -1 and ack_end != -1:
        acknowledgments = build_acknowledgments(sources)
        ack_section = f"""<!-- ACKNOWLEDGMENTS_START -->

Thanks to the maintainers of all source blocklists:

{acknowledgments}

<!-- ACKNOWLEDGMENTS_END -->"""

        new_content = (
            new_content[:ack_start]
            + ack_section
            + new_content[ack_end + len("<!-- ACKNOWLEDGMENTS_END -->") :]
        )

    readme_path.write_text(new_content, encoding="utf-8")
    print("Updated README.md with host-list analytics")


def build_acknowledgments(sources: list[SourceConfig]) -> str:
    """Build acknowledgments list from active sources."""
    maintainers: dict[str, tuple[str, str]] = {}

    for source in sources:
        if source.maintainer_name and source.maintainer_url and source.maintainer_description:
            maintainers.setdefault(
                source.maintainer_name,
                (source.maintainer_url, source.maintainer_description),
            )

    sorted_maintainers = sorted(maintainers.items())

    lines = []
    for name, (url, description) in sorted_maintainers:
        lines.append(f"- [{name}]({url}) - {description}")

    return "\n".join(lines) if lines else "No maintainer information available."


def main() -> int:
    """
    Fetch configured sources and update host-list analytics.

    Returns:
        Exit code: 0 on success, 1 on error
    """
    parser = argparse.ArgumentParser(
        description="YAHA - Host-List Analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force analysis even if no source changes are detected",
    )
    args = parser.parse_args()

    print("YAHA - Host-List Analyzer")
    print("=" * 50)

    current_time = datetime.now(UTC)

    try:
        print("\nLoading state from previous run...")
        state = load_state()
        print(f"  Previous analysis: {state.last_analysis or 'Never'}")
        print(f"  Total analyses: {state.analysis_count}")
        print(f"  Skipped analyses: {state.skipped_analyses}")

        print("\nLoading source configuration...")
        sources = load_sources()
        print(f"Loaded {len(sources)} source(s)")

        print("\nChecking source health...")
        stale_sources = get_stale_sources(state, sources, current_time)
        if stale_sources:
            print(f"  {len(stale_sources)} source(s) meet the staleness criterion")
        else:
            print("  No stale sources found")

        print("\nLoading whitelist...")
        whitelist = load_whitelist()
        total_wl = len(whitelist.exact) + len(whitelist.wildcards)
        if total_wl > 0:
            print(f"  Loaded {len(whitelist.exact)} exact, {len(whitelist.wildcards)} wildcard(s)")

        pipeline = PipelineFiles.create()
        print("\nFetching sources and computing hashes...")
        source_stats, id_to_name, any_changed, failed_sources = collect_sources(
            sources,
            pipeline.annotated,
            state,
        )
        if failed_sources:
            pipeline.cleanup()
            names = ", ".join(sorted(failed_sources))
            print(
                f"\nError: analysis aborted because source fetches failed: {names}",
                file=sys.stderr,
            )
            return 1
        stale_sources = get_stale_sources(state, sources, current_time)
        newly_stale = [
            name
            for name in stale_sources
            if not state.sources[name].metadata.get("stale_candidate_reported", False)
        ]

        force_analysis = (
            args.force or should_force_analysis(state, current_time) or bool(newly_stale)
        )

        if not any_changed and not force_analysis:
            print("\nNo changes detected - skipping analysis")
            print(f"Last analysis was at {state.last_analysis}")
            state.skipped_analyses += 1
            pipeline.cleanup()
            save_state(state)
            return 0

        if args.force:
            print("\nForcing analysis (--force)")
        elif newly_stale:
            print("\nRunning analysis for newly stale source(s)")
        elif force_analysis:
            print("\nRunning scheduled weekly analysis")
        else:
            print("\nSource changes detected - running analysis")

        print("\nAnalyzing deduplication and provenance...")
        all_count, general_count, contribution_stats, whitelisted_count = (
            process_annotated_pipeline(pipeline, id_to_name, whitelist)
        )

        print(f"\n  Total unique domains (general): {general_count:,}")
        print(f"  Total unique domains (all with NSFW): {all_count:,}")
        if whitelisted_count > 0:
            print(f"  Whitelisted domains (filtered): {whitelisted_count:,}")

        timestamp = current_time.strftime("%Y-%m-%d %H:%M:%S UTC")

        print("\nUpdating README...")
        update_readme(
            sources,
            source_stats,
            general_count,
            all_count,
            contribution_stats,
            timestamp,
            stale_sources,
        )
        for source in sources:
            source_state = state.sources.get(source.name)
            if source_state is None:
                continue
            contributions = (
                contribution_stats.contrib_all
                if source.nsfw
                else contribution_stats.contrib_general
            )
            unique = contributions.get(source.name, 0)
            candidate_reasons = get_candidate_reasons(
                unique,
                stale_sources.get(source.name),
            )
            source_state.metadata.update(
                {
                    "domain_count": source_stats.get(source.name, 0),
                    "unique_contribution": unique,
                    "removal_candidate": bool(candidate_reasons),
                    "candidate_reasons": candidate_reasons,
                }
            )
            if source.name in stale_sources:
                source_state.metadata["stale_candidate_reported"] = True
            else:
                source_state.metadata.pop("stale_candidate_reported", None)

        print("\nCleaning up temporary files...")
        pipeline.cleanup()

        state.last_analysis = current_time.isoformat()
        state.analysis_count += 1

        print("\nAnalysis complete")

        save_state(state)

        return 0

    except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
