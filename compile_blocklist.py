#!/usr/bin/env python3
"""
YAHA - Yet Another Host Aggregator

Compiles multiple blocklists into unified hosts files with hash-based
change detection.

Features:
- SHA256 hash comparison for change detection
- Auto-purge of stale lists (no updates for 180+ days)
- Weekly forced compilation
- Concurrent fetching
- Dual output: general protection and complete (with NSFW)
"""

import hashlib
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from curl_cffi import requests

MAX_WORKERS = 5
REQUEST_TIMEOUT = 30
STATE_FILE = Path("state.json")
STALE_THRESHOLD_DAYS = 180

PSL_FILE = Path("public_suffix_list.dat")
PSL_URL = "https://publicsuffix.org/list/public_suffix_list.dat"
PSL_STALE_DAYS = 30


@dataclass(frozen=True)
class PublicSuffixList:
    """
    Parsed Public Suffix List data structure.

    Supports exact suffixes, wildcard rules, and exception rules.
    """

    exact: frozenset[str]
    wildcards: frozenset[str]
    exceptions: frozenset[str]


def download_psl(psl_path: Path) -> None:
    """
    Download the Public Suffix List from Mozilla.

    Args:
        psl_path: Path to save the downloaded file
    """
    response = requests.get(
        PSL_URL,
        timeout=REQUEST_TIMEOUT,
        impersonate="chrome120",
        verify=True,
    )
    response.raise_for_status()
    psl_path.write_text(response.text, encoding="utf-8")


def is_psl_stale(psl_path: Path) -> bool:
    """
    Check if the cached PSL file is stale (older than PSL_STALE_DAYS).

    Args:
        psl_path: Path to the PSL file

    Returns:
        True if file is missing or older than threshold
    """
    if not psl_path.exists():
        return True

    mtime = datetime.fromtimestamp(psl_path.stat().st_mtime, tz=timezone.utc)
    age_days = (datetime.now(timezone.utc) - mtime).days
    return age_days >= PSL_STALE_DAYS


def load_public_suffix_list(psl_path: Path) -> PublicSuffixList:
    """
    Parse the Public Suffix List file into lookup structures.

    Format:
    - Lines starting with // are comments
    - Blank lines are ignored
    - *.suffix indicates wildcard (all subdomains are public suffixes)
    - !exception indicates an exception to a wildcard rule
    - Other lines are exact public suffixes

    Args:
        psl_path: Path to the PSL file

    Returns:
        PublicSuffixList with parsed rules
    """
    exact: set[str] = set()
    wildcards: set[str] = set()
    exceptions: set[str] = set()

    with psl_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            # Skip comments and empty lines
            if not line or line.startswith("//"):
                continue

            # Exception rule: !www.ck means www.ck is NOT a public suffix
            if line.startswith("!"):
                exceptions.add(line[1:].lower())
            # Wildcard rule: *.ck means all *.ck are public suffixes
            elif line.startswith("*."):
                wildcards.add(line[2:].lower())
            # Exact suffix rule
            else:
                exact.add(line.lower())

    return PublicSuffixList(
        exact=frozenset(exact),
        wildcards=frozenset(wildcards),
        exceptions=frozenset(exceptions),
    )


def ensure_psl_and_load() -> PublicSuffixList:
    """
    Ensure PSL file exists and is fresh, then load and parse it.

    Downloads the PSL if missing or stale (>30 days old).

    Returns:
        Parsed PublicSuffixList data structure
    """
    if is_psl_stale(PSL_FILE):
        print("  Downloading fresh Public Suffix List...")
        download_psl(PSL_FILE)
        print(f"  Saved to {PSL_FILE}")
    else:
        print(f"  Using cached {PSL_FILE}")

    return load_public_suffix_list(PSL_FILE)


def get_registrable_domain(domain: str, psl: PublicSuffixList) -> str:
    """
    Extract the registrable (base) domain respecting public suffixes.

    The registrable domain is the public suffix plus one label.
    For public suffixes like github.io, this preserves user.github.io
    rather than incorrectly stripping to github.io.

    Args:
        domain: Full domain name (lowercase)
        psl: Parsed Public Suffix List

    Returns:
        Registrable base domain

    Examples:
        www.example.com -> example.com
        api.foo.github.io -> foo.github.io (github.io is public suffix)
        www.example.co.uk -> example.co.uk (co.uk is public suffix)
        sub.example.ck -> example.ck (*.ck wildcard rule)
        www.ck -> www.ck (!www.ck exception)
    """
    labels = domain.split(".")
    num_labels = len(labels)

    # Single-label domains cannot be stripped further
    if num_labels < 2:
        return domain

    # Check from longest possible suffix to shortest
    for i in range(num_labels):
        # Build candidate suffix from position i to end
        candidate = ".".join(labels[i:])

        # Check exception rules first (highest priority)
        if candidate in psl.exceptions:
            # This is an exception - the candidate itself is registrable
            if i == 0:
                return domain
            return ".".join(labels[i - 1 :])

        # Check exact match
        if candidate in psl.exact:
            # Found public suffix at position i
            # Registrable domain = one label before suffix + suffix
            if i == 0:
                # Domain is exactly a public suffix (e.g., "com")
                return domain
            return ".".join(labels[i - 1 :])

        # Check wildcard rules: if parent is a wildcard suffix
        if len(labels) > i + 1:
            parent = ".".join(labels[i + 1 :])
            if parent in psl.wildcards:
                # *.parent is a wildcard rule, so candidate is a public suffix
                if i == 0:
                    return domain
                return ".".join(labels[i - 1 :])

    # No public suffix found - treat TLD as suffix, return domain.tld
    return ".".join(labels[-2:])


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


@dataclass
class Whitelist:
    """Whitelist containing exact domains and wildcard patterns."""

    exact: set[str]
    wildcards: list[str]

    def is_whitelisted(self, domain: str) -> bool:
        """
        Check if domain matches whitelist.

        Args:
            domain: Domain to check

        Returns:
            True if domain is whitelisted
        """
        # Check exact match first (O(1))
        if domain in self.exact:
            return True

        # Check wildcard patterns (O(W) where W is number of wildcards)
        for pattern in self.wildcards:
            if pattern.startswith("*."):
                # Match *.example.com against example.com and all subdomains
                suffix = pattern[2:]  # Remove *.
                if domain == suffix or domain.endswith("." + suffix):
                    return True
        return False


@dataclass
class ListState:
    """State tracking for a single blocklist."""

    url: str
    content_hash: str
    last_fetch_date: str
    last_changed_date: str
    fetch_count: int
    change_count: int
    consecutive_failures: int
    nsfw: bool


@dataclass
class CompilationState:
    """Overall compilation state."""

    lists: dict[str, ListState]
    last_compilation: str
    compilation_count: int
    skipped_compilations: int
    purged_lists: list[dict]


def load_state() -> CompilationState:
    """Load state from disk, create new if missing."""
    if not STATE_FILE.exists():
        return CompilationState(
            lists={},
            last_compilation="",
            compilation_count=0,
            skipped_compilations=0,
            purged_lists=[],
        )

    with STATE_FILE.open() as f:
        data = json.load(f)

    # Convert dict to dataclass instances
    lists = {
        name: ListState(**state_dict)
        for name, state_dict in data.get("lists", {}).items()
    }

    return CompilationState(
        lists=lists,
        last_compilation=data.get("last_compilation", ""),
        compilation_count=data.get("compilation_count", 0),
        skipped_compilations=data.get("skipped_compilations", 0),
        purged_lists=data.get("purged_lists", []),
    )


def save_state(state: CompilationState) -> None:
    """Persist state to disk."""
    data = {
        "lists": {
            name: {
                "url": s.url,
                "content_hash": s.content_hash,
                "last_fetch_date": s.last_fetch_date,
                "last_changed_date": s.last_changed_date,
                "fetch_count": s.fetch_count,
                "change_count": s.change_count,
                "consecutive_failures": s.consecutive_failures,
                "nsfw": s.nsfw,
            }
            for name, s in state.lists.items()
        },
        "last_compilation": state.last_compilation,
        "compilation_count": state.compilation_count,
        "skipped_compilations": state.skipped_compilations,
        "purged_lists": state.purged_lists,
    }

    with STATE_FILE.open("w") as f:
        json.dump(data, f, indent=2)


def check_and_purge_stale_lists(
    state: CompilationState,
    blocklists_config: list[dict],
    current_time: datetime,
) -> tuple[list[dict], bool]:
    """
    Identify stale lists (no updates for 180 days) and remove them.

    Args:
        state: Current compilation state
        blocklists_config: List of blocklist configurations
        current_time: Current UTC datetime

    Returns:
        Tuple of (active_lists, purge_occurred)
    """
    active_lists = []
    purged_any = False

    for blocklist in blocklists_config:
        name = blocklist["name"]

        # Check for manual preservation flag
        if blocklist.get("preserve", False):
            active_lists.append(blocklist)
            continue

        state_entry = state.lists.get(name)

        if state_entry and state_entry.last_changed_date:
            last_changed_dt = datetime.fromisoformat(
                state_entry.last_changed_date.replace("Z", "+00:00")
            )
            days_stale = (current_time - last_changed_dt).days

            if days_stale > STALE_THRESHOLD_DAYS:
                print(f"WARNING: Purging stale list: {name}")
                print(
                    f"         No updates for {days_stale} days "
                    f"(threshold: {STALE_THRESHOLD_DAYS})"
                )

                state.purged_lists.append(
                    {
                        "name": name,
                        "url": blocklist["url"],
                        "last_changed": state_entry.last_changed_date,
                        "purged_date": current_time.isoformat(),
                        "reason": f"No updates for {days_stale} days",
                    }
                )

                # Remove from state tracking
                del state.lists[name]

                purged_any = True
                continue

        active_lists.append(blocklist)

    return active_lists, purged_any


def should_force_compile(state: CompilationState, current_time: datetime) -> bool:
    """
    Check if compilation should be forced regardless of changes.

    Runs weekly compilation on Sunday at midnight UTC to handle:
    - Missed updates due to hash detection issues
    - State corruption recovery
    - System verification

    Args:
        state: Current compilation state
        current_time: Current UTC datetime

    Returns:
        True if compilation should be forced
    """
    if not state.last_compilation:
        return True  # First run

    last_compile = datetime.fromisoformat(state.last_compilation.replace("Z", "+00:00"))

    # Force if >7 days since last compilation
    hours_since = (current_time - last_compile).total_seconds() / 3600

    # Also check if on Sunday (weekday 6) during midnight hour UTC
    is_sunday_midnight = current_time.weekday() == 6 and current_time.hour == 0

    return hours_since >= 168 or is_sunday_midnight  # 168 hours = 7 days


# Domain validation per RFC 1035: max 253 chars total, 63 per label
_DOMAIN_REGEX = r"[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*"

HOSTS_PATTERN = re.compile(
    rf"^(?:0\.0\.0\.0|127\.0\.0\.1|::1?)[\s\t]+({_DOMAIN_REGEX})"
)
RAW_DOMAIN_PATTERN = re.compile(rf"^({_DOMAIN_REGEX})$")
ADBLOCK_PATTERN = re.compile(rf"^\|\|({_DOMAIN_REGEX})\^")


def fetch_and_hash_streaming(
    name: str, url: str, timeout: int = REQUEST_TIMEOUT
) -> tuple[str, str, Iterator[str], str]:
    """
    Fetch blocklist content and compute SHA256 hash.

    curl_cffi doesn't support true streaming (iter_content raises NotImplementedError).
    Fetch full response, compute hash, then yield lines one at a time.

    Args:
        name: Name of the blocklist
        url: URL of the blocklist
        timeout: Request timeout in seconds

    Returns:
        Tuple of (name, url, line iterator, content_hash)

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

        # Compute SHA256 hash of raw content
        content_hash = hashlib.sha256(response_text.encode("utf-8")).hexdigest()

        def line_generator():
            for line in response_text.split("\n"):
                yield line.rstrip("\r")

        return name, url, line_generator(), content_hash
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


def parse_domains_stream(lines, psl: PublicSuffixList):
    """
    Extract domains from line iterator, strip to base domain, yield one at a time.

    Support hosts files, raw domain lists, and Adblock Plus filters.
    Domains are stripped to their registrable base domain before yielding.

    Args:
        lines: Iterator of lines from blocklist
        psl: Parsed Public Suffix List for base domain extraction

    Yields:
        Registrable base domain names
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
                    base_domain = get_registrable_domain(domain, psl)
                    yield base_domain
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


def load_whitelist(whitelist_path: Path = Path("whitelist.txt")) -> Whitelist:
    """
    Load whitelist from file.

    Format: one domain per line, supports wildcards (*.example.com)
    Lines starting with # are comments.

    Args:
        whitelist_path: Path to whitelist file

    Returns:
        Whitelist object containing exact domains and wildcard patterns
    """
    exact: set[str] = set()
    wildcards: list[str] = []

    if not whitelist_path.exists():
        print(f"Note: {whitelist_path} not found, proceeding without whitelist")
        return Whitelist(exact=exact, wildcards=wildcards)

    with whitelist_path.open() as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            domain = line.lower()
            if domain.startswith("*."):
                wildcards.append(domain)
            else:
                exact.add(domain)

    total = len(exact) + len(wildcards)
    if total > 0:
        print(f"Loaded whitelist: {len(exact)} exact, {len(wildcards)} wildcard(s)")
    return Whitelist(exact=exact, wildcards=wildcards)


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


def collect_blocklists_with_hashes(
    blocklists: list[dict[str, str]],
    output_file: Path,
    state: CompilationState,
    psl: PublicSuffixList,
) -> tuple[dict[str, int], dict[int, str], dict[str, str], bool]:
    """
    Fetch all blocklists, compute hashes, and check for changes.

    Format per line: domain<TAB>list_id<TAB>is_general
    where is_general is 1 for non-NSFW lists and 0 otherwise.
    Domains are stripped to their registrable base domain before writing.

    Args:
        blocklists: List of blocklist configurations
        output_file: Path to write annotated stream
        state: Current compilation state for hash comparison
        psl: Parsed Public Suffix List for base domain extraction

    Returns:
        Tuple of (list_stats, id_to_name, new_hashes, any_changed)
    """
    list_stats: dict[str, int] = {}
    name_to_id = {bl["name"]: idx for idx, bl in enumerate(blocklists)}
    id_to_name = {idx: bl["name"] for idx, bl in enumerate(blocklists)}
    new_hashes: dict[str, str] = {}
    any_changed = False

    with output_file.open("w") as f_out:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_blocklist = {
                executor.submit(fetch_and_hash_streaming, bl["name"], bl["url"]): bl
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
                    _, _, lines, content_hash = future.result()
                    new_hashes[name] = content_hash

                    # Check if hash changed
                    old_state = state.lists.get(name)
                    if old_state:
                        if old_state.content_hash != content_hash:
                            print("  → Content CHANGED (hash mismatch)")
                            any_changed = True
                        else:
                            print("  → Content unchanged (hash match)")
                    else:
                        print("  → New list (no previous state)")
                        any_changed = True

                    # Write domains to annotated stream (stripped to base domains)
                    count = 0
                    for domain in parse_domains_stream(lines, psl):
                        f_out.write(f"{domain}\t{list_id}\t{is_general_flag}\n")
                        count += 1

                    list_stats[name] = count
                    print(f"  → Found {count:,} domains")

                except Exception as e:
                    print(f"  → Error: {e}", file=sys.stderr)
                    list_stats[name] = 0

                    # Track consecutive failures
                    if name in state.lists:
                        state.lists[name].consecutive_failures += 1

    return list_stats, id_to_name, new_hashes, any_changed


def process_annotated_pipeline(
    pipeline: PipelineFiles,
    id_to_name: dict[int, str],
    whitelist: Whitelist,
) -> tuple[int, int, ContributionStats, int]:
    """
    Process annotated stream through sort → streaming group-by pipeline.

    Single external sort by domain, then streaming group-by that:
    - Writes deduplicated domains to ALL output (sorted)
    - Writes deduplicated domains to GENERAL output (sorted, derived in same pass)
    - Computes per-list contribution counters for both aggregates
    - Filters out whitelisted domains

    Contribution metric: domains appearing in exactly one list within each aggregate.
    This matches "how many domains would disappear if list were removed."

    Args:
        pipeline: PipelineFiles containing input/output paths
        id_to_name: Mapping of list IDs to names
        whitelist: Whitelist object for domain filtering

    Returns:
        Tuple of (all_count, general_count, ContributionStats, whitelisted_count)
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
    whitelisted_count = 0
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
            nonlocal all_count, general_count, whitelisted_count
            if current_domain is None:
                return

            # Check whitelist - skip if domain is whitelisted
            if whitelist.is_whitelisted(current_domain):
                whitelisted_count += 1
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
    return all_count, general_count, stats, whitelisted_count


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
            r"(Use `hosts` for general protection \(~)[^)]+(\))",
            rf"\g<1>{general_formatted} domains\g<2>",
        ),
        (
            r"(Use `hosts_nsfw` for all the same domains in `hosts` \*\*\*plus\*\*\* adult content \(\*\*~)[^)]+(\*\*\))",
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
> **Unique Contribution** shows how many domains would disappear if that source were removed. Sources with low unique counts (~50 or less) provide minimal value and should be considered for removal.

<!-- STATS_END -->"""

    new_content = (
        content[:stats_start]
        + stats_section
        + content[stats_end + len("<!-- STATS_END -->") :]
    )

    # Update acknowledgments section
    ack_start = new_content.find("<!-- ACKNOWLEDGMENTS_START -->")
    ack_end = new_content.find("<!-- ACKNOWLEDGMENTS_END -->")

    if ack_start != -1 and ack_end != -1:
        acknowledgments = build_acknowledgments(blocklists)
        ack_section = f"""<!-- ACKNOWLEDGMENTS_START -->

Thanks to the maintainers of all source blocklists:

{acknowledgments}

<!-- ACKNOWLEDGMENTS_END -->"""

        new_content = (
            new_content[:ack_start]
            + ack_section
            + new_content[ack_end + len("<!-- ACKNOWLEDGMENTS_END -->") :]
        )

    readme_path.write_text(new_content)
    print("Updated README.md with dual statistics tables")


def build_acknowledgments(blocklists: list[dict[str, str]]) -> str:
    """
    Build acknowledgments list from active blocklists.

    Groups blocklists by maintainer and removes duplicates.
    Uses optional acknowledgment fields from blocklist configuration.

    Args:
        blocklists: List of blocklist configurations

    Returns:
        Formatted acknowledgments as markdown list
    """
    # Track unique maintainers: maintainer_name -> (url, description)
    maintainers: dict[str, tuple[str, str]] = {}

    for blocklist in blocklists:
        # Check for optional acknowledgment fields
        maintainer_name = blocklist.get("maintainer_name")
        maintainer_url = blocklist.get("maintainer_url")
        maintainer_desc = blocklist.get("maintainer_description")

        # Only add if all acknowledgment fields are present
        if maintainer_name and maintainer_url and maintainer_desc:
            # Use maintainer_name as key to deduplicate
            if maintainer_name not in maintainers:
                maintainers[maintainer_name] = (maintainer_url, maintainer_desc)

    # Sort by maintainer name alphabetically
    sorted_maintainers = sorted(maintainers.items())

    # Build markdown list
    lines = []
    for maintainer_name, (url, desc) in sorted_maintainers:
        lines.append(f"- [{maintainer_name}]({url}) - {desc}")

    return "\n".join(lines) if lines else "No maintainer information available."


def main() -> int:
    """
    Execute compilation with hash-based change detection.

    Pipeline:
    1. Load state from previous run
    2. Check for stale lists (auto-purge if >180 days)
    3. Fetch all lists + compute hashes concurrently
    4. Compare hashes → skip compilation if unchanged
    5. If changed: run full pipeline
    6. Update state and commit

    Returns:
        Exit code: 0 on success, 1 on error
    """
    print("YAHA - Yet Another Host Aggregator")
    print("=" * 50)

    current_time = datetime.now(timezone.utc)

    try:
        # Step 1: Load state
        print("\nLoading state from previous run...")
        state = load_state()
        print(f"  Previous compilation: {state.last_compilation or 'Never'}")
        print(f"  Total compilations: {state.compilation_count}")
        print(f"  Skipped compilations: {state.skipped_compilations}")

        # Step 2: Load and check for stale lists
        print("\nLoading blocklist configuration...")
        blocklists = load_blocklists()
        print(f"Loaded {len(blocklists)} blocklist(s)")

        print("\nChecking for stale lists...")
        blocklists, purge_occurred = check_and_purge_stale_lists(
            state, blocklists, current_time
        )

        if purge_occurred:
            print("  Saving updated blocklists.json...")
            with Path("blocklists.json").open("w") as f:
                json.dump(blocklists, f, indent=2)
                f.write("\n")  # Trailing newline
            print(f"  Active lists after purge: {len(blocklists)}")
        else:
            print("  No stale lists found")

        # Step 3: Load whitelist
        print("\nLoading whitelist...")
        whitelist = load_whitelist()

        # Step 4: Load Public Suffix List
        print("\nLoading Public Suffix List...")
        psl = ensure_psl_and_load()
        print(
            f"  Loaded {len(psl.exact):,} exact, "
            f"{len(psl.wildcards):,} wildcard, "
            f"{len(psl.exceptions):,} exception rules"
        )

        # Step 5: Fetch + hash all lists concurrently
        blocklists_dir = Path("blocklists")
        blocklists_dir.mkdir(exist_ok=True)

        pipeline = PipelineFiles.create()

        print("\nFetching blocklists and computing hashes...")
        list_stats, id_to_name, new_hashes, any_changed = (
            collect_blocklists_with_hashes(blocklists, pipeline.annotated, state, psl)
        )

        # Step 6: Update state with fetch results
        for blocklist in blocklists:
            name = blocklist["name"]
            is_nsfw = blocklist.get("nsfw", False)
            new_hash = new_hashes.get(name)

            if not new_hash:
                continue  # Fetch failed

            old_state = state.lists.get(name)

            if old_state:
                # Update existing entry
                changed = old_state.content_hash != new_hash
                old_state.last_fetch_date = current_time.isoformat()
                old_state.fetch_count += 1
                old_state.consecutive_failures = 0

                if changed:
                    old_state.content_hash = new_hash
                    old_state.last_changed_date = current_time.isoformat()
                    old_state.change_count += 1
            else:
                # New list
                state.lists[name] = ListState(
                    url=blocklist["url"],
                    content_hash=new_hash,
                    last_fetch_date=current_time.isoformat(),
                    last_changed_date=current_time.isoformat(),
                    fetch_count=1,
                    change_count=1,
                    consecutive_failures=0,
                    nsfw=is_nsfw,
                )

        # Step 7: Decide whether to compile
        force_compile = should_force_compile(state, current_time)

        if not any_changed and not force_compile and not purge_occurred:
            print("\nNo changes detected - skipping compilation")
            print(f"Last compilation was at {state.last_compilation}")
            state.skipped_compilations += 1
            pipeline.cleanup()
            save_state(state)
            return 0

        if force_compile:
            print("\nWARNING: Forcing compilation (weekly schedule)")
        elif purge_occurred:
            print("\nWARNING: Compiling due to purged lists")
        else:
            print("\nChanges detected - proceeding with compilation")

        # Step 8: Run full compilation pipeline
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

        print("\nUpdating README...")
        update_readme(
            blocklists,
            list_stats,
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
