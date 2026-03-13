"""ip_lookup.py 的单元测试。"""

from unittest.mock import Mock, patch

import pytest
import requests

from traceviz.ip_lookup import (
    IPInfo,
    _apply_ipinfo_payload,
    _cache,
    _match_backbone,
    _query_ipinfo,
    lookup_ip,
    lookup_ips,
)


class TestMatchBackbone:
    def test_ct_163(self):
        result = _match_backbone("202.97.12.34")
        assert result is not None
        asn, carrier, btype = result
        assert asn == "AS4134"
        assert carrier == "ChinaNet"
        assert btype == "CT 163"

    def test_ct_cn2(self):
        result = _match_backbone("59.43.246.97")
        assert result is not None
        assert result[0] == "AS4809"
        assert result[2] == "CN2"

    def test_cu_cunet(self):
        result = _match_backbone("218.105.1.1")
        assert result is not None
        assert result[2] == "CUII/9929"

    def test_cu_cunet_210(self):
        result = _match_backbone("210.51.10.1")
        assert result is not None
        assert result[0] == "AS9929"

    def test_cm_cmi(self):
        result = _match_backbone("223.120.1.1")
        assert result is not None
        assert result[2] == "CMI"

    def test_no_match(self):
        assert _match_backbone("8.8.8.8") is None

    def test_private_ip(self):
        assert _match_backbone("192.168.1.1") is None

    def test_invalid_ip(self):
        assert _match_backbone("not-an-ip") is None


class TestLookupIP:
    def setup_method(self):
        _cache.clear()

    def test_invalid_loc_does_not_raise(self):
        resp = Mock(status_code=200)
        resp.json.return_value = {"loc": "x,y", "org": "AS15169 Google LLC"}

        with patch("traceviz.ip_lookup.requests.get", return_value=resp):
            info = lookup_ip("8.8.8.8")

        assert info.ip == "8.8.8.8"
        assert info.lat is None
        assert info.lon is None
        assert info.asn == "AS15169"
        assert info.org == "Google LLC"

    def test_invalid_json_does_not_raise(self):
        resp = Mock(status_code=200)
        resp.json.side_effect = ValueError("bad json")

        with patch("traceviz.ip_lookup.requests.get", return_value=resp):
            info = lookup_ip("1.1.1.1")

        assert info.ip == "1.1.1.1"
        assert info.city == ""

    def test_cache_hit_skips_second_query(self):
        cached = IPInfo(ip="8.8.8.8", org="Google LLC")

        with patch("traceviz.ip_lookup._query_ipinfo", return_value=cached) as query_ipinfo:
            first = lookup_ip("8.8.8.8", token="secret")
            second = lookup_ip("8.8.8.8", token="secret")

        assert first is cached
        assert second is cached
        query_ipinfo.assert_called_once_with("8.8.8.8", "secret")


class TestApplyIpinfoPayload:
    def test_ignores_non_dict_payloads(self):
        info = IPInfo(ip="8.8.8.8", org="Original")

        _apply_ipinfo_payload(info, ["not", "a", "dict"])

        assert info.org == "Original"

    def test_parses_fields_coordinates_and_asn_prefixed_org(self):
        info = IPInfo(ip="8.8.8.8")

        _apply_ipinfo_payload(
            info,
            {
                "city": "Mountain View",
                "region": "California",
                "country": "US",
                "hostname": "dns.google",
                "anycast": True,
                "loc": "37.4056,-122.0775",
                "org": "AS15169 Google LLC",
            },
        )

        assert info.city == "Mountain View"
        assert info.region == "California"
        assert info.country == "US"
        assert info.hostname == "dns.google"
        assert info.is_anycast is True
        assert info.lat == pytest.approx(37.4056)
        assert info.lon == pytest.approx(-122.0775)
        assert info.asn == "AS15169"
        assert info.org == "Google LLC"

    def test_preserves_backbone_identity_and_fills_missing_city(self):
        info = IPInfo(ip="202.97.1.1", org="ChinaNet", asn="AS4134", backbone="CT 163")

        _apply_ipinfo_payload(info, {"city": "Beijing", "org": "AS9999 Different Carrier"})

        assert info.city == "Beijing"
        assert info.org == "ChinaNet"
        assert info.asn == "AS4134"

    def test_handles_invalid_loc_and_non_string_org(self):
        info = IPInfo(ip="1.1.1.1")

        _apply_ipinfo_payload(info, {"loc": "x,y", "org": 42})

        assert info.lat is None
        assert info.lon is None
        assert info.org == ""


class TestQueryIpinfo:
    def setup_method(self):
        _cache.clear()
        import traceviz.ip_lookup as ip_lookup

        ip_lookup._rate_limit_warned = False

    def test_private_ip_returns_local_stub_without_network_call(self):
        with patch("traceviz.ip_lookup.requests.get") as requests_get:
            info = _query_ipinfo("192.168.1.1")

        assert info.is_private is True
        assert info.city == "LAN"
        assert info.org == "Private"
        requests_get.assert_not_called()

    def test_invalid_ip_returns_empty_info(self):
        with patch("traceviz.ip_lookup.requests.get") as requests_get:
            info = _query_ipinfo("not-an-ip")

        assert info == IPInfo(ip="not-an-ip")
        requests_get.assert_not_called()

    def test_uses_token_and_applies_api_payload(self):
        resp = Mock(status_code=200)
        resp.json.return_value = {
            "city": "Sydney",
            "country": "AU",
            "loc": "-33.8688,151.2093",
            "org": "AS13335 Cloudflare",
        }

        with patch("traceviz.ip_lookup.requests.get", return_value=resp) as requests_get:
            info = _query_ipinfo("1.1.1.1", token="secret")

        requests_get.assert_called_once_with(
            "https://ipinfo.io/1.1.1.1/json",
            params={"token": "secret"},
            timeout=5,
        )
        assert info.city == "Sydney"
        assert info.country == "AU"
        assert info.asn == "AS13335"
        assert info.org == "Cloudflare"

    def test_backbone_match_populates_backbone_and_keeps_it_after_api_parse(self):
        resp = Mock(status_code=200)
        resp.json.return_value = {"city": "Shanghai", "org": "AS9999 Override"}

        with patch("traceviz.ip_lookup.requests.get", return_value=resp):
            info = _query_ipinfo("202.97.12.34")

        assert info.asn == "AS4134"
        assert info.org == "ChinaNet"
        assert info.backbone == "CT 163"
        assert info.city == "Shanghai"

    def test_rate_limit_warning_only_prints_once(self, capsys):
        resp = Mock(status_code=429)

        with patch("traceviz.ip_lookup.requests.get", return_value=resp):
            _query_ipinfo("8.8.8.8")
            _query_ipinfo("1.1.1.1")

        captured = capsys.readouterr()
        assert captured.err.count("rate limit reached") == 1

    def test_request_exception_is_swallowed(self):
        with patch("traceviz.ip_lookup.requests.get", side_effect=requests.RequestException("down")):
            info = _query_ipinfo("8.8.8.8")

        assert info == IPInfo(ip="8.8.8.8")


class TestLookupIps:
    def setup_method(self):
        _cache.clear()

    def test_returns_cached_results_without_spawning_pool(self):
        cached = IPInfo(ip="8.8.8.8", org="Google LLC")
        _cache[("8.8.8.8", None)] = cached

        with patch("traceviz.ip_lookup.ThreadPoolExecutor") as executor:
            results = lookup_ips(["8.8.8.8"])

        assert results == {"8.8.8.8": cached}
        executor.assert_not_called()

    def test_deduplicates_queries_and_falls_back_on_future_errors(self):
        class FakeFuture:
            def __init__(self, result=None, error=None):
                self._result = result
                self._error = error

            def result(self):
                if self._error is not None:
                    raise self._error
                return self._result

        class FakeExecutor:
            def __init__(self, future_map):
                self.future_map = future_map
                self.submissions = []

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def submit(self, fn, ip, token):
                self.submissions.append((fn, ip, token))
                return self.future_map[ip]

        cached = IPInfo(ip="8.8.8.8", org="Google LLC")
        queried = IPInfo(ip="1.1.1.1", org="Cloudflare")
        failed_ip = "9.9.9.9"
        _cache[("8.8.8.8", "secret")] = cached
        future_ok = FakeFuture(result=queried)
        future_fail = FakeFuture(error=RuntimeError("boom"))
        executor = FakeExecutor({"1.1.1.1": future_ok, failed_ip: future_fail})

        with (
            patch("traceviz.ip_lookup.ThreadPoolExecutor", return_value=executor),
            patch("traceviz.ip_lookup.as_completed", return_value=[future_ok, future_fail]),
        ):
            results = lookup_ips(["8.8.8.8", "1.1.1.1", "1.1.1.1", failed_ip], token="secret")

        assert [submission[1:] for submission in executor.submissions] == [
            ("1.1.1.1", "secret"),
            (failed_ip, "secret"),
        ]
        assert results["8.8.8.8"] is cached
        assert results["1.1.1.1"] is queried
        assert results[failed_ip] == IPInfo(ip=failed_ip)
        assert _cache[("1.1.1.1", "secret")] is queried
        assert _cache[(failed_ip, "secret")] == IPInfo(ip=failed_ip)
