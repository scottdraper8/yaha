#!/usr/bin/env python3
"""
YAHA - Yet Another Host Aggregator
Compiles multiple blocklists into a single unified hosts file.
"""

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

# Blocklist sources
BLOCKLISTS = [
    {
        "name": "Steven Black's Unified Hosts",
        "url": "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts",
        "comment": "Unified hosts with adware and malware",
    },
    {
        "name": "OISD Big List",
        "url": "https://big.oisd.nl",
        "comment": "Comprehensive domain blocklist",
    },
    {
        "name": "Abuse.ch Malware Blocklist",
        "url": "https://urlhaus.abuse.ch/downloads/hostfile/",
        "comment": "Malware and botnet domains",
    },
    {
        "name": "HaGeZi Multi-pro Extended",
        "url": "https://cdn.jsdelivr.net/gh/hagezi/dns-blocklists@latest/hosts/pro.txt",
        "comment": "Pro-level extended protection",
    },
    {
        "name": "HaGeZi Threat Intelligence",
        "url": "https://cdn.jsdelivr.net/gh/hagezi/dns-blocklists@latest/hosts/tif.txt",
        "comment": "Threat intelligence feeds",
    },
]

# Regex pattern to extract domains from various hosts file formats
DOMAIN_PATTERN = re.compile(
    r"^(?:0\.0\.0\.0|127\.0\.0\.1|::1?)\s+([a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*)"
)
RAW_DOMAIN_PATTERN = re.compile(
    r"^([a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)+)"
)


def fetch_blocklist(url: str, timeout: int = 30) -> str:
    """
    Fetches blocklist content from URL.

    Args:
        url: URL of the blocklist
        timeout: Request timeout in seconds

    Returns:
        Raw content of the blocklist

    Raises:
        httpx.HTTPError: If request fails
    """
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text


def parse_domains(content: str) -> set[str]:
    """
    Extracts domains from blocklist content.

    Args:
        content: Raw blocklist content

    Returns:
        Set of unique domain names
    """
    domains = set()

    for line in content.splitlines():
        line = line.strip()

        # Skip empty lines and comments
        if not line or line.startswith("#"):
            continue

        # Try hosts file format first
        match = DOMAIN_PATTERN.match(line)
        if match:
            domains.add(match.group(1).lower())
            continue

        # Try raw domain format
        match = RAW_DOMAIN_PATTERN.match(line)
        if match:
            domains.add(match.group(1).lower())

    return domains


def collect_blocklists() -> tuple[set[str], dict[str, int], dict[str, set[str]]]:
    """
    Fetches and processes all blocklists.

    Returns:
        Tuple of (all unique domains, domain count per list, domains per list)
    """
    all_domains = set()
    list_stats = {}
    domains_by_list = {}

    for blocklist in BLOCKLISTS:
        print(f"Fetching {blocklist['name']}...")
        try:
            content = fetch_blocklist(blocklist["url"])
            domains = parse_domains(content)
            list_stats[blocklist["name"]] = len(domains)
            domains_by_list[blocklist["name"]] = domains
            all_domains.update(domains)
            print(f"  → Found {len(domains):,} domains")
        except Exception as e:
            print(f"  → Error: {e}", file=sys.stderr)
            list_stats[blocklist["name"]] = 0
            domains_by_list[blocklist["name"]] = set()

    return all_domains, list_stats, domains_by_list


def calculate_overlap(domains_by_list: dict[str, set[str]]) -> dict[str, int]:
    """
    Calculates unique domain contributions per list using cached data.

    Args:
        domains_by_list: Dictionary mapping list name to its domains

    Returns:
        Dictionary of unique domains contributed by each list
    """
    unique_contributions = {}

    for blocklist in BLOCKLISTS:
        name = blocklist["name"]
        print(f"Analyzing overlap for {name}...")

        if name not in domains_by_list or not domains_by_list[name]:
            unique_contributions[name] = 0
            print(f"  → {0:,} unique domains")
            continue

        # Calculate unique domains by removing this list and checking difference
        other_domains = set()
        for other_name, other_domain_set in domains_by_list.items():
            if other_name != name:
                other_domains.update(other_domain_set)

        unique = domains_by_list[name] - other_domains
        unique_contributions[name] = len(unique)
        print(f"  → {len(unique):,} unique domains")

    return unique_contributions

    return unique_contributions


def generate_hosts_file(domains: set[str], list_stats: dict[str, int]) -> str:
    """
    Generates hosts file content with header.

    Args:
        domains: Set of unique domains
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

    for blocklist in BLOCKLISTS:
        count = list_stats.get(blocklist["name"], 0)
        header.append(f"#   - {blocklist['name']}: {count:,} domains")
        header.append(f"#     {blocklist['url']}")

    header.extend(
        ["#", "# Usage: Add this URL to your Pi-hole blocklist subscriptions", "#"]
    )

    content = "\n".join(header) + "\n\n"
    content += "\n".join(f"0.0.0.0 {domain}" for domain in sorted_domains)
    content += "\n"

    return content


def update_readme(
    list_stats: dict[str, int],
    total_domains: int,
    unique_contributions: dict[str, int],
    last_update: str,
) -> None:
    """
    Updates README with current statistics.

    Args:
        list_stats: Domain count per list
        total_domains: Total unique domains
        unique_contributions: Unique domains per list
        last_update: Timestamp of last update
    """
    readme_path = Path("README.md")
    current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Check if README exists and read it
    if readme_path.exists():
        content = readme_path.read_text()

        # Update statistics section
        stats_start = content.find("<!-- STATS_START -->")
        stats_end = content.find("<!-- STATS_END -->")

        if stats_start != -1 and stats_end != -1:
            stats_section = f"""<!-- STATS_START -->

## 📊 Statistics

**Last Updated:** {last_update}
**Last Run:** {current_time}
**Total Unique Domains:** {total_domains:,}

### Domain Count by Source

| Source List | Total Domains | Unique Contribution |
|-------------|---------------|---------------------|
"""

            for blocklist in BLOCKLISTS:
                name = blocklist["name"]
                total = list_stats.get(name, 0)
                unique = unique_contributions.get(name, 0)
                stats_section += f"| {name} | {total:,} | {unique:,} |\n"

            stats_section += "\n<!-- STATS_END -->"

            new_content = (
                content[:stats_start]
                + stats_section
                + content[stats_end + len("<!-- STATS_END -->") :]
            )
            readme_path.write_text(new_content)
            print("Updated README.md with statistics")
        else:
            print("Warning: README.md missing stats markers", file=sys.stderr)


def main() -> int:
    """
    Main execution function.

    Returns:
        Exit code: 0 if hosts file unchanged, 1 if updated
    """
    print("YAHA - Yet Another Host Aggregator")
    print("=" * 50)

    # Read existing hosts file if it exists
    hosts_path = Path("hosts")
    old_content = hosts_path.read_text() if hosts_path.exists() else ""

    # Collect all domains
    print("\nStep 1: Fetching blocklists...")
    all_domains, list_stats, domains_by_list = collect_blocklists()

    print(f"\nTotal unique domains: {len(all_domains):,}")

    # Calculate overlap
    print("\nStep 2: Calculating unique contributions...")
    unique_contributions = calculate_overlap(domains_by_list)

    # Generate new hosts file
    print("\nStep 3: Generating hosts file...")
    new_content = generate_hosts_file(all_domains, list_stats)
    hosts_path.write_text(new_content)
    print(f"Wrote {len(all_domains):,} domains to hosts file")

    # Update README
    print("\nStep 4: Updating README...")
    last_update = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    if old_content != new_content:
        update_readme(list_stats, len(all_domains), unique_contributions, last_update)
        print("\n✓ Hosts file updated successfully")
        return 1
    else:
        update_readme(list_stats, len(all_domains), unique_contributions, last_update)
        print("\n✓ No changes detected in hosts file")
        return 0


if __name__ == "__main__":
    sys.exit(main())
