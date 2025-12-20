#!/usr/bin/env python3
"""
YAHA - Yet Another Host Aggregator
Compiles multiple blocklists into a single unified hosts file.
"""

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from curl_cffi import requests

# Configuration constants
MAX_WORKERS = 5  # Maximum concurrent blocklist fetches
REQUEST_TIMEOUT = 30  # Request timeout in seconds

# Regex patterns to extract domains from various blocklist formats
# Hosts file format: 0.0.0.0 domain.com or 127.0.0.1	domain.com
HOSTS_PATTERN = re.compile(
    r"^(?:0\.0\.0\.0|127\.0\.0\.1|::1?)\s+([a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*)"
)
# Raw domain format: domain.com
RAW_DOMAIN_PATTERN = re.compile(
    r"^([a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)+)$"
)
# Adblock Plus filter format: ||domain.com^
ADBLOCK_PATTERN = re.compile(r"^\|\|([a-zA-Z0-9](?:[a-zA-Z0-9\-\.]*[a-zA-Z0-9])?)\^")


def fetch_blocklist(
    name: str, url: str, timeout: int = REQUEST_TIMEOUT
) -> tuple[str, str, str]:
    """
    Fetches blocklist content from URL using curl_cffi.

    Args:
        name: Name of the blocklist
        url: URL of the blocklist
        timeout: Request timeout in seconds

    Returns:
        Tuple of (name, url, content)

    Raises:
        requests.RequestException: If request fails
    """
    response = requests.get(
        url,
        timeout=timeout,
        impersonate="chrome120",
        verify=True,
    )
    response.raise_for_status()
    return name, url, response.text


def is_valid_domain(domain: str) -> bool:
    """Validates domain has proper structure."""
    return "." in domain and not domain.startswith(".") and not domain.endswith(".")


def parse_domains(content: str) -> set[str]:
    """
    Extracts domains from blocklist content.
    Supports multiple formats: hosts files, raw domains, and Adblock Plus filters.

    Args:
        content: Raw blocklist content

    Returns:
        Set of unique domain names
    """
    domains = set()
    patterns = [ADBLOCK_PATTERN, HOSTS_PATTERN, RAW_DOMAIN_PATTERN]

    for line in content.splitlines():
        line = line.strip()

        # Skip empty lines and comments
        if (
            not line
            or line.startswith(("#", "!", "["))
            or line.startswith("127.0.0.1 localhost")
        ):
            continue

        # Try each pattern until one matches
        for pattern in patterns:
            match = pattern.match(line)
            if match:
                domain = match.group(1).lower()
                if is_valid_domain(domain):
                    domains.add(domain)
                break

    return domains


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

    return blocklists


def collect_blocklists(
    blocklists: list[dict[str, str]],
) -> tuple[set[str], dict[str, int], dict[str, set[str]]]:
    """
    Fetches and processes all blocklists concurrently.

    Args:
        blocklists: List of blocklist configurations

    Returns:
        Tuple of (all unique domains, domain count per list, domains per list)
    """
    all_domains = set()
    list_stats = {}
    domains_by_list = {}

    # Submit all fetch tasks concurrently
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_blocklist = {
            executor.submit(fetch_blocklist, bl["name"], bl["url"]): bl
            for bl in blocklists
        }

        # Process results as they complete
        for future in as_completed(future_to_blocklist):
            blocklist = future_to_blocklist[future]
            name = blocklist["name"]

            try:
                name, url, content = future.result()
                print(f"Fetching {name}...")
                domains = parse_domains(content)
                list_stats[name] = len(domains)
                domains_by_list[name] = domains
                all_domains.update(domains)
                print(f"  → Found {len(domains):,} domains")
            except Exception as e:
                print(f"Fetching {name}...")
                print(f"  → Error: {e}", file=sys.stderr)
                list_stats[name] = 0
                domains_by_list[name] = set()

    return all_domains, list_stats, domains_by_list


def calculate_overlap(
    blocklists: list[dict[str, str]], domains_by_list: dict[str, set[str]]
) -> dict[str, int]:
    """
    Calculates unique domain contributions per list.

    Args:
        blocklists: List of blocklist configurations
        domains_by_list: Dictionary mapping list name to its domains

    Returns:
        Dictionary of unique domains contributed by each list
    """
    unique_contributions = {}

    for blocklist in blocklists:
        name = blocklist["name"]
        print(f"Analyzing overlap for {name}...")

        if name not in domains_by_list or not domains_by_list[name]:
            unique_contributions[name] = 0
            print(f"  → {0:,} unique domains")
            continue

        # Collect all domains from other lists
        other_domains = set().union(
            *(
                domains
                for other_name, domains in domains_by_list.items()
                if other_name != name
            )
        )

        unique_count = len(domains_by_list[name] - other_domains)
        unique_contributions[name] = unique_count
        print(f"  → {unique_count:,} unique domains")

    return unique_contributions


def generate_hosts_file(
    domains: set[str], blocklists: list[dict[str, str]], list_stats: dict[str, int]
) -> str:
    """
    Generates hosts file content with header.

    Args:
        domains: Set of unique domains
        blocklists: List of blocklist configurations
        list_stats: Domain count per list

    Returns:
        Formatted hosts file content
    """
    sorted_domains = sorted(domains)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    header = [
        "# YAHA - Yet Another Host Aggregator",
        "# Compiled blocklist from multiple sources",
        "#",
        f"# Last Updated: {timestamp}",
        f"# Total Domains: {len(domains):,}",
        "#",
        "# Source Lists:",
    ]

    for blocklist in blocklists:
        count = list_stats.get(blocklist["name"], 0)
        header.append(f"#   - {blocklist['name']}: {count:,} domains")
        header.append(f"#     {blocklist['url']}")

    header.extend(["#", "# Usage: Add this URL to your blocklist subscriptions", "#"])

    content = "\n".join(header) + "\n\n"
    content += "\n".join(f"0.0.0.0 {domain}" for domain in sorted_domains)
    content += "\n"

    return content


def build_stats_table(
    blocklists: list[dict[str, str]],
    list_stats: dict[str, int],
    unique_contributions: dict[str, int],
) -> str:
    """Builds markdown table rows for statistics."""
    rows = []
    for blocklist in blocklists:
        name = blocklist["name"]
        total = list_stats.get(name, 0)
        unique = unique_contributions.get(name, 0)
        rows.append(f"| {name} | {total:,} | {unique:,} |")
    return "\n".join(rows)


def update_readme(
    blocklists: list[dict[str, str]],
    list_stats: dict[str, int],
    total_domains: int,
    unique_contributions: dict[str, int],
    last_update: str,
) -> None:
    """
    Updates README with current statistics.

    Args:
        blocklists: List of blocklist configurations
        list_stats: Domain count per list
        total_domains: Total unique domains
        unique_contributions: Unique domains per list
        last_update: Timestamp of last update
    """
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

    table_rows = build_stats_table(blocklists, list_stats, unique_contributions)

    # Format timestamp with double-dash date separator for badge display
    # Input: "2025-12-20 11:01:47 UTC" -> Output: "2025--12--20_11:01:47_UTC"
    date_part, time_part, utc = last_update.split()
    last_update_badge = f"{date_part.replace('-', '--')}_{time_part}_{utc}"

    stats_section = f"""<!-- STATS_START -->

## Latest Run

<div align="center">

![Total Domains](https://img.shields.io/badge/Total_Unique_Domains-{total_domains:,}-ff79c6?style=for-the-badge&labelColor=282a36)
![Last Updated](https://img.shields.io/badge/Last_Updated-{last_update_badge}-bd93f9?style=for-the-badge&labelColor=282a36)

</div>

### Domain Count by Source

Unique Contribution shows domains that appear only in that specific list. A source with 0 unique contributions is entirely covered by other lists.

| Source List | Total Domains | Unique Contribution |
| ----------- | ------------- | ------------------- |
{table_rows}

<!-- STATS_END -->"""

    new_content = (
        content[:stats_start]
        + stats_section
        + content[stats_end + len("<!-- STATS_END -->") :]
    )
    readme_path.write_text(new_content)
    print("Updated README.md with statistics")


def main() -> int:
    """
    Main execution function.

    Returns:
        Exit code: 0 if unchanged, 1 if updated, 2 if error
    """
    print("YAHA - Yet Another Host Aggregator")
    print("=" * 50)

    try:
        print("\nLoading blocklist configuration...")
        blocklists = load_blocklists()
        print(f"Loaded {len(blocklists)} blocklist(s)")

        hosts_path = Path("hosts")
        old_content = hosts_path.read_text() if hosts_path.exists() else ""

        print("\nStep 1: Fetching blocklists...")
        all_domains, list_stats, domains_by_list = collect_blocklists(blocklists)
        print(f"\nTotal unique domains: {len(all_domains):,}")

        print("\nStep 2: Calculating unique contributions...")
        unique_contributions = calculate_overlap(blocklists, domains_by_list)

        print("\nStep 3: Generating hosts file...")
        new_content = generate_hosts_file(all_domains, blocklists, list_stats)
        hosts_path.write_text(new_content)
        print(f"Wrote {len(all_domains):,} domains to hosts file")

        print("\nStep 4: Updating README...")
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        update_readme(
            blocklists, list_stats, len(all_domains), unique_contributions, timestamp
        )

        if old_content != new_content:
            print("\n✓ Hosts file updated successfully")
            return 1

        print("\n✓ No changes detected in hosts file")
        return 0

    except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
