# TraceViz

**Visualize traceroute paths on a world map.**
Traceroute 路径可视化工具 —— 在世界地图上展示网络数据包的旅行路径。

[![PyPI](https://img.shields.io/pypi/v/traceviz)](https://pypi.org/project/traceviz/)
![Python](https://img.shields.io/badge/Python-3.12+-blue)
![License](https://img.shields.io/badge/License-MIT-green)
[![CI](https://github.com/shixy96/traceviz/actions/workflows/ci.yml/badge.svg)](https://github.com/shixy96/traceviz/actions/workflows/ci.yml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

<!-- TODO: Add screenshot -->

## Features / 功能特性

- Run traceroute and visualize each hop on an interactive world map
- Auto-detect Chinese ISP backbone segments (ChinaTelecom 163/CN2, ChinaUnicom CUNet, ChinaMobile CMI, etc.)
- Latency spike detection — automatically flag possible transoceanic hops
- Cross-platform: macOS / Linux / Windows
- ICMP and UDP probe modes
- Pure JSON output for scripting
- Built-in demo mode — try the frontend without running a real traceroute

## Installation / 安装

```bash
# Recommended: using uv
uv tool install traceviz

# Or using pip
pip install traceviz
```

> Homebrew formula coming soon.

## Usage / 使用

```bash
# Basic — trace to google.com and open the map in your browser
traceviz google.com

# ICMP mode (better penetration, requires sudo/admin)
sudo traceviz google.com --icmp

# JSON-only output
traceviz google.com --json

# Demo mode (simulated data)
traceviz --demo google.com

# Custom parameters
traceviz google.com --max-hops 20 --queries 3 --wait 3

# Use an ipinfo.io token for higher query limits
traceviz google.com --token YOUR_TOKEN
```

### CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `target` | Target domain or IP address | (required) |
| `--max-hops` | Maximum number of hops | 30 |
| `--port` | Local server port | 8890 |
| `--token` | ipinfo.io API token | — |
| `--icmp` | Use ICMP mode | off |
| `--wait` | Timeout per hop (seconds) | 2 |
| `-q, --queries` | Probes per hop | 2 |
| `--json` | JSON output only, no server | off |
| `--demo` | Use simulated demo data | off |

## How It Works / 工作原理

1. **Traceroute** — runs the system `traceroute` / `tracert` command and parses each hop's IP and RTT
2. **IP Lookup** — queries ipinfo.io for geolocation and ASN data; matches built-in backbone rules
3. **Analysis** — detects latency spikes (>100 ms jump → possible ocean crossing) and classifies network segments
4. **Visualization** — starts a local Flask server and renders the path on a Leaflet world map

## Requirements / 系统要求

- Python 3.12+
- `traceroute` (macOS / Linux) or `tracert` (Windows, built-in)
  - Ubuntu / Debian: `sudo apt install traceroute`

## Development / 开发

```bash
# Clone
git clone https://github.com/shixy96/traceviz.git
cd traceviz

# Install dev dependencies
uv sync --extra dev

# Install locally as a tool
uv tool install .

# Run tests
uv run pytest

# Lint
uv run ruff check traceviz/
```

To publish a new version, tag and push — GitHub Actions will handle the PyPI release:

```bash
git tag v0.1.0
git push --tags
```

## License

[MIT](LICENSE)
