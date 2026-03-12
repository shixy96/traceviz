"""ip_lookup.py 的单元测试。"""

from unittest.mock import Mock, patch

from traceviz.ip_lookup import _cache, _match_backbone, lookup_ip


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
