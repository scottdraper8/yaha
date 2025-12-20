<div align="center">

# YAHA - Yet Another Host Aggregator

[![Update Blocklist](https://github.com/scottdraper8/yaha/actions/workflows/update-blocklist.yml/badge.svg)](https://github.com/scottdraper8/yaha/actions/workflows/update-blocklist.yml)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![pre-commit](https://img.shields.io/badge/pre--commit-v4.5.1-FAB040?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)

---

*A blocklist aggregator that compiles multiple sources into a single, deduplicated hosts file.*
*Perfect for applications like [TrackerControl](https://f-droid.org/packages/net.kollnig.missioncontrol.fdroid/) that only support one custom blocklist URL.*

---

</div>

## Usage

**Raw Hosts File URL:**

```text
https://raw.githubusercontent.com/scottdraper8/yaha/main/hosts
```

Copy this URL into any application that supports hosts-based blocking to get unified protection from all configured blocklists.

## How It Works

YAHA runs automatically every 6 hours via GitHub Actions, fetching blocklists concurrently, parsing multiple formats, deduplicating domains, and generating a unified hosts file with statistics.

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': {
    'primaryColor': '#ff79c6',
    'secondaryColor': '#bd93f9',
    'tertiaryColor': '#44475a',
    'mainBkg': '#282a36',
    'nodeBorder': '#ff79c6',
    'clusterBkg': '#44475a',
    'clusterBorder': '#bd93f9',
    'textColor': '#f8f8f2'
}}}%%
flowchart LR
    Sources[("📋 Blocklist<br/>Sources")] --> Fetch

    subgraph Process["⚙️ YAHA Processing"]
        direction LR
        Fetch["🔄 Concurrent<br/>Fetch"] --> Parse["📝 Parse<br/>Formats"]
        Parse --> Dedupe["🔍 Deduplicate<br/>Domains"]
        Dedupe --> Stats["📊 Calculate<br/>Statistics"]
    end

    Stats --> Output[("📄 Unified<br/>Hosts File")]
    Stats --> README["📖 Update<br/>README"]

    Output --> Apps["📱 Applications<br/>(TrackerControl, etc)"]

    style Sources fill:#44475a,stroke:#bd93f9,stroke-width:2px
    style Process fill:#44475a,stroke:#ff79c6,stroke-width:2px
    style Output fill:#44475a,stroke:#50fa7b,stroke-width:2px
    style README fill:#44475a,stroke:#8be9fd,stroke-width:2px
    style Apps fill:#44475a,stroke:#ffb86c,stroke-width:2px
```

**Supported Formats:**

- **Hosts file format**: `0.0.0.0 domain.com` or `127.0.0.1 domain.com`
- **Raw domain lists**: One domain per line
- **Adblock Plus filters**: `||domain.com^`

<!-- STATS_START -->

## Latest Run

<div align="center">

![Total Domains](https://img.shields.io/badge/Total_Unique_Domains-1,030,190-ff79c6?style=for-the-badge&labelColor=282a36)
![Last Updated](https://img.shields.io/badge/Last_Updated-2025--12--20_11:10:34_UTC-bd93f9?style=for-the-badge&labelColor=282a36)

</div>

### Domain Count by Source

Unique Contribution shows domains that appear only in that specific list. A source with 0 unique contributions is entirely covered by other lists.

| Source List | Total Domains | Unique Contribution |
| ----------- | ------------- | ------------------- |
| Steven Black's Unified Hosts | 88,502 | 38,947 |
| OISD Big List | 259,789 | 85,805 |
| Abuse.ch Malware Blocklist | 810 | 1 |
| HaGeZi Multi-pro Extended | 328,737 | 217,842 |
| HaGeZi Threat Intelligence | 624,964 | 466,235 |

<!-- STATS_END -->

## Development

> [!NOTE]
> This section is for developers who want to customize or contribute to YAHA.

### Configuration

Blocklists are configured in `blocklists.json`. The script automatically adapts to any number of blocklists.

**blocklists.json Format:**

```json
[
  {
    "name": "List Name",
    "url": "https://example.com/blocklist.txt"
  }
]
```

Each entry requires:

- `name`: Display name for the blocklist
- `url`: Direct URL to the blocklist file

**Default Sources:**

| Source | URL |
| ------ | --- |
| Steven Black's Unified Hosts | [Steven Black Hosts](https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts) |
| OISD Big List | [OISD](https://big.oisd.nl) |
| Abuse.ch Malware Blocklist | [Abuse.ch](https://urlhaus.abuse.ch/downloads/hostfile/) |
| HaGeZi Multi-pro Extended | [HaGeZi Pro](https://cdn.jsdelivr.net/gh/hagezi/dns-blocklists@latest/hosts/pro.txt) |
| HaGeZi Threat Intelligence | [HaGeZi TIF](https://cdn.jsdelivr.net/gh/hagezi/dns-blocklists@latest/hosts/tif.txt) |

### Performance Configuration

In `compile_blocklist.py`, you can adjust these constants:

- `MAX_WORKERS = 5`: Maximum concurrent blocklist fetches
- `REQUEST_TIMEOUT = 30`: Request timeout in seconds

> [!WARNING]
> If you add many sources or experience rate limiting, adjust `MAX_WORKERS` to control concurrency.

### Local Development Setup

**Prerequisites:**

- Python 3.10 or higher
- Git

**Clone and setup:**

```bash
git clone https://github.com/scottdraper8/yaha.git
cd yaha
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**Install pre-commit hooks:**

```bash
pip install pre-commit
pre-commit install
```

**Run locally:**

```bash
python compile_blocklist.py
```

This fetches all blocklists, parses and deduplicates domains, generates the hosts file, and updates the README with current statistics.

## Acknowledgments

Thanks to the maintainers of the source blocklists:

- [Steven Black](https://github.com/StevenBlack/hosts)
- [OISD](https://oisd.nl/)
- [Abuse.ch](https://abuse.ch/)
- [HaGeZi](https://github.com/hagezi/dns-blocklists)
