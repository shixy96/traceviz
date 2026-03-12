"""IP lookup via ipinfo.io API + backbone hardcoded rules."""

import ipaddress
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import requests

_rate_limit_warned = False

# Backbone IP range rules: (CIDR, ASN, carrier, backbone type)
_BACKBONE_RULES: list[tuple[str, str, str, str]] = [
    ("202.97.0.0/16", "AS4134", "ChinaNet", "CT 163"),
    ("59.43.0.0/16", "AS4809", "ChinaNet", "CN2"),
    ("219.158.0.0/16", "AS4837", "China Unicom", "CU 169"),
    ("218.105.0.0/16", "AS9929", "China Unicom", "CUII/9929"),
    ("210.51.0.0/16", "AS9929", "China Unicom", "CUII/9929"),
    ("221.183.0.0/16", "AS9808", "China Mobile", "CM"),
    ("223.120.0.0/16", "AS58453", "China Mobile", "CMI"),
]

# 预编译为 ip_network 对象
_BACKBONE_NETWORKS = [
    (ipaddress.ip_network(cidr), asn, carrier, btype) for cidr, asn, carrier, btype in _BACKBONE_RULES
]


@dataclass
class IPInfo:
    ip: str
    city: str = ""
    region: str = ""
    country: str = ""
    lat: float | None = None
    lon: float | None = None
    org: str = ""
    asn: str = ""
    backbone: str = ""
    is_private: bool = False
    hostname: str = ""
    is_anycast: bool = False


def _match_backbone(ip: str) -> tuple[str, str, str] | None:
    """检查 IP 是否匹配骨干网规则，返回 (ASN, 运营商, 骨干类型)。"""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    for network, asn, carrier, backbone_type in _BACKBONE_NETWORKS:
        if addr in network:
            return asn, carrier, backbone_type
    return None


def _apply_ipinfo_payload(info: IPInfo, data: object) -> None:
    """Best-effort payload parsing; malformed fields should not abort a trace."""
    if not isinstance(data, dict):
        return

    info.city = data.get("city", "") if isinstance(data.get("city"), str) else ""
    info.region = data.get("region", "") if isinstance(data.get("region"), str) else ""
    info.country = data.get("country", "") if isinstance(data.get("country"), str) else ""
    info.hostname = data.get("hostname", "") if isinstance(data.get("hostname"), str) else ""
    info.is_anycast = bool(data.get("anycast", False))

    loc = data.get("loc", "")
    if isinstance(loc, str) and "," in loc:
        lat_s, lon_s = loc.split(",", 1)
        try:
            info.lat = float(lat_s)
            info.lon = float(lon_s)
        except ValueError:
            info.lat = None
            info.lon = None

    api_org = data.get("org", "")
    if not isinstance(api_org, str):
        api_org = ""

    if not info.backbone:
        # Strip ASN prefix from org: "AS1234 Name" -> asn="AS1234", org="Name"
        if api_org.startswith("AS"):
            parts = api_org.split(" ", 1)
            info.asn = parts[0]
            info.org = parts[1] if len(parts) > 1 else api_org
        else:
            info.org = api_org
    elif not info.city and isinstance(data.get("city"), str):
        info.city = data["city"]


def _query_ipinfo(ip: str, token: str | None = None) -> IPInfo:
    """查询单个 IP 的信息。"""
    # 私有 IP 不查询
    try:
        if ipaddress.ip_address(ip).is_private:
            return IPInfo(ip=ip, is_private=True, city="LAN", org="Private")
    except ValueError:
        return IPInfo(ip=ip)

    info = IPInfo(ip=ip)

    # 先检查骨干网规则
    backbone_match = _match_backbone(ip)
    if backbone_match:
        info.asn, info.org, info.backbone = backbone_match

    # 查询 ipinfo.io
    url = f"https://ipinfo.io/{ip}/json"
    params = {}
    if token:
        params["token"] = token

    try:
        resp = requests.get(url, params=params, timeout=5)
        if resp.status_code == 429:
            global _rate_limit_warned
            if not _rate_limit_warned:
                print("Warning: ipinfo.io rate limit reached, some IP info will be missing", file=sys.stderr)
                _rate_limit_warned = True
        elif resp.status_code == 200:
            _apply_ipinfo_payload(info, resp.json())
    except (requests.RequestException, ValueError):
        pass

    return info


# 内存缓存
_cache: dict[tuple[str, str | None], IPInfo] = {}


def lookup_ip(ip: str, token: str | None = None) -> IPInfo:
    """Look up a single IP with caching (for streaming mode)."""
    key = (ip, token)
    if key in _cache:
        return _cache[key]
    info = _query_ipinfo(ip, token)
    _cache[key] = info
    return info


def lookup_ips(ips: list[str], token: str | None = None) -> dict[str, IPInfo]:
    """批量查询 IP 信息，返回 {ip: IPInfo} 映射。"""
    results: dict[str, IPInfo] = {}
    to_query: list[str] = []
    seen: set[str] = set()

    for ip in ips:
        key = (ip, token)
        if key in _cache:
            results[ip] = _cache[key]
        elif ip not in seen:
            to_query.append(ip)
            seen.add(ip)

    if not to_query:
        return results

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_query_ipinfo, ip, token): ip for ip in to_query}
        for future in as_completed(futures):
            ip = futures[future]
            try:
                info = future.result()
            except Exception:
                info = IPInfo(ip=ip)
            _cache[(ip, token)] = info
            results[ip] = info

    return results
