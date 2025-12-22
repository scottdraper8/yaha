#!/usr/bin/env python3
"""
YAHA - Yet Another Host Aggregator
Compiles multiple blocklists into a single unified hosts file.
"""

import json
import re
import sys
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from curl_cffi import requests

MAX_WORKERS = 5
REQUEST_TIMEOUT = 30


@dataclass(frozen=True)
class PipelineFiles:
    """Temporary file paths for annotated domain processing pipeline."""

    annotated: Path
    sorted: Path
    domains_all: Path
    domains_general: Path

    @classmethod
    def create(cls) -> "PipelineFiles":
        """Create temp file paths for the processing pipeline."""
        return cls(
            annotated=Path("temp_annotated.txt"),
            sorted=Path("temp_sorted.txt"),
            domains_all=Path("temp_domains_all.txt"),
            domains_general=Path("temp_domains_general.txt"),
        )

    def cleanup(self) -> None:
        """Remove all temporary files."""
        self.annotated.unlink(missing_ok=True)
        self.sorted.unlink(missing_ok=True)
        self.domains_all.unlink(missing_ok=True)
        self.domains_general.unlink(missing_ok=True)


@dataclass
class ContributionStats:
    """Per-list contribution statistics for both aggregates."""

    contrib_all: dict[str, int]
    contrib_general: dict[str, int]


# Domain validation per RFC 1035: max 253 chars total, 63 per label
_DOMAIN_REGEX = r"[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*"

HOSTS_PATTERN = re.compile(
    rf"^(?:0\.0\.0\.0|127\.0\.0\.1|::1?)[\s\t]+({_DOMAIN_REGEX})"
)
RAW_DOMAIN_PATTERN = re.compile(rf"^({_DOMAIN_REGEX})$")
ADBLOCK_PATTERN = re.compile(rf"^\|\|({_DOMAIN_REGEX})\^")


def fetch_blocklist_stream(name: str, url: str, timeout: int = REQUEST_TIMEOUT):
    """
    Fetch blocklist content from URL and return line iterator.

    curl_cffi doesn't support true streaming (iter_content raises NotImplementedError).
    Fetch full response but yield lines one at a time to minimize memory overhead.

    Args:
        name: Name of the blocklist
        url: URL of the blocklist
        timeout: Request timeout in seconds

    Returns:
        Tuple of (name, url, line iterator)

    Raises:
        Exception: If request fails
    """
    try:
        response = requests.get(
            url,
            timeout=timeout,
            impersonate="chrome120",
            verify=True,
            stream=False,
        )
        response.raise_for_status()

        response_text = response.text

        def line_generator():
            for line in response_text.split("\n"):
                yield line.rstrip("\r")

        return name, url, line_generator()
    except Exception as e:
        raise Exception(f"Failed to fetch {name}: {str(e)}") from e


def is_valid_domain(domain: str) -> bool:
    """
    Validate domain structure per RFC 1035.

    Check for proper TLD, label length, hyphen placement, and format.
    """
    if not domain or len(domain) > 253:
        return False

    if "." not in domain or domain.startswith(".") or domain.endswith("."):
        return False

    if ".." in domain:
        return False

    labels = domain.split(".")
    for label in labels:
        if not label or len(label) > 63:
            return False
        if label.startswith("-") or label.endswith("-"):
            return False

    return True


def parse_domains_stream(lines):
    """
    Extract domains from line iterator, yielding one at a time.

    Support hosts files, raw domain lists, and Adblock Plus filters.

    Args:
        lines: Iterator of lines from blocklist

    Yields:
        Individual domain names
    """
    patterns = [ADBLOCK_PATTERN, HOSTS_PATTERN, RAW_DOMAIN_PATTERN]
    localhost_prefixes = [
        "127.0.0.1 localhost",
        "::1 localhost",
        "0.0.0.0 localhost",
        "::1 ip6-localhost",
        "::1 ip6-loopback",
    ]

    for line in lines:
        if not line:
            continue
        line = line.strip()

        if not line or line.startswith(("#", "!", "[")):
            continue

        if any(line.startswith(prefix) for prefix in localhost_prefixes):
            continue

        for pattern in patterns:
            match = pattern.match(line)
            if match:
                domain = match.group(1).lower()
                if is_valid_domain(domain):
                    yield domain
                break


def load_blocklists() -> list[dict[str, str]]:
    """
    Load blocklist configuration from JSON file.

    Returns:
        List of blocklist configurations

    Raises:
        FileNotFoundError: If blocklists.json not found
        json.JSONDecodeError: If JSON is invalid
        ValueError: If JSON structure is invalid
    """
    config_path = Path("blocklists.json")
    if not config_path.exists():
        raise FileNotFoundError(
            "blocklists.json not found. Please create it with blocklist configurations."
        )

    with config_path.open() as f:
        blocklists = json.load(f)

    if not isinstance(blocklists, list):
        raise ValueError("blocklists.json must contain a JSON array")

    for idx, blocklist in enumerate(blocklists, 1):
        if not isinstance(blocklist, dict):
            raise ValueError(f"Entry {idx} must be a JSON object")
        if "name" not in blocklist or "url" not in blocklist:
            raise ValueError(f"Entry {idx} missing 'name' or 'url' field")
        if "nsfw" in blocklist and not isinstance(blocklist["nsfw"], bool):
            raise ValueError(f"Entry {idx}: 'nsfw' field must be a boolean value")

    return blocklists


def filter_blocklists_by_nsfw(
    blocklists: list[dict[str, str]], include_nsfw: bool
) -> list[dict[str, str]]:
    """
    Filter blocklist configuration by NSFW flag.

    Args:
        blocklists: List of blocklist configurations
        include_nsfw: If True, return NSFW lists; if False, return non-NSFW lists

    Returns:
        Filtered list of blocklist configurations
    """
    return [bl for bl in blocklists if bl.get("nsfw", False) == include_nsfw]


def collect_blocklists_annotated(
    blocklists: list[dict[str, str]],
    output_file: Path,
) -> tuple[dict[str, int], dict[int, str]]:
    """
    Fetch all blocklists and emit annotated stream to disk.

    Format per line: domain<TAB>list_id<TAB>is_general
    where is_general is 1 for non-NSFW lists and 0 otherwise.

    Args:
        blocklists: List of blocklist configurations
        output_file: Path to write annotated stream

    Returns:
        Tuple of (domain count per list, list_id to name mapping)
    """
    list_stats: dict[str, int] = {}
    name_to_id = {bl["name"]: idx for idx, bl in enumerate(blocklists)}
    id_to_name = {idx: bl["name"] for idx, bl in enumerate(blocklists)}

    with output_file.open("w") as f_out:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_blocklist = {
                executor.submit(fetch_blocklist_stream, bl["name"], bl["url"]): bl
                for bl in blocklists
            }

            for future in as_completed(future_to_blocklist):
                blocklist = future_to_blocklist[future]
                name = blocklist["name"]
                is_nsfw = blocklist.get("nsfw", False)
                is_general_flag = 0 if is_nsfw else 1
                list_id = name_to_id[name]
                nsfw_tag = "  [NSFW]" if is_nsfw else ""

                print(f"Fetching {name}{nsfw_tag}...")

                try:
                    _, _, lines = future.result()

                    count = 0
                    for domain in parse_domains_stream(lines):
                        f_out.write(f"{domain}\t{list_id}\t{is_general_flag}\n")
                        count += 1

                    list_stats[name] = count
                    print(f"  → Found {count:,} domains")
                except Exception as e:
                    print(f"  → Error: {e}", file=sys.stderr)
                    list_stats[name] = 0

    return list_stats, id_to_name


def process_annotated_pipeline(
    pipeline: PipelineFiles,
    id_to_name: dict[int, str],
) -> tuple[int, int, ContributionStats]:
    """
    Process annotated stream through sort → streaming group-by pipeline.

    Single external sort by domain, then streaming group-by that:
    - Writes deduplicated domains to ALL output (sorted)
    - Writes deduplicated domains to GENERAL output (sorted, derived in same pass)
    - Computes per-list contribution counters for both aggregates

    Contribution metric: domains appearing in exactly one list within each aggregate.
    This matches "how many domains would disappear if list were removed."

    Args:
        pipeline: PipelineFiles containing input/output paths
        id_to_name: Mapping of list IDs to names

    Returns:
        Tuple of (all_count, general_count, ContributionStats)
    """
    # Sort by domain (primary), then list_id (secondary) for consistent grouping
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

    print("  Streaming group-by with contribution calculation...")
    all_count = 0
    general_count = 0
    contrib_all: dict[str, int] = {name: 0 for name in id_to_name.values()}
    contrib_general: dict[str, int] = {name: 0 for name in id_to_name.values()}

    with (
        pipeline.sorted.open("r") as f_in,
        pipeline.domains_all.open("w") as f_all,
        pipeline.domains_general.open("w") as f_gen,
    ):
        current_domain: str | None = None
        lists_all: set[int] = set()
        lists_general: set[int] = set()

        def flush_domain():
            """Process accumulated data for current domain and write outputs."""
            nonlocal all_count, general_count
            if current_domain is None:
                return

            # Write to ALL output (always)
            f_all.write(f"{current_domain}\n")
            all_count += 1

            # Write to GENERAL output only if at least one general list contains it
            if lists_general:
                f_gen.write(f"{current_domain}\n")
                general_count += 1

            # Update contribution counters: domains with frequency=1 in each aggregate
            if len(lists_all) == 1:
                only_list_id = next(iter(lists_all))
                contrib_all[id_to_name[only_list_id]] += 1

            if len(lists_general) == 1:
                only_list_id = next(iter(lists_general))
                contrib_general[id_to_name[only_list_id]] += 1

        for line in f_in:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 3:
                continue

            domain, list_id_str, is_general_str = parts
            list_id = int(list_id_str)
            is_general = is_general_str == "1"

            if domain != current_domain:
                flush_domain()
                current_domain = domain
                lists_all.clear()
                lists_general.clear()

            lists_all.add(list_id)
            if is_general:
                lists_general.add(list_id)

        # Flush final domain
        flush_domain()

    stats = ContributionStats(contrib_all=contrib_all, contrib_general=contrib_general)
    return all_count, general_count, stats


def format_domain_count(count: int) -> str:
    """
    Format domain count as human-readable string (e.g., "4.4M" for 4,400,000).

    Args:
        count: Domain count

    Returns:
        Formatted string
    """
    millions = count / 1_000_000
    return f"{millions:.1f}M"


def build_header(
    title: str,
    total_domains: int,
    blocklists: list[dict[str, str]],
    list_stats: dict[str, int],
    include_nsfw: bool,
    timestamp: str,
) -> list[str]:
    """
    Build header lines for hosts file.

    Args:
        title: Title for the hosts file (e.g., "GENERAL - No NSFW")
        total_domains: Total count of unique domains
        blocklists: List of blocklist configurations
        list_stats: Domain count per list
        include_nsfw: Whether to include NSFW lists in header
        timestamp: Last updated timestamp

    Returns:
        List of header lines
    """
    header = [
        "# YAHA - Yet Another Host Aggregator",
        f"# Compiled blocklist from multiple sources ({title})",
        "#",
        f"# Last Updated: {timestamp}",
        f"# Total Domains: {total_domains:,}",
        "#",
        "# Source Lists:",
    ]

    filtered_lists = (
        blocklists if include_nsfw else filter_blocklists_by_nsfw(blocklists, False)
    )

    for blocklist in filtered_lists:
        is_nsfw = blocklist.get("nsfw", False)
        count = list_stats.get(blocklist["name"], 0)
        nsfw_flag = " [NSFW]" if is_nsfw else ""
        header.append(f"#   - {blocklist['name']}{nsfw_flag}: {count:,} domains")
        header.append(f"#     {blocklist['url']}")

    header.extend(["#", "# Usage: Add this URL to your blocklist subscriptions", "#"])
    return header


def generate_hosts_file_streaming(
    deduplicated_domains: Path, output_file: Path, header_lines: list[str]
):
    """
    Generate hosts file by streaming from deduplicated domain file.

    Args:
        deduplicated_domains: Path to file with deduplicated domains
        output_file: Path to output hosts file
        header_lines: List of header lines to write
    """
    with deduplicated_domains.open("r") as f_in, output_file.open("w") as f_out:
        f_out.write("\n".join(header_lines) + "\n\n")

        for line in f_in:
            domain = line.strip()
            if domain:
                f_out.write(f"0.0.0.0 {domain}\n")


def update_readme(
    blocklists: list[dict[str, str]],
    list_stats: dict[str, int],
    total_general: int,
    total_all: int,
    contribution_stats: ContributionStats,
    last_update: str,
) -> None:
    """
    Update README with dual statistics tables (general and NSFW).

    General lists show contribution to GENERAL aggregate (hosts file).
    NSFW lists show contribution to ALL aggregate (hosts_nsfw file).

    Args:
        blocklists: List of blocklist configurations
        list_stats: Domain count per list
        total_general: Total unique domains (non-NSFW)
        total_all: Total unique domains (including NSFW)
        contribution_stats: Per-list contribution to each aggregate
        last_update: Timestamp of last update
    """

    def build_table(lists: list[dict[str, str]], contributions: dict[str, int]) -> str:
        """Build HTML table for blocklist statistics."""
        sorted_lists = sorted(
            lists, key=lambda bl: contributions.get(bl["name"], 0), reverse=True
        )

        rows = []
        for bl in sorted_lists:
            name = bl["name"]
            url = bl["url"]
            total = list_stats.get(name, 0)
            unique = contributions.get(name, 0)
            rows.append(
                f"<tr><td><a href='{url}'>{name}</a></td>"
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

    content = readme_path.read_text()

    general_formatted = format_domain_count(total_general)
    nsfw_formatted = format_domain_count(total_all)

    replacements = [
        (
            r"(Use `hosts` for general protection without NSFW blocking \(~)[^)]+(\))",
            rf"\g<1>{general_formatted} domains\g<2>",
        ),
        (
            r"(Use `hosts_nsfw` for complete protection including NSFW blocking \(~)[^)]+(\))",
            rf"\g<1>{nsfw_formatted} domains\g<2>",
        ),
        (
            r'(Output1\[\("📄 hosts<br/>\(General Only\)<br/>~)[^"]+( domains"\)\])',
            rf"\g<1>{general_formatted}\g<2>",
        ),
        (
            r'(Output2\[\("🔞 hosts_nsfw<br/>\(Complete\)<br/>~)[^"]+( domains"\)\])',
            rf"\g<1>{nsfw_formatted}\g<2>",
        ),
    ]

    for pattern, replacement in replacements:
        content = re.sub(pattern, replacement, content)

    stats_start = content.find("<!-- STATS_START -->")
    stats_end = content.find("<!-- STATS_END -->")

    if stats_start == -1 or stats_end == -1:
        print("Warning: README.md missing stats markers", file=sys.stderr)
        return

    general_lists = filter_blocklists_by_nsfw(blocklists, False)
    nsfw_lists = filter_blocklists_by_nsfw(blocklists, True)

    # General lists: contribution to GENERAL aggregate (relevant for hosts file)
    general_table = build_table(general_lists, contribution_stats.contrib_general)
    # NSFW lists: contribution to ALL aggregate (relevant for hosts_nsfw file)
    nsfw_table = build_table(nsfw_lists, contribution_stats.contrib_all)

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
> **Unique Contribution** shows how many domains would disappear if that source were removed. These are domains that appear in only one list. Two files are generated: `hosts` (general only) and `hosts_nsfw` (includes NSFW). Sources with low unique counts (~50 or less) provide minimal value and should be considered for removal.

<!-- STATS_END -->"""

    new_content = (
        content[:stats_start]
        + stats_section
        + content[stats_end + len("<!-- STATS_END -->") :]
    )
    readme_path.write_text(new_content)
    print("Updated README.md with dual statistics tables")


def main() -> int:
    """
    Execute main compilation process using annotated streaming pipeline.

    Pipeline: annotate → one sort → streaming group-by
    Complexity: O(N log N) sort + O(N) streaming pass, O(k) memory for list counters.

    Returns:
        Exit code: 0 on success, 1 on error
    """
    print("YAHA - Yet Another Host Aggregator")
    print("=" * 50)

    try:
        print("\nLoading blocklist configuration...")
        blocklists = load_blocklists()
        print(f"Loaded {len(blocklists)} blocklist(s)")

        blocklists_dir = Path("blocklists")
        blocklists_dir.mkdir(exist_ok=True)

        hosts_path = blocklists_dir / "hosts"
        hosts_nsfw_path = blocklists_dir / "hosts_nsfw"

        pipeline = PipelineFiles.create()

        print("\nStep 1: Fetching blocklists and emitting annotated stream...")
        list_stats, id_to_name = collect_blocklists_annotated(
            blocklists, pipeline.annotated
        )

        print("\nStep 2: Processing through sort → group-by pipeline...")
        all_count, general_count, contribution_stats = process_annotated_pipeline(
            pipeline, id_to_name
        )

        print(f"\n  Total unique domains (general): {general_count:,}")
        print(f"  Total unique domains (all with NSFW): {all_count:,}")

        print("\nStep 3: Generating hosts files...")
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        general_header = build_header(
            "GENERAL - No NSFW", general_count, blocklists, list_stats, False, timestamp
        )
        nsfw_header = build_header(
            "INCLUDING NSFW", all_count, blocklists, list_stats, True, timestamp
        )

        generate_hosts_file_streaming(
            pipeline.domains_general, hosts_path, general_header
        )
        generate_hosts_file_streaming(
            pipeline.domains_all, hosts_nsfw_path, nsfw_header
        )

        print(f"  Wrote {general_count:,} domains to blocklists/hosts")
        print(f"  Wrote {all_count:,} domains to blocklists/hosts_nsfw")

        print("\nStep 4: Updating README...")
        update_readme(
            blocklists,
            list_stats,
            general_count,
            all_count,
            contribution_stats,
            timestamp,
        )

        print("\nStep 5: Cleaning up temporary files...")
        pipeline.cleanup()

        print("\n✓ Compilation complete")
        return 0

    except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
