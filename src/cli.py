"""CLI orchestrator for YAHA.

Main entry point that knows all business logic:
- Aggregating "blocklists"
- "NSFW" category handling
- Business rules (180-day purge, weekly compile)
- Output files: hosts, hosts_nsfw
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import sys
from typing import Any

from src.config import SourceConfig, load_sources, load_whitelist, save_sources
from src.domain_processor import ensure_psl_and_load, extract_domains_from_lines
from src.fetcher import FetchError, fetch_url_with_hash
from src.hosts_generator import format_count, generate_hosts_file_from_file
from src.pipeline import ContributionStats, PipelineFiles, process_annotated_pipeline
from src.state_manager import (
    check_stale_sources,
    load_state,
    save_state,
    should_force_compile,
    update_source_state,
)

MAX_WORKERS = 5


def build_header(
    title: str,
    total_domains: int,
    sources: list[SourceConfig],
    source_stats: dict[str, int],
    timestamp: str,
) -> list[str]:
    """Build header lines for hosts file with YAHA-specific formatting."""
    header = [
        "# YAHA - Yet Another Host Aggregator",
        f"# Compiled blocklist from multiple sources ({title})",
        "#",
        f"# Last Updated: {timestamp}",
        f"# Total Domains: {total_domains:,}",
        "#",
        "# Source Lists:",
    ]

    for source in sources:
        count = source_stats.get(source.name, 0)
        nsfw_flag = " [NSFW]" if source.nsfw else ""
        header.append(f"#   - {source.name}{nsfw_flag}: {count:,} domains")
        header.append(f"#     {source.url}")

    header.extend(["#", "# Usage: Add this URL to your blocklist subscriptions", "#"])
    return header


def collect_sources_with_hashes(
    sources: list[SourceConfig],
    output_file: Path,
    state: Any,
    psl: Any,
) -> tuple[dict[str, int], dict[int, str], dict[str, str], bool]:
    """
    Fetch all sources, compute hashes, and check for changes.

    Format per line: domain<TAB>source_id<TAB>is_general
    where is_general is 1 for non-NSFW sources and 0 otherwise.
    """
    source_stats: dict[str, int] = {}
    name_to_id = {s.name: idx for idx, s in enumerate(sources)}
    id_to_name = {idx: s.name for idx, s in enumerate(sources)}
    new_hashes: dict[str, str] = {}
    any_changed = False
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
                content_hash, lines = future.result()
                new_hashes[source.name] = content_hash

                # Check if hash changed and update state
                changed = update_source_state(state, source, content_hash, current_time)
                if changed:
                    print("  → Content CHANGED (hash mismatch)")
                    any_changed = True
                else:
                    print("  → Content unchanged (hash match)")

                # Write domains to annotated stream
                count = 0
                for domain in extract_domains_from_lines(lines, psl):
                    f_out.write(f"{domain}\t{source_id}\t{is_general_flag}\n")
                    count += 1

                source_stats[source.name] = count
                print(f"  → Found {count:,} domains")

            except FetchError as e:
                print(f"  → Error: {e}", file=sys.stderr)
                source_stats[source.name] = 0

    return source_stats, id_to_name, new_hashes, any_changed


def update_readme(
    sources: list[SourceConfig],
    source_stats: dict[str, int],
    total_general: int,
    total_all: int,
    contribution_stats: ContributionStats,
    last_update: str,
) -> None:
    """Update README with dual statistics tables (general and NSFW)."""

    def build_table(source_list: list[SourceConfig], contributions: dict[str, int]) -> str:
        """Build HTML table for source statistics."""
        sorted_sources = sorted(
            source_list, key=lambda s: contributions.get(s.name, 0), reverse=True
        )

        rows = []
        for source in sorted_sources:
            total = source_stats.get(source.name, 0)
            unique = contributions.get(source.name, 0)
            rows.append(
                f"<tr><td><a href='{source.url}'>{source.name}</a></td>"
                f"<td>{total:,}</td><td>{unique:,}</td></tr>"
            )

        return f"""<table align="center">
<thead>
<tr>
<th>Source List</th>
<th>Total Domains</th>
<th>Unique Contribution</th>
</tr>
</thead>
<tbody>
{chr(10).join(rows)}
</tbody>
</table>"""

    readme_path = Path("README.md")

    if not readme_path.exists():
        print("Warning: README.md not found", file=sys.stderr)
        return

    content = readme_path.read_text(encoding="utf-8")

    general_formatted = format_count(total_general)
    nsfw_formatted = format_count(total_all)

    replacements = [
        (
            r"(Use `hosts` for general protection \(~)[^)]+(\))",
            rf"\g<1>{general_formatted} domains\g<2>",
        ),
        (
            r"(Use `hosts_nsfw` for all the same domains in `hosts` "
            r"\*\*\*plus\*\*\* adult content \(\*\*~)[^)]+(\*\*\))",
            rf"\g<1>{nsfw_formatted} domains\g<2>",
        ),
    ]

    for pattern, replacement in replacements:
        content = re.sub(pattern, replacement, content)

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

### General Protection Lists

{general_table}

### NSFW Blocking Lists

{nsfw_table}

</div>

> [!NOTE]
> **Unique Contribution** shows how many domains would disappear if that source were removed.
> Sources with low unique counts (~50 or less) provide minimal value.

<!-- STATS_END -->"""

    new_content = (
        content[:stats_start] + stats_section + content[stats_end + len("<!-- STATS_END -->") :]
    )

    # Update acknowledgments section
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
    print("Updated README.md with dual statistics tables")


def build_acknowledgments(sources: list[SourceConfig]) -> str:
    """Build acknowledgments list from active sources."""
    maintainers: dict[str, tuple[str, str]] = {}

    for source in sources:
        has_maintainer = (
            source.maintainer_name and source.maintainer_url and source.maintainer_description
        )
        if (
            has_maintainer
            and source.maintainer_name is not None
            and source.maintainer_name not in maintainers
        ):
            # mypy doesn't understand the narrowing from has_maintainer check
            assert source.maintainer_url is not None
            assert source.maintainer_description is not None
            maintainers[source.maintainer_name] = (
                source.maintainer_url,
                source.maintainer_description,
            )

    sorted_maintainers = sorted(maintainers.items())

    lines = []
    for name, (url, desc) in sorted_maintainers:
        lines.append(f"- [{name}]({url}) - {desc}")

    return "\n".join(lines) if lines else "No maintainer information available."


def main() -> int:
    """
    Execute compilation with hash-based change detection.

    Returns:
        Exit code: 0 on success, 1 on error
    """
    parser = argparse.ArgumentParser(
        description="YAHA - Yet Another Host Aggregator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force recompilation even if no changes detected",
    )
    args = parser.parse_args()

    print("YAHA - Yet Another Host Aggregator")
    print("=" * 50)

    current_time = datetime.now(UTC)

    try:
        # Step 1: Load state
        print("\nLoading state from previous run...")
        state = load_state()
        print(f"  Previous compilation: {state.last_compilation or 'Never'}")
        print(f"  Total compilations: {state.compilation_count}")
        print(f"  Skipped compilations: {state.skipped_compilations}")

        # Step 2: Load and check for stale sources
        print("\nLoading source configuration...")
        sources = load_sources()
        print(f"Loaded {len(sources)} source(s)")

        print("\nChecking for stale sources...")
        sources, purge_occurred = check_stale_sources(state, sources, current_time)

        if purge_occurred:
            print("  Saving updated blocklists.json...")
            save_sources(sources)
            print(f"  Active sources after purge: {len(sources)}")
        else:
            print("  No stale sources found")

        # Step 3: Load whitelist
        print("\nLoading whitelist...")
        whitelist = load_whitelist()
        total_wl = len(whitelist.exact) + len(whitelist.wildcards)
        if total_wl > 0:
            print(f"  Loaded {len(whitelist.exact)} exact, {len(whitelist.wildcards)} wildcard(s)")

        # Step 4: Load Public Suffix List
        print("\nLoading Public Suffix List...")
        psl = ensure_psl_and_load()
        print(
            f"  Loaded {len(psl.exact):,} exact, "
            f"{len(psl.wildcards):,} wildcard, "
            f"{len(psl.exceptions):,} exception rules"
        )

        # Step 5: Fetch + hash all sources concurrently
        blocklists_dir = Path("blocklists")
        blocklists_dir.mkdir(exist_ok=True)

        pipeline = PipelineFiles.create()

        print("\nFetching sources and computing hashes...")
        source_stats, id_to_name, _new_hashes, any_changed = collect_sources_with_hashes(
            sources, pipeline.annotated, state, psl
        )

        # Step 6: Decide whether to compile
        force_compile = args.force or should_force_compile(state, current_time)

        if not any_changed and not force_compile and not purge_occurred:
            print("\nNo changes detected - skipping compilation")
            print(f"Last compilation was at {state.last_compilation}")
            state.skipped_compilations += 1
            pipeline.cleanup()
            save_state(state)
            return 0

        if args.force:
            print("\nWARNING: Forcing compilation (--force flag)")
        elif force_compile:
            print("\nWARNING: Forcing compilation (weekly schedule)")
        elif purge_occurred:
            print("\nWARNING: Compiling due to purged sources")
        else:
            print("\nChanges detected - proceeding with compilation")

        # Step 7: Run full compilation pipeline
        hosts_path = blocklists_dir / "hosts"
        hosts_nsfw_path = blocklists_dir / "hosts_nsfw"

        print("\nProcessing through sort → group-by pipeline...")
        all_count, general_count, contribution_stats, whitelisted_count = (
            process_annotated_pipeline(pipeline, id_to_name, whitelist)
        )

        print(f"\n  Total unique domains (general): {general_count:,}")
        print(f"  Total unique domains (all with NSFW): {all_count:,}")
        if whitelisted_count > 0:
            print(f"  Whitelisted domains (filtered): {whitelisted_count:,}")

        print("\nGenerating hosts files...")
        timestamp = current_time.strftime("%Y-%m-%d %H:%M:%S UTC")

        general_sources = [s for s in sources if not s.nsfw]

        general_header = build_header(
            "GENERAL - No NSFW", general_count, general_sources, source_stats, timestamp
        )
        nsfw_header = build_header("INCLUDING NSFW", all_count, sources, source_stats, timestamp)

        generate_hosts_file_from_file(pipeline.domains_general, hosts_path, general_header)
        generate_hosts_file_from_file(pipeline.domains_all, hosts_nsfw_path, nsfw_header)

        print(f"  Wrote {general_count:,} domains to blocklists/hosts")
        print(f"  Wrote {all_count:,} domains to blocklists/hosts_nsfw")

        print("\nUpdating README...")
        update_readme(
            sources,
            source_stats,
            general_count,
            all_count,
            contribution_stats,
            timestamp,
        )

        print("\nCleaning up temporary files...")
        pipeline.cleanup()

        # Update compilation stats
        state.last_compilation = current_time.isoformat()
        state.compilation_count += 1

        print("\nCompilation complete")

        # Save state
        save_state(state)

        return 0

    except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
