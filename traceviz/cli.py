"""CLI entry point."""

import argparse
import json
import sys
import threading
import webbrowser

from .analyzer import LATENCY_JUMP_THRESHOLD, analyze
from .ip_lookup import IPInfo, lookup_ip, lookup_ips
from .tracer import Hop, _resolve_target, run_traceroute, stream_traceroute


def main():
    parser = argparse.ArgumentParser(
        prog="traceviz",
        description="Traceroute visualization - display network paths on a world map",
    )
    parser.add_argument("target", help="Target domain or IP address")
    parser.add_argument("--max-hops", type=int, default=30, help="Max hops (default 30)")
    parser.add_argument("--port", type=int, default=8890, help="Local server port (default 8890)")
    parser.add_argument("--token", help="ipinfo.io API token (optional, increases rate limit)")
    parser.add_argument("--icmp", action="store_true", help="Use ICMP mode (better penetration, requires root)")
    parser.add_argument("--wait", type=int, default=2, help="Timeout per hop in seconds (default 2)")
    parser.add_argument("--queries", "-q", type=int, default=2, help="Probes per hop (default 2)")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output JSON only, no server")
    parser.add_argument("--demo", action="store_true", help="Use mock data to demo the frontend")
    args = parser.parse_args()

    if args.demo:
        results, target = _demo_data(args.target)
        return _serve_or_print(results, target, args)

    if args.json_output:
        _run_batch(args)
    else:
        _run_streaming(args)


def _run_batch(args):
    """Batch mode: run traceroute, lookup all IPs, then output."""
    mode = "ICMP" if args.icmp else "UDP"
    print(f"Tracing {args.target}, max {args.max_hops} hops, {mode} mode...", file=sys.stderr)
    try:
        hops = run_traceroute(args.target, max_hops=args.max_hops, icmp=args.icmp, wait=args.wait, queries=args.queries)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not hops:
        print("Error: traceroute returned no hop data", file=sys.stderr)
        sys.exit(1)

    ips = [h.ip for h in hops if h.ip]
    ip_infos = lookup_ips(ips, token=args.token)
    target_ip = _resolve_target(args.target)
    results = analyze(hops, ip_infos, target_ip=target_ip)
    _serve_or_print(results, args.target, args)


def _run_streaming(args):
    """Streaming mode: print each hop as it arrives."""
    target_ip = _resolve_target(args.target)
    mode = "ICMP" if args.icmp else "UDP"
    print(f"\nTracing {args.target} ({target_ip}), max {args.max_hops} hops, {mode} mode\n")

    hops: list[Hop] = []
    ip_infos: dict[str, IPInfo] = {}
    prev_rtt: float | None = None

    try:
        for hop in stream_traceroute(
            args.target,
            max_hops=args.max_hops,
            icmp=args.icmp,
            wait=args.wait,
            queries=args.queries,
        ):
            hops.append(hop)

            info: IPInfo | None = None
            if hop.ip:
                info = lookup_ip(hop.ip, token=args.token)
                ip_infos[hop.ip] = info

            line = _format_hop_line(hop, info, prev_rtt)
            print(line)

            if hop.avg_rtt is not None:
                prev_rtt = hop.avg_rtt
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not hops:
        print("Error: traceroute returned no hop data", file=sys.stderr)
        sys.exit(1)

    # Trim trailing timeouts
    while hops and hops[-1].is_timeout:
        hops.pop()

    print(f"\nDone: {len(hops)} hops")

    results = analyze(hops, ip_infos, target_ip=target_ip)
    _serve_or_print(results, args.target, args)


def _format_hop_line(hop: Hop, info: IPInfo | None, prev_rtt: float | None) -> str:
    """Format a single hop line for streaming output."""
    num = f"{hop.hop_number:2d}"

    if hop.is_timeout:
        return f" {num}  * * *"

    parts = [f" {num}"]

    # IP
    ip_str = hop.ip or "*"
    parts.append(f"  {ip_str:<15s}")

    # RTT
    avg = hop.avg_rtt
    if avg is not None:
        parts.append(f" {avg:>7.1f} ms")
    else:
        parts.append("           ")

    # Info section
    info_parts: list[str] = []
    if info:
        if info.asn:
            info_parts.append(f"[{info.asn}]")
        if info.org:
            info_parts.append(info.org)
        if info.backbone:
            info_parts.append(f" {info.backbone}")
        location = ", ".join(filter(None, [info.city, info.country]))
        if location:
            info_parts.append(f" {location}")

    if info_parts:
        parts.append("  " + " ".join(info_parts))

    # Latency jump
    if avg is not None and prev_rtt is not None:
        jump = avg - prev_rtt
        if abs(jump) >= 1.0:
            marker = ""
            if jump > LATENCY_JUMP_THRESHOLD:
                marker = " \U0001f30a"  # 🌊
            parts.append(f"  (+{jump:.1f}{marker})" if jump > 0 else f"  ({jump:.1f})")

    return "".join(parts)


def _serve_or_print(results, target, args):
    """Output JSON or start Flask server."""
    if args.json_output:
        import dataclasses

        data = {"target": target, "hops": [dataclasses.asdict(h) for h in results]}
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    from .server import create_app

    app = create_app(results, target)
    url = f"http://127.0.0.1:{args.port}"
    print(f"Map ready at {url}")
    print("   Press Ctrl+C to stop")

    threading.Timer(1.5, webbrowser.open, args=[url]).start()
    app.run(host="127.0.0.1", port=args.port, debug=False)


def _demo_data(target: str):
    """Generate mock traceroute data for frontend demo."""
    from .analyzer import AnalyzedHop

    hops = [
        AnalyzedHop(
            hop_number=1,
            ip="192.168.1.1",
            avg_rtt=1.2,
            is_timeout=False,
            city="",
            region="",
            country="",
            lat=None,
            lon=None,
            org="Private",
            asn="",
            backbone="",
            segment="local",
            color="#9e9e9e",
            latency_jump=None,
            is_cross_ocean=False,
            hostname="",
            is_anycast=False,
        ),
        AnalyzedHop(
            hop_number=2,
            ip="10.0.0.1",
            avg_rtt=3.5,
            is_timeout=False,
            city="",
            region="",
            country="",
            lat=None,
            lon=None,
            org="Private",
            asn="",
            backbone="",
            segment="local",
            color="#9e9e9e",
            latency_jump=2.3,
            is_cross_ocean=False,
            hostname="",
            is_anycast=False,
        ),
        AnalyzedHop(
            hop_number=3,
            ip=None,
            avg_rtt=None,
            is_timeout=True,
            city="",
            region="",
            country="",
            lat=None,
            lon=None,
            org="",
            asn="",
            backbone="",
            segment="local",
            color="#9e9e9e",
            latency_jump=None,
            is_cross_ocean=False,
            hostname="",
            is_anycast=False,
        ),
        AnalyzedHop(
            hop_number=4,
            ip="202.97.12.34",
            avg_rtt=8.1,
            is_timeout=False,
            city="Shanghai",
            region="Shanghai",
            country="CN",
            lat=31.23,
            lon=121.47,
            org="ChinaNet",
            asn="AS4134",
            backbone="CT 163",
            segment="backbone",
            color="#ff9800",
            latency_jump=4.6,
            is_cross_ocean=False,
            hostname="",
            is_anycast=False,
        ),
        AnalyzedHop(
            hop_number=5,
            ip="202.97.94.150",
            avg_rtt=12.3,
            is_timeout=False,
            city="Beijing",
            region="Beijing",
            country="CN",
            lat=39.90,
            lon=116.40,
            org="ChinaNet",
            asn="AS4134",
            backbone="CT 163",
            segment="backbone",
            color="#ff9800",
            latency_jump=4.2,
            is_cross_ocean=False,
            hostname="",
            is_anycast=False,
        ),
        AnalyzedHop(
            hop_number=6,
            ip="59.43.246.97",
            avg_rtt=15.8,
            is_timeout=False,
            city="Guangzhou",
            region="Guangdong",
            country="CN",
            lat=23.13,
            lon=113.26,
            org="ChinaNet",
            asn="AS4809",
            backbone="CN2",
            segment="backbone",
            color="#ff9800",
            latency_jump=3.5,
            is_cross_ocean=False,
            hostname="",
            is_anycast=False,
        ),
        AnalyzedHop(
            hop_number=7,
            ip="59.43.187.1",
            avg_rtt=38.2,
            is_timeout=False,
            city="Hong Kong",
            region="Hong Kong",
            country="HK",
            lat=22.28,
            lon=114.16,
            org="ChinaNet",
            asn="AS4809",
            backbone="CN2",
            segment="backbone",
            color="#ff9800",
            latency_jump=22.4,
            is_cross_ocean=False,
            hostname="",
            is_anycast=False,
        ),
        AnalyzedHop(
            hop_number=8,
            ip="203.131.241.65",
            avg_rtt=52.6,
            is_timeout=False,
            city="Singapore",
            region="Singapore",
            country="SG",
            lat=1.35,
            lon=103.82,
            org="Equinix",
            asn="AS4637",
            backbone="",
            segment="transit",
            color="#2196f3",
            latency_jump=14.4,
            is_cross_ocean=False,
            hostname="",
            is_anycast=False,
        ),
        AnalyzedHop(
            hop_number=9,
            ip="72.14.196.201",
            avg_rtt=178.5,
            is_timeout=False,
            city="Los Angeles",
            region="California",
            country="US",
            lat=34.05,
            lon=-118.24,
            org="Google LLC",
            asn="AS15169",
            backbone="",
            segment="international",
            color="#f44336",
            latency_jump=125.9,
            is_cross_ocean=True,
            hostname="",
            is_anycast=True,
        ),
        AnalyzedHop(
            hop_number=10,
            ip="142.251.55.43",
            avg_rtt=180.3,
            is_timeout=False,
            city="Los Angeles",
            region="California",
            country="US",
            lat=34.05,
            lon=-118.24,
            org="Google LLC",
            asn="AS15169",
            backbone="",
            segment="transit",
            color="#2196f3",
            latency_jump=1.8,
            is_cross_ocean=False,
            hostname="",
            is_anycast=True,
        ),
        AnalyzedHop(
            hop_number=11,
            ip="142.250.196.110",
            avg_rtt=179.8,
            is_timeout=False,
            city="Mountain View",
            region="California",
            country="US",
            lat=37.39,
            lon=-122.08,
            org="Google LLC",
            asn="AS15169",
            backbone="",
            segment="target",
            color="#4caf50",
            latency_jump=-0.5,
            is_cross_ocean=False,
            hostname="lax17s55-in-f14.1e100.net",
            is_anycast=True,
        ),
    ]
    return hops, target or "google.com"
