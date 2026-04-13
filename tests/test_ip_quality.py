"""ip_quality.py unit tests."""

from unittest.mock import Mock, patch

import requests

from traceviz.ip_quality import IPQuality, _cache, lookup_ip_qualities, lookup_ip_quality, parse_ipapi_quality


def setup_function(_function):
    _cache.clear()


def test_parse_ipapi_quality_extracts_risk_type_and_factors():
    quality = parse_ipapi_quality(
        {
            "asn": {"type": "isp"},
            "company": {"type": "hosting", "abuser_score": "0.73 (High)"},
            "is_proxy": True,
            "is_vpn": False,
            "is_tor": False,
            "is_datacenter": True,
            "is_abuser": False,
            "is_crawler": True,
        }
    )

    assert quality.risk_score == 73.0
    assert quality.risk_level == "high"
    assert quality.usage_type == "isp"
    assert quality.company_type == "hosting"
    assert quality.factors == {
        "proxy": True,
        "vpn": False,
        "tor": False,
        "hosting": True,
        "abuser": False,
        "crawler": True,
    }
    assert quality.sources == ["ipapi.is"]


def test_parse_ipapi_quality_ignores_malformed_payload():
    assert parse_ipapi_quality(["bad"]) == IPQuality()


def test_lookup_ip_quality_skips_private_and_invalid_ips():
    with patch("traceviz.ip_quality.requests.get") as requests_get:
        private_quality = lookup_ip_quality("192.168.1.1")
        invalid_quality = lookup_ip_quality("not-an-ip")

    assert private_quality == IPQuality()
    assert invalid_quality == IPQuality()
    requests_get.assert_not_called()


def test_lookup_ip_quality_uses_ipapi_endpoint():
    resp = Mock(status_code=200)
    resp.json.return_value = {"company": {"abuser_score": 42}, "is_proxy": True}

    with patch("traceviz.ip_quality.requests.get", return_value=resp) as requests_get:
        quality = lookup_ip_quality("8.8.8.8")

    requests_get.assert_called_once_with("https://api.ipapi.is/", params={"q": "8.8.8.8"}, timeout=5)
    assert quality.risk_score == 42.0
    assert quality.risk_level == "medium"
    assert quality.factors == {"proxy": True}


def test_lookup_ip_quality_swallow_request_errors():
    with patch("traceviz.ip_quality.requests.get", side_effect=requests.RequestException("down")):
        quality = lookup_ip_quality("8.8.8.8")

    assert quality == IPQuality()


def test_lookup_ip_qualities_deduplicates_and_caches_queries():
    quality = IPQuality(risk_level="low")

    with patch("traceviz.ip_quality.lookup_ip_quality", return_value=quality) as lookup:
        first = lookup_ip_qualities(["8.8.8.8", "8.8.8.8"])
        second = lookup_ip_qualities(["8.8.8.8"])

    assert first == {"8.8.8.8": quality}
    assert second == {"8.8.8.8": quality}
    lookup.assert_called_once_with("8.8.8.8", 5)
