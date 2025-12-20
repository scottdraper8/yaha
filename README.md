# YAHA - Yet Another Host Aggregator

[![Update Blocklist](https://github.com/YOUR_USERNAME/yaha/actions/workflows/update-blocklist.yml/badge.svg)](https://github.com/YOUR_USERNAME/yaha/actions/workflows/update-blocklist.yml)

> A consolidated Pi-hole blocklist aggregator that compiles multiple trusted sources into a single, deduplicated hosts file.

## 🎯 Overview

YAHA automatically fetches, processes, and merges multiple blocklists into one optimized hosts file.
It eliminates duplicates, tracks domain contributions from each source, and updates every 6 hours via
GitHub Actions.

### Why YAHA?

- **Consolidated Management**: One URL instead of managing multiple blocklist subscriptions
- **Duplicate Elimination**: Removes redundant entries across lists
- **Transparency**: See exactly which lists contribute unique domains
- **Always Fresh**: Automatic updates every 6 hours
- **Open Source**: Review the code, fork it, customize it

## 📋 Blocklist Sources

This aggregator combines the following trusted blocklists:

| Source | Description | URL |
|--------|-------------|-----|
| **Steven Black's Unified Hosts** | Unified hosts with adware and malware | [Link](https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts) |
| **OISD Big List** | Comprehensive domain blocklist | [Link](https://big.oisd.nl) |
| **Abuse.ch Malware Blocklist** | Malware and botnet domains | [Link](https://urlhaus.abuse.ch/downloads/hostfile/) |
| **HaGeZi Multi-pro Extended** | Pro-level extended protection | [Link](https://cdn.jsdelivr.net/gh/hagezi/dns-blocklists@latest/hosts/pro.txt) |
| **HaGeZi Threat Intelligence** | Threat intelligence feeds | [Link](https://cdn.jsdelivr.net/gh/hagezi/dns-blocklists@latest/hosts/tif.txt) |

<!-- STATS_START -->

## 📊 Statistics

**Last Updated:** 2025-12-20 09:29:30 UTC
**Last Run:** 2025-12-20 09:29:30 UTC
**Total Unique Domains:** 943,737

### Domain Count by Source

| Source List | Total Domains | Unique Contribution |
|-------------|---------------|---------------------|
| Steven Black's Unified Hosts | 88,510 | 42,298 |
| OISD Big List | 0 | 0 |
| Abuse.ch Malware Blocklist | 0 | 0 |
| HaGeZi Multi-pro Extended | 328,109 | 262,897 |
| HaGeZi Threat Intelligence | 624,964 | 550,988 |

<!-- STATS_END -->

## 🚀 Usage with Pi-hole

### Option 1: Use the Raw GitHub URL

1. Log into your Pi-hole admin interface
1. Navigate to **Group Management** → **Adlists**
1. Add the following URL:

```text
https://raw.githubusercontent.com/YOUR_USERNAME/yaha/main/hosts
```

1. Update gravity: `pihole -g`

### Option 2: Use GitHub Pages (if enabled)

```text
https://YOUR_USERNAME.github.io/yaha/hosts
```

## 🛠️ Local Development

### Prerequisites

- Python 3.11 or higher
- Git

### Setup

1. Clone the repository:

```bash
git clone https://github.com/YOUR_USERNAME/yaha.git
cd yaha
```

1. Create and activate virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

1. Install dependencies:

```bash
pip install -r requirements.txt
```

1. Install pre-commit hooks:

```bash
pip install pre-commit
pre-commit install
```

### Running Manually

Execute the compilation script:

```bash
python compile_blocklist.py
```

The script will:

- Fetch all blocklists
- Parse and deduplicate domains
- Generate the unified `hosts` file
- Update README with statistics
- Display analysis of unique contributions per list

## 🔄 Automation

The blocklist updates automatically every 6 hours via GitHub Actions. The workflow:

1. Fetches all source blocklists
2. Deduplicates domains
3. Calculates statistics
4. Updates the hosts file (if changes detected)
5. Commits changes with domain count in message
6. Updates README with latest run timestamp

You can also trigger a manual update from the Actions tab in GitHub.

## 📊 Understanding the Statistics

- **Total Domains**: Total entries before deduplication
- **Unique Contribution**: Domains that only appear in that specific list
- **Overlap Analysis**: Helps identify which lists provide redundant coverage

If a list shows 0 unique contributions, it might be entirely covered by other lists and
could be removed to optimize update times.

## 🤝 Contributing

Contributions are welcome! Feel free to:

- Report issues
- Suggest new blocklists
- Improve documentation
- Submit pull requests

## 📝 License

This project is open source and available under the MIT License.

## ⚠️ Disclaimer

This blocklist aggregator is provided as-is. Always review blocklists before deploying to
production. False positives may occur. The maintainers are not responsible for blocked or
unblocked content.

## 🙏 Acknowledgments

Massive thanks to the maintainers of the source blocklists:

- [Steven Black](https://github.com/StevenBlack/hosts)
- [OISD](https://oisd.nl/)
- [Abuse.ch](https://abuse.ch/)
- [HaGeZi](https://github.com/hagezi/dns-blocklists)

---

## Made with ❤️ for the Pi-hole community
