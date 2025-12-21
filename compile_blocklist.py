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

# Configuration constants
MAX_WORKERS = 5
REQUEST_TIMEOUT = 30


@dataclass(frozen=True)
class TempFiles:
    """Manages temporary file paths for domain processing pipeline."""

    unsorted: Path
    sorted: Path
    deduped: Path

    @classmethod
    def for_variant(cls, variant: str) -> "TempFiles":
        """Creates temp file paths for a processing variant (general or nsfw)."""
        return cls(
            unsorted=Path(f"temp_{variant}_unsorted.txt"),
            sorted=Path(f"temp_{variant}_sorted.txt"),
            deduped=Path(f"temp_{variant}_deduped.txt"),
        )

    def cleanup(self) -> None:
        """Removes all temporary files."""
        self.unsorted.unlink(missing_ok=True)
        self.sorted.unlink(missing_ok=True)
        self.deduped.unlink(missing_ok=True)


# Regex patterns to extract domains from various blocklist formats
# Domain validation per RFC 1035: max 253 chars total, 63 per label
_DOMAIN_REGEX = r"[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*"

HOSTS_PATTERN = re.compile(
    rf"^(?:0\.0\.0\.0|127\.0\.0\.1|::1?)[\s\t]+({_DOMAIN_REGEX})"
)
RAW_DOMAIN_PATTERN = re.compile(rf"^({_DOMAIN_REGEX})$")
ADBLOCK_PATTERN = re.compile(rf"^\|\|({_DOMAIN_REGEX})\^")


def fetch_blocklist_stream(name: str, url: str, timeout: int = REQUEST_TIMEOUT):
    """
    Fetches blocklist content from URL.

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

        def line_generator():
            for line in response.text.splitlines():
                yield line

        return name, url, line_generator()
    except Exception as e:
        raise Exception(f"Failed to fetch {name}: {str(e)}") from e


def is_valid_domain(domain: str) -> bool:
    """
    Validates domain structure per RFC 1035.

    Checks for proper TLD, label length, hyphen placement, and format.
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


def compute_domain_hash(file_path: Path) -> str:
    """
    Computes SHA256 hash of domain lines only (excluding comments/headers).

    Uses system tools for better performance with large files.

    Args:
        file_path: Path to hosts file

    Returns:
        SHA256 hash as hex string, or empty string if file doesn't exist
    """
    if not file_path.exists():
        return ""

    try:
        # Piped commands: filter comments → filter empty lines → compute hash
        result = subprocess.run(
            "grep -v '^#' | grep -v '^[[:space:]]*$' | sha256sum",
            input=file_path.read_text(),
            capture_output=True,
            text=True,
            shell=True,
            check=True,
        )
        return result.stdout.split()[0]
    except (subprocess.CalledProcessError, IndexError):
        return ""


def parse_domains_stream(lines):
    """
    Extracts domains from line iterator, yielding one at a time.

    Supports hosts files, raw domain lists, and Adblock Plus filters.

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
    Loads blocklist configuration from JSON file.

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
    Filters blocklist configuration by NSFW flag.

    Args:
        blocklists: List of blocklist configurations
        include_nsfw: If True, return NSFW lists; if False, return non-NSFW lists

    Returns:
        Filtered list of blocklist configurations
    """
    return [bl for bl in blocklists if bl.get("nsfw", False) == include_nsfw]


def collect_blocklists_to_disk(
    blocklists: list[dict[str, str]],
) -> tuple[Path, Path, dict[str, int]]:
    """
    Fetches and streams all blocklists to temporary files on disk.

    Args:
        blocklists: List of blocklist configurations

    Returns:
        Tuple of (general temp file path, nsfw temp file path, domain count per list)
    """
    temp_files_general = TempFiles.for_variant("general")
    temp_files_nsfw = TempFiles.for_variant("nsfw")
    list_stats = {}

    with (
        temp_files_general.unsorted.open("w") as f_gen,
        temp_files_nsfw.unsorted.open("w") as f_nsfw,
    ):
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_blocklist = {
                executor.submit(fetch_blocklist_stream, bl["name"], bl["url"]): bl
                for bl in blocklists
            }

            for future in as_completed(future_to_blocklist):
                blocklist = future_to_blocklist[future]
                name = blocklist["name"]
                is_nsfw = blocklist.get("nsfw", False)

                try:
                    name, url, lines = future.result()
                    print(f"Fetching {name}{'  [NSFW]' if is_nsfw else ''}...")

                    count = 0
                    for domain in parse_domains_stream(lines):
                        f_gen.write(f"{domain}\n")
                        if is_nsfw:
                            f_nsfw.write(f"{domain}\n")
                        count += 1

                    list_stats[name] = count
                    print(f"  → Found {count:,} domains")
                except Exception as e:
                    print(f"Fetching {name}...")
                    print(f"  → Error: {e}", file=sys.stderr)
                    list_stats[name] = 0

    return temp_files_general.unsorted, temp_files_nsfw.unsorted, list_stats


def sort_domain_file(input_file: Path, output_file: Path):
    """
    Sorts domain file alphabetically using system sort.

    Args:
        input_file: Path to unsorted domain file
        output_file: Path to write sorted domain file
    """
    subprocess.run(["sort", str(input_file), "-o", str(output_file)], check=True)


def deduplicate_sorted_file(sorted_input: Path, deduplicated_output: Path) -> int:
    """
    Deduplicates sorted domains using consecutive comparison.

    Implements sequential duplicate removal: compares each domain with its
    predecessor in a single pass. Since input is sorted, all duplicates are
    adjacent and can be detected by pairwise comparison.

    Memory-efficient: maintains only two strings in memory (previous and current).
    This is the algorithm used by Unix `uniq` command.

    Args:
        sorted_input: Path to sorted domain file
        deduplicated_output: Path to write deduplicated domains

    Returns:
        Count of unique domains
    """
    unique_count = 0
    previous_domain = None

    with sorted_input.open("r") as f_in, deduplicated_output.open("w") as f_out:
        for line in f_in:
            current_domain = line.strip()

            if not current_domain:
                continue

            if current_domain != previous_domain:
                if previous_domain is not None:
                    f_out.write(f"{previous_domain}\n")
                    unique_count += 1
                previous_domain = current_domain

        if previous_domain is not None:
            f_out.write(f"{previous_domain}\n")
            unique_count += 1

    return unique_count


def process_domain_pipeline(temp_files: TempFiles) -> int:
    """
    Processes domain file through sort → deduplicate pipeline.

    Args:
        temp_files: TempFiles instance containing pipeline file paths

    Returns:
        Count of unique domains
    """
    sort_domain_file(temp_files.unsorted, temp_files.sorted)
    unique_count = deduplicate_sorted_file(temp_files.sorted, temp_files.deduped)
    return unique_count


def calculate_overlap(
    blocklists: list[dict[str, str]], domains_by_list: dict[str, set[str]]
) -> dict[str, int]:
    """
    Disabled to avoid memory issues with large domain sets.

    Returns zero for all lists.
    """
    return {bl["name"]: 0 for bl in blocklists}


def build_header(
    title: str,
    total_domains: int,
    blocklists: list[dict[str, str]],
    list_stats: dict[str, int],
    include_nsfw: bool,
    timestamp: str,
) -> list[str]:
    """
    Builds header lines for hosts file.

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

    for blocklist in blocklists:
        is_nsfw = blocklist.get("nsfw", False)
        if not include_nsfw and is_nsfw:
            continue

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
    Generates hosts file by streaming from deduplicated domain file.

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
    unique_contributions: dict[str, int],
    last_update: str,
) -> None:
    """
    Updates README with dual statistics tables (general and NSFW).

    Args:
        blocklists: List of blocklist configurations
        list_stats: Domain count per list
        total_general: Total unique domains (non-NSFW)
        total_all: Total unique domains (including NSFW)
        unique_contributions: Unique domains per list
        last_update: Timestamp of last update
    """

    def build_table(lists: list[dict[str, str]]) -> str:
        """Builds HTML table for blocklist statistics."""
        sorted_lists = sorted(
            lists, key=lambda bl: unique_contributions.get(bl["name"], 0), reverse=True
        )

        rows = []
        for bl in sorted_lists:
            name = bl["name"]
            url = bl["url"]
            total = list_stats.get(name, 0)
            unique = unique_contributions.get(name, 0)
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
    stats_start = content.find("<!-- STATS_START -->")
    stats_end = content.find("<!-- STATS_END -->")

    if stats_start == -1 or stats_end == -1:
        print("Warning: README.md missing stats markers", file=sys.stderr)
        return

    general_lists = filter_blocklists_by_nsfw(blocklists, False)
    nsfw_lists = filter_blocklists_by_nsfw(blocklists, True)

    general_table = build_table(general_lists)
    nsfw_table = build_table(nsfw_lists)

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
> Unique Contribution shows domains that appear only in that specific list. Two files are generated: `hosts` (general only) and `hosts_nsfw` (includes NSFW). Sources with low unique counts (~50 or less) should be considered for removal as they provide minimal value.

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
    Main execution function using disk-based streaming.

    Returns:
        Exit code: 0 if unchanged, 1 if updated, 2 if error
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

        old_general_hash = compute_domain_hash(hosts_path)
        old_nsfw_hash = compute_domain_hash(hosts_nsfw_path)

        print("\nStep 1: Fetching and streaming blocklists to disk...")
        _, _, list_stats = collect_blocklists_to_disk(blocklists)

        print("\nStep 2: Sorting and deduplicating domains...")
        temp_general = TempFiles.for_variant("general")
        temp_nsfw = TempFiles.for_variant("nsfw")

        print("  Processing general (non-NSFW) domains...")
        general_count = process_domain_pipeline(temp_general)

        print("  Processing all domains (including NSFW)...")
        nsfw_count = process_domain_pipeline(temp_nsfw)

        print(f"\n  Total unique domains (general): {general_count:,}")
        print(f"  Total unique domains (all with NSFW): {nsfw_count:,}")

        print("\nStep 3: Generating hosts files...")
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        general_header = build_header(
            "GENERAL - No NSFW", general_count, blocklists, list_stats, False, timestamp
        )
        nsfw_header = build_header(
            "INCLUDING NSFW", nsfw_count, blocklists, list_stats, True, timestamp
        )

        generate_hosts_file_streaming(temp_general.deduped, hosts_path, general_header)
        generate_hosts_file_streaming(temp_nsfw.deduped, hosts_nsfw_path, nsfw_header)

        print(f"  Wrote {general_count:,} domains to blocklists/hosts")
        print(f"  Wrote {nsfw_count:,} domains to blocklists/hosts_nsfw")

        print("\nStep 4: Updating README...")
        update_readme(
            blocklists,
            list_stats,
            general_count,
            nsfw_count,
            {},
            timestamp,
        )

        print("\nStep 5: Cleaning up temporary files...")
        temp_general.cleanup()
        temp_nsfw.cleanup()

        print("\nStep 6: Comparing with previous version...")
        new_general_hash = compute_domain_hash(hosts_path)
        new_nsfw_hash = compute_domain_hash(hosts_nsfw_path)

        if old_general_hash != new_general_hash or old_nsfw_hash != new_nsfw_hash:
            general_changed = old_general_hash != new_general_hash
            nsfw_changed = old_nsfw_hash != new_nsfw_hash
            print("\n✓ Domain content changed - blocklists updated")
            print(f"  General: {'changed' if general_changed else 'unchanged'}")
            print(f"  NSFW: {'changed' if nsfw_changed else 'unchanged'}")
            return 1

        print("\n✓ No domain changes detected - files up to date")
        return 0

    except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
