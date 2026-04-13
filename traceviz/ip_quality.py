"""Lightweight IP quality lookup inspired by IPQuality's ipapi checks."""

import ipaddress
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

import requests

_SCORE_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")
_LEVEL_RE = re.compile(r"\(([^)]+)\)")


@dataclass
class IPQuality:
    risk_level: str = ""
    risk_score: float | None = None
    usage_type: str = ""
    company_type: str = ""
    factors: dict[str, bool] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)


def _bool_field(payload: dict[str, Any], key: str) -> bool | None:
    value = payload.get(key)
    if isinstance(value, bool):
        return value
    return None


def _normalize_level(level: str) -> str:
    return level.strip().lower().replace(" ", "_").replace("-", "_")


def _risk_level_from_score(score: float | None) -> str:
    if score is None:
        return ""
    if score < 20:
        return "low"
    if score < 60:
        return "medium"
    if score < 90:
        return "high"
    return "very_high"


def _parse_abuser_score(value: object) -> tuple[float | None, str]:
    if isinstance(value, int | float):
        score = float(value)
        if score <= 1:
            score *= 100
        return round(score, 2), _risk_level_from_score(score)

    if not isinstance(value, str):
        return None, ""

    score: float | None = None
    score_match = _SCORE_RE.search(value)
    if score_match:
        score = float(score_match.group(0))
        if score <= 1:
            score *= 100
        score = round(score, 2)

    level_match = _LEVEL_RE.search(value)
    level = _normalize_level(level_match.group(1)) if level_match else _risk_level_from_score(score)
    return score, level


def parse_ipapi_quality(payload: object) -> IPQuality:
    """Parse the subset of api.ipapi.is fields used by IPQuality's checks."""
    if not isinstance(payload, dict):
        return IPQuality()

    company = payload.get("company")
    company = company if isinstance(company, dict) else {}
    asn = payload.get("asn")
    asn = asn if isinstance(asn, dict) else {}

    score, level = _parse_abuser_score(company.get("abuser_score"))
    factors = {
        name: value
        for name, value in {
            "proxy": _bool_field(payload, "is_proxy"),
            "vpn": _bool_field(payload, "is_vpn"),
            "tor": _bool_field(payload, "is_tor"),
            "hosting": _bool_field(payload, "is_datacenter"),
            "abuser": _bool_field(payload, "is_abuser"),
            "crawler": _bool_field(payload, "is_crawler"),
        }.items()
        if value is not None
    }

    usage_type = asn.get("type", "")
    company_type = company.get("type", "")

    return IPQuality(
        risk_level=level,
        risk_score=score,
        usage_type=usage_type if isinstance(usage_type, str) else "",
        company_type=company_type if isinstance(company_type, str) else "",
        factors=factors,
        sources=["ipapi.is"],
    )


def lookup_ip_quality(ip: str, timeout: int = 5) -> IPQuality:
    """Look up lightweight quality signals for a public IP address."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return IPQuality()

    if addr.is_private:
        return IPQuality()

    try:
        resp = requests.get("https://api.ipapi.is/", params={"q": ip}, timeout=timeout)
        if resp.status_code != 200:
            return IPQuality()
        return parse_ipapi_quality(resp.json())
    except (requests.RequestException, ValueError):
        return IPQuality()


_cache: dict[str, IPQuality] = {}


def lookup_ip_qualities(ips: list[str], timeout: int = 5) -> dict[str, IPQuality]:
    """Batch lookup IP quality with simple in-memory caching."""
    results: dict[str, IPQuality] = {}
    to_query: list[str] = []
    seen: set[str] = set()

    for ip in ips:
        if ip in _cache:
            results[ip] = _cache[ip]
        elif ip not in seen:
            to_query.append(ip)
            seen.add(ip)

    if not to_query:
        return results

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(lookup_ip_quality, ip, timeout): ip for ip in to_query}
        for future in as_completed(futures):
            ip = futures[future]
            try:
                quality = future.result()
            except Exception:
                quality = IPQuality()
            _cache[ip] = quality
            results[ip] = quality

    return results
