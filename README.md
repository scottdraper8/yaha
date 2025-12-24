<div align="center">

# YAHA - Yet Another Host Aggregator

[![Update Blocklist](https://github.com/scottdraper8/yaha/actions/workflows/update-blocklist.yml/badge.svg)](https://github.com/scottdraper8/yaha/actions/workflows/update-blocklist.yml)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![pre-commit](https://img.shields.io/badge/pre--commit-v4.5.1-FAB040?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)

---

*A blocklist aggregator that compiles multiple sources into two optimized hosts files: one for general protection (ads, trackers, malware) and one including NSFW content blocking.*
*Perfect for applications like [TrackerControl](https://f-droid.org/packages/net.kollnig.missioncontrol.fdroid/) that only support one blocklist URL.*

---

</div>

## Usage

**General Protection (Ads, Trackers, Malware):**

```text
https://github.com/scottdraper8/yaha/releases/download/latest/hosts
```

**Complete Protection (Including NSFW Content):**

```text
https://github.com/scottdraper8/yaha/releases/download/latest/hosts_nsfw
```

> [!TIP]
> Copy either URL into any application that supports hosts-based blocking:
>
> - Use `hosts` for general protection (~4.3M domains)
> - Use `hosts_nsfw` for all the same domains in `hosts` ***plus*** adult content (**~9.3M domains**)

## How It Works

YAHA runs automatically every 6 hours via GitHub Actions, fetching blocklists concurrently, parsing multiple formats (hosts, raw domains, Adblock Plus), sorting and deduplicating via streaming algorithms, and generating unified hosts files with statistics.

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
    Sources[("📋 Blocklist<br/>Sources<br/>(24 General + 3 NSFW)")] --> Fetch

    subgraph Process["⚙️ YAHA Processing"]
        direction LR
        Fetch["🔄 Concurrent<br/>Fetch"] --> Parse["📝 Parse<br/>Formats"]
        Parse --> Dedupe["🔍 Deduplicate<br/>& Separate"]
        Dedupe --> Stats["📊 Calculate<br/>Statistics"]
    end

    Stats --> Output1[("📄 hosts<br/>(General Only)<br/>4.3M domains")]
    Stats --> Output2[("🔞 hosts_nsfw<br/>(Complete)<br/>9.3M domains")]
    Stats --> README["📖 Update README<br/>(Dual Tables)"]

    Output1 --> Apps["📱 Applications<br/>(TrackerControl, etc)"]
    Output2 --> Apps

    style Sources fill:#44475a,stroke:#bd93f9,stroke-width:2px
    style Process fill:#44475a,stroke:#ff79c6,stroke-width:2px
    style Output1 fill:#44475a,stroke:#50fa7b,stroke-width:2px
    style Output2 fill:#44475a,stroke:#ff79c6,stroke-width:2px
    style README fill:#44475a,stroke:#8be9fd,stroke-width:2px
    style Apps fill:#44475a,stroke:#ffb86c,stroke-width:2px
```

> [!NOTE]
> **Supported Formats:**
>
> - **Hosts file format**: `0.0.0.0 domain.com` or `127.0.0.1 domain.com`
> - **Raw domain lists**: One domain per line
> - **Adblock Plus filters**: `||domain.com^`

<!-- STATS_START -->

## Latest Run

<div align="center">

![General Domains](https://img.shields.io/badge/General_Domains-3,749,794-8be9fd?style=for-the-badge&labelColor=6272a4)
![Total Domains](https://img.shields.io/badge/Total_Domains_(with_NSFW)-8,602,394-ff79c6?style=for-the-badge&labelColor=6272a4)
![Last Updated](https://img.shields.io/badge/Last_Updated-2025--12--24_12:35:19_UTC-50fa7b?style=for-the-badge&labelColor=6272a4)

### General Protection Lists

<table align="center">
<thead>
<tr>
<th>Source List</th>
<th>Total Domains</th>
<th>Unique Contribution</th>
</tr>
</thead>
<tbody>
<tr><td><a href='https://cdn.jsdelivr.net/gh/hagezi/dns-blocklists@latest/domains/dga30.txt'>HaGeZi DGA 30 Days</a></td><td>2,213,326</td><td>2,192,451</td></tr>
<tr><td><a href='https://cdn.jsdelivr.net/gh/hagezi/dns-blocklists@latest/hosts/tif.txt'>HaGeZi Threat Intelligence</a></td><td>623,890</td><td>417,102</td></tr>
<tr><td><a href='https://v.firebog.net/hosts/RPiList-Malware.txt'>RPiList Malware</a></td><td>301,338</td><td>233,606</td></tr>
<tr><td><a href='https://cdn.jsdelivr.net/gh/hagezi/dns-blocklists@latest/hosts/pro.txt'>HaGeZi Multi-pro Extended</a></td><td>327,681</td><td>194,812</td></tr>
<tr><td><a href='https://raw.githubusercontent.com/RooneyMcNibNug/pihole-stuff/master/SNAFU.txt'>SNAFU</a></td><td>71,907</td><td>65,755</td></tr>
<tr><td><a href='https://v.firebog.net/hosts/RPiList-Phishing.txt'>RPiList Phishing</a></td><td>165,937</td><td>55,824</td></tr>
<tr><td><a href='https://v.firebog.net/hosts/AdguardDNS.txt'>AdGuard DNS Filter</a></td><td>120,533</td><td>43,148</td></tr>
<tr><td><a href='https://big.oisd.nl'>OISD Big List</a></td><td>223,291</td><td>33,317</td></tr>
<tr><td><a href='https://raw.githubusercontent.com/anudeepND/blacklist/master/adservers.txt'>Anudeep's Blacklist</a></td><td>42,521</td><td>31,069</td></tr>
<tr><td><a href='https://hostfiles.frogeye.fr/firstparty-trackers-hosts.txt'>First-Party Trackers</a></td><td>31,837</td><td>22,924</td></tr>
<tr><td><a href='https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts'>Steven Black's Unified Hosts</a></td><td>88,502</td><td>18,466</td></tr>
<tr><td><a href='https://v.firebog.net/hosts/Easyprivacy.txt'>EasyPrivacy</a></td><td>42,217</td><td>16,681</td></tr>
<tr><td><a href='https://v.firebog.net/hosts/Prigent-Crypto.txt'>Prigent Crypto</a></td><td>16,288</td><td>15,885</td></tr>
<tr><td><a href='https://lists.cyberhost.uk/malware.txt'>Cyber Threat Coalition Malware</a></td><td>20,229</td><td>14,965</td></tr>
<tr><td><a href='https://raw.githubusercontent.com/Spam404/lists/master/main-blacklist.txt'>Spam404</a></td><td>8,140</td><td>6,448</td></tr>
<tr><td><a href='https://raw.githubusercontent.com/bigdargon/hostsVN/master/hosts'>hostsVN</a></td><td>19,179</td><td>4,610</td></tr>
<tr><td><a href='https://raw.githubusercontent.com/PolishFiltersTeam/KADhosts/master/KADhosts.txt'>KADhosts</a></td><td>57,294</td><td>3,916</td></tr>
<tr><td><a href='https://raw.githubusercontent.com/DandelionSprout/adfilt/master/Alternate%20versions%20Anti-Malware%20List/AntiMalwareHosts.txt'>DandelionSprout Anti-Malware</a></td><td>15,187</td><td>3,080</td></tr>
<tr><td><a href='https://raw.githubusercontent.com/matomo-org/referrer-spam-blacklist/master/spammers.txt'>Matomo Referrer Spam</a></td><td>2,322</td><td>1,970</td></tr>
<tr><td><a href='https://v.firebog.net/hosts/Prigent-Ads.txt'>Prigent Ads</a></td><td>4,270</td><td>1,147</td></tr>
<tr><td><a href='https://malware-filter.gitlab.io/malware-filter/phishing-filter-hosts.txt'>Phishing Hosts</a></td><td>20,389</td><td>1,068</td></tr>
<tr><td><a href='https://raw.githubusercontent.com/AssoEchap/stalkerware-indicators/master/generated/hosts'>Stalkerware Indicators</a></td><td>919</td><td>540</td></tr>
<tr><td><a href='https://raw.githubusercontent.com/crazy-max/WindowsSpyBlocker/master/data/hosts/spy.txt'>Windows Spy Blocker</a></td><td>347</td><td>256</td></tr>
<tr><td><a href='https://v.firebog.net/hosts/static/w3kbl.txt'>W3KBL</a></td><td>355</td><td>90</td></tr>
</tbody>
</table>

### NSFW Blocking Lists

<table align="center">
<thead>
<tr>
<th>Source List</th>
<th>Total Domains</th>
<th>Unique Contribution</th>
</tr>
</thead>
<tbody>
<tr><td><a href='https://v.firebog.net/hosts/Prigent-Adult.txt'>Prigent Adult</a></td><td>4,646,353</td><td>4,409,620</td></tr>
<tr><td><a href='https://nsfw.oisd.nl'>OISD NSFW</a></td><td>412,395</td><td>220,593</td></tr>
<tr><td><a href='https://cdn.jsdelivr.net/gh/hagezi/dns-blocklists@latest/adblock/nsfw.txt'>HaGeZi NSFW</a></td><td>84,878</td><td>32,421</td></tr>
</tbody>
</table>

</div>

> [!NOTE]
> **Unique Contribution** shows how many domains would disappear if that source were removed. Sources with low unique counts (~50 or less) provide minimal value and should be considered for removal.

<!-- STATS_END -->

---

> [!IMPORTANT]
> The section below is ***ONLY*** for developers who want to customize or contribute to YAHA.

## Local Development Setup

**Prerequisites:**

- Python 3.10 or higher

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

### Performance Configuration

In `compile_blocklist.py`, you can adjust these constants:

- `MAX_WORKERS = 5`: Maximum concurrent blocklist fetches
- `REQUEST_TIMEOUT = 30`: Request timeout in seconds

> [!WARNING]
> If you add many sources or experience rate limiting, adjust `MAX_WORKERS` to control concurrency.

## Acknowledgments

Thanks to the maintainers of all source blocklists:

- [Steven Black](https://github.com/StevenBlack/hosts) - Unified hosts file
- [OISD](https://oisd.nl/) - Big List & NSFW blocklists
- [HaGeZi](https://github.com/hagezi/dns-blocklists) - Multi-pro, Threat Intelligence, DGA, and NSFW lists
- [Firebog](https://firebog.net/) - RPiList Phishing/Malware, Prigent collections, AdGuard DNS, EasyPrivacy, W3KBL
- [RooneyMcNibNug](https://github.com/RooneyMcNibNug/pihole-stuff) - SNAFU
- [Anudeep ND](https://github.com/anudeepND/blacklist) - Adservers blacklist
- [Frogeye](https://hostfiles.frogeye.fr/) - First-party trackers
- [Cyber Threat Coalition](https://cyberthreatcoalition.org/) - Malware blocklist
- [Spam404](https://github.com/Spam404/lists) - Main blacklist
- [Polish Filters Team](https://github.com/PolishFiltersTeam/KADhosts) - KADhosts
- [bigdargon](https://github.com/bigdargon/hostsVN) - hostsVN
- [DandelionSprout](https://github.com/DandelionSprout/adfilt) - Anti-Malware List
- [Matomo](https://github.com/matomo-org/referrer-spam-blacklist) - Referrer spam blacklist
- [AssoEchap](https://github.com/AssoEchap/stalkerware-indicators) - Stalkerware indicators
- [crazy-max](https://github.com/crazy-max/WindowsSpyBlocker) - Windows Spy Blocker
- [Malware Filter](https://gitlab.com/malware-filter/phishing-filter) - Phishing filter
