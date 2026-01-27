"""Hosts file generation.

Zero-knowledge module for generating hosts file format from domains.
Handles file I/O only - no knowledge of sources, categories, or purposes.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path


def format_count(count: int) -> str:
    """Format count as human-readable string (e.g., "4.4M" for 4,400,000)."""
    millions = count / 1_000_000
    return f"{millions:.1f}M"


def generate_hosts_file(
    domains: Iterator[str],
    output_path: Path,
    header_lines: list[str],
) -> int:
    """
    Generate hosts file from domain iterator.

    Each domain is written as: 0.0.0.0 domain.com

    Args:
        domains: Iterator of domain names
        output_path: Path to write hosts file
        header_lines: List of header lines to write first

    Returns:
        Number of domains written
    """
    count = 0
    with output_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(header_lines) + "\n\n")

        for raw_domain in domains:
            domain = raw_domain.strip()
            if domain:
                f.write(f"0.0.0.0 {domain}\n")
                count += 1

    return count


def generate_hosts_file_from_file(
    source_path: Path,
    output_path: Path,
    header_lines: list[str],
) -> int:
    """
    Generate hosts file by reading domains from a file.

    Args:
        source_path: Path to file with deduplicated domains (one per line)
        output_path: Path to write hosts file
        header_lines: List of header lines to write first

    Returns:
        Number of domains written
    """

    def domain_reader() -> Iterator[str]:
        with source_path.open("r", encoding="utf-8") as f:
            for line in f:
                yield line.strip()

    return generate_hosts_file(domain_reader(), output_path, header_lines)
