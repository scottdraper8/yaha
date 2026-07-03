<div align="center">

# YAHA - Yet Another Host Aggregator

[![Analyze Host Lists](https://img.shields.io/github/actions/workflow/status/scottdraper8/yaha/analyze-host-lists.yml?label=Analyze%20Host%20Lists&logo=github&logoColor=white&color=50fa7b&labelColor=6272a4)](https://github.com/scottdraper8/yaha/actions/workflows/analyze-host-lists.yml)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-bd93f9?logo=python&logoColor=white&labelColor=6272a4)](https://www.python.org/downloads/)
[![uv](https://img.shields.io/badge/uv-managed-ff79c6?logo=astral&logoColor=white&labelColor=6272a4)](https://docs.astral.sh/uv/)
[![pre-commit](https://img.shields.io/badge/pre--commit-4.4.0-f1fa8c?logo=pre-commit&logoColor=282a36&labelColor=6272a4)](https://github.com/pre-commit/pre-commit)
[![curl-cffi](https://img.shields.io/badge/curl--cffi-0.14.0+-8be9fd?logo=curl&logoColor=white&labelColor=6272a4)](https://github.com/yifeikong/curl_cffi)

---

Personal host-file analyzer and whitelist workspace. YAHA aggregates configured
lists for normalization, deduplication, provenance analysis, and maintenance of
devices running tools such as Pi-hole and TrackerControl.

---

</div>

## Purpose

YAHA polls the configured host lists weekly and publishes analytics to this
README. It measures how many domains each source uniquely contributes and flags
sources as removal candidates when they contribute 50 or fewer unique domains or
show no observed content change for 30 days.

This repository intentionally does **not** compile or publish installable host
lists. Others are welcome to fork the project and adapt the analysis and
whitelist to their own devices.

The repository-level [`whitelist.txt`](whitelist.txt) is applied before domain
counts and contribution statistics are calculated, so the report reflects the
effective policy used for the maintained devices.

## How It Works

Runs automatically once a week via GitHub Actions. Sources are fetched in
parallel, normalized, filtered through the whitelist, and deduplicated for
provenance and contribution analysis. The workflow updates only the README and
analysis state; it does not generate or publish a combined host list.

<!-- STATS_START -->

## Latest Run

<div align="center">

![General Domains](https://img.shields.io/badge/General_Domains-5,802,617-8be9fd?style=for-the-badge&labelColor=6272a4)
![Total Domains](https://img.shields.io/badge/Total_Domains_(with_NSFW)-10,642,299-ff79c6?style=for-the-badge&labelColor=6272a4)
![Last Updated](https://img.shields.io/badge/Last_Updated-2026--07--03_14:55:12_UTC-50fa7b?style=for-the-badge&labelColor=6272a4)

### General Host Lists

<table align="center">
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
<tr><td><a href='https://raw.githubusercontent.com/hagezi/nrd/main/adblock/dga30.txt'>HaGeZi DGA 30 Days</a></td><td>2,380,363</td><td>2,334,445</td><td>No</td></tr>
<tr><td><a href='https://cdn.jsdelivr.net/gh/hagezi/dns-blocklists@latest/hosts/tif.txt'>HaGeZi Threat Intelligence</a></td><td>1,824,248</td><td>1,423,995</td><td>No</td></tr>
<tr><td><a href='https://v.firebog.net/hosts/RPiList-Malware.txt'>RPiList Malware</a></td><td>1,039,235</td><td>826,904</td><td>No</td></tr>
<tr><td><a href='https://cdn.jsdelivr.net/gh/hagezi/dns-blocklists@latest/hosts/pro.txt'>HaGeZi Multi-pro Extended</a></td><td>511,403</td><td>326,396</td><td>No</td></tr>
<tr><td><a href='https://raw.githubusercontent.com/RooneyMcNibNug/pihole-stuff/master/SNAFU.txt'>SNAFU</a></td><td>74,766</td><td>70,792</td><td>No</td></tr>
<tr><td><a href='https://big.oisd.nl'>OISD Big List</a></td><td>326,002</td><td>61,488</td><td>No</td></tr>
<tr><td><a href='https://v.firebog.net/hosts/AdguardDNS.txt'>AdGuard DNS Filter</a></td><td>152,286</td><td>55,319</td><td>No</td></tr>
<tr><td><a href='https://lists.cyberhost.uk/malware.txt'>Cyber Threat Coalition Malware</a></td><td>50,365</td><td>31,236</td><td>No</td></tr>
<tr><td><a href='https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts'>Steven Black's Unified Hosts</a></td><td>82,927</td><td>19,945</td><td>No</td></tr>
<tr><td><a href='https://v.firebog.net/hosts/Easyprivacy.txt'>EasyPrivacy</a></td><td>42,586</td><td>13,146</td><td>No</td></tr>
<tr><td><a href='https://v.firebog.net/hosts/RPiList-Phishing.txt'>RPiList Phishing</a></td><td>146,215</td><td>12,905</td><td>No</td></tr>
<tr><td><a href='https://hostfiles.frogeye.fr/firstparty-trackers-hosts.txt'>First-Party Trackers</a></td><td>14,999</td><td>11,432</td><td>No</td></tr>
<tr><td><a href='https://v.firebog.net/hosts/Prigent-Crypto.txt'>Prigent Crypto</a></td><td>11,491</td><td>10,883</td><td>No</td></tr>
<tr><td><a href='https://raw.githubusercontent.com/bigdargon/hostsVN/master/hosts'>hostsVN</a></td><td>18,108</td><td>4,209</td><td>No</td></tr>
<tr><td><a href='https://raw.githubusercontent.com/PolishFiltersTeam/KADhosts/master/KADhosts.txt'>KADhosts</a></td><td>47,890</td><td>2,678</td><td>No</td></tr>
<tr><td><a href='https://raw.githubusercontent.com/DandelionSprout/adfilt/master/Alternate%20versions%20Anti-Malware%20List/AntiMalwareHosts.txt'>DandelionSprout Anti-Malware</a></td><td>12,329</td><td>2,059</td><td>No</td></tr>
<tr><td><a href='https://v.firebog.net/hosts/Prigent-Ads.txt'>Prigent Ads</a></td><td>4,270</td><td>1,516</td><td>No</td></tr>
<tr><td><a href='https://malware-filter.gitlab.io/malware-filter/phishing-filter-hosts.txt'>Phishing Hosts</a></td><td>32,211</td><td>1,169</td><td>No</td></tr>
<tr><td><a href='https://raw.githubusercontent.com/matomo-org/referrer-spam-blacklist/master/spammers.txt'>Matomo Referrer Spam</a></td><td>2,343</td><td>998</td><td>No</td></tr>
<tr><td><a href='https://raw.githubusercontent.com/AssoEchap/stalkerware-indicators/master/generated/hosts'>Stalkerware Indicators</a></td><td>925</td><td>388</td><td>No</td></tr>
</tbody>
</table>
<!-- markdownlint-enable MD013 -->

### NSFW Host Lists

<table align="center">
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
<tr><td><a href='https://v.firebog.net/hosts/Prigent-Adult.txt'>Prigent Adult</a></td><td>4,590,338</td><td>4,431,020</td><td>No</td></tr>
<tr><td><a href='https://nsfw.oisd.nl'>OISD NSFW</a></td><td>364,750</td><td>195,240</td><td>No</td></tr>
<tr><td><a href='https://cdn.jsdelivr.net/gh/hagezi/dns-blocklists@latest/adblock/nsfw.txt'>HaGeZi NSFW</a></td><td>105,402</td><td>45,994</td><td>No</td></tr>
</tbody>
</table>
<!-- markdownlint-enable MD013 -->

</div>

> [!NOTE]
> **Unique Contribution** is the number of domains that would disappear if a
> source were removed. A source is a **Removal Candidate** when it contributes
> 50 or fewer unique domains or has no observed content change for 30 days.
> Sources are never removed automatically.

<!-- STATS_END -->

---

> [!IMPORTANT]
> The section below is ***ONLY*** for developers who want to
> customize or contribute to YAHA.

## Local Development Setup

**Prerequisites:**

- Python 3.11 or higher
- [uv](https://docs.astral.sh/uv/getting-started/installation/) for dependency
  management and the project environment

**Clone and setup:**

```bash
git clone https://github.com/scottdraper8/yaha.git
cd yaha
uv sync
```

**Install pre-commit hooks:**

```bash
uv run pre-commit install
```

**Run locally:**

```bash
# Analyze current sources (skips if nothing changed)
uv run yaha

# Force a complete analysis
uv run yaha --force
```

The analyzer fetches all configured sources, parses and normalizes domains,
applies whitelist filters, calculates deduplication and provenance metrics,
and updates README statistics. It does not generate a combined host file.

### Project Structure

```text
yaha/
├── src/                     # Application source
│   ├── cli.py               # Main orchestrator (business logic)
│   ├── config.py            # Configuration loading and validation
│   ├── domain_processor.py  # Domain extraction and validation
│   ├── fetcher.py           # HTTP fetching with hash computation
│   ├── pipeline.py          # Deduplication and contribution stats
│   └── state_manager.py     # State persistence and staleness checks
├── tests/                   # Unit and integration tests
├── blocklists.json          # Source configuration
├── whitelist.txt            # Domain whitelist
├── state.json               # Runtime state (hashes, timestamps)
├── pyproject.toml           # Project and tool configuration
├── uv.lock                  # Reproducible dependency lock
└── .pre-commit-config.yaml  # Pre-commit hooks
```

### Development Workflow

**Run tests:**

```bash
# Run all tests
uv run pytest

# Run with coverage report
uv run pytest --cov=src --cov-report=term-missing

# Run specific test file
uv run pytest tests/test_domain_processor.py
```

**Code quality checks:**

```bash
# Linting (with auto-fix)
uv run ruff check src/ tests/ --fix

# Formatting
uv run ruff format src/ tests/

# Type checking
uv run mypy src/

# Run all pre-commit hooks
uv run pre-commit run --all-files
```

### Configuration

Blocklists are configured in `blocklists.json`.

**blocklists.json Format:**

```json
[
  {
    "name": "List Name",
    "url": "https://example.com/blocklist.txt",
    "nsfw": false,
    "maintainer_name": "Maintainer Name",
    "maintainer_url": "https://github.com/maintainer",
    "maintainer_description": "Summary used in acknowledgments"
  }
]
```

Each entry requires:

- `name`: Display name for the blocklist
- `url`: Direct URL to the blocklist file

Optional fields:

- `nsfw`: Set to `true` to report the source in the separate NSFW category
- `maintainer_name`: Maintainer's display name for acknowledgments section
- `maintainer_url`: URL to maintainer's repository or website
- `maintainer_description`: Maintainer summary used in acknowledgments

Maintainer fields are grouped and deduplicated in the acknowledgments section.

#### Whitelist Configuration

Domains can be excluded from blocklists using `whitelist.txt`.

**whitelist.txt Format:**

```text
# One domain per line
# Lines starting with # are comments

# Exact domain match
example.com

# Wildcard match (all subdomains)
*.aurorastore.org
```

**Supported patterns:**

- **Exact match**: `example.com` - matches only that domain
- **Wildcard match**: `*.example.com` - matches the domain and all
  subdomains

Whitelisted domains are filtered during the deduplication pass.

### Performance Tuning

In `src/cli.py`, adjust:

- `MAX_WORKERS = 5`: Maximum concurrent source fetches

In `src/fetcher.py`, adjust:

- `REQUEST_TIMEOUT = 90`: HTTP request timeout per attempt
- `MAX_FETCH_ATTEMPTS = 3`: Requests made before a source is reported unavailable

In `src/state_manager.py`:

- `STALE_THRESHOLD_DAYS = 30`: Days without an observed content change
  before a source is flagged as a removal candidate

Sources are never removed automatically.

> [!WARNING]
> If you add many sources or experience rate limiting, reduce
> `MAX_WORKERS` to control concurrency.

## Acknowledgments

<!-- markdownlint-disable MD013 -->
<!-- ACKNOWLEDGMENTS_START -->

Thanks to the maintainers of all source blocklists:

- [AssoEchap](https://github.com/AssoEchap/stalkerware-indicators) - Stalkerware indicators
- [Cyber Threat Coalition](https://cyberthreatcoalition.org/) - Malware blocklist
- [DandelionSprout](https://github.com/DandelionSprout/adfilt) - Anti-Malware List
- [Firebog](https://firebog.net/) - RPiList Phishing/Malware, Prigent collections, AdGuard DNS, EasyPrivacy
- [Frogeye](https://hostfiles.frogeye.fr/) - First-party trackers
- [HaGeZi](https://github.com/hagezi/dns-blocklists) - Multi-pro, Threat Intelligence, DGA, and NSFW lists
- [Malware Filter](https://gitlab.com/malware-filter/phishing-filter) - Phishing filter
- [Matomo](https://github.com/matomo-org/referrer-spam-blacklist) - Referrer spam blacklist
- [OISD](https://oisd.nl/) - Big List & NSFW blocklists
- [Polish Filters Team](https://github.com/PolishFiltersTeam/KADhosts) - KADhosts
- [RooneyMcNibNug](https://github.com/RooneyMcNibNug/pihole-stuff) - SNAFU
- [Steven Black](https://github.com/StevenBlack/hosts) - Unified hosts file
- [bigdargon](https://github.com/bigdargon/hostsVN) - hostsVN

<!-- ACKNOWLEDGMENTS_END -->
<!-- markdownlint-enable MD013 -->
