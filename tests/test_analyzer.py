"""analyzer.py 的单元测试。"""

from traceviz.analyzer import analyze
from traceviz.ip_lookup import IPInfo
from traceviz.tracer import Hop


def _make_hop(num, ip=None, rtts=None, timeout=False):
    return Hop(hop_number=num, ip=ip, rtts=rtts or [], is_timeout=timeout)


def _make_info(ip, **kwargs):
    return IPInfo(ip=ip, **kwargs)


class TestAnalyze:
    def test_last_hop_is_target_when_reached(self):
        hops = [_make_hop(1, "1.1.1.1", [5.0]), _make_hop(2, "2.2.2.2", [10.0])]
        infos = {
            "1.1.1.1": _make_info("1.1.1.1"),
            "2.2.2.2": _make_info("2.2.2.2"),
        }
        results = analyze(hops, infos, target_ip="2.2.2.2")
        assert results[-1].segment == "target"

    def test_last_hop_not_target_when_not_reached(self):
        """部分 trace 未到达目标时，最后一跳不应标记为 target。"""
        hops = [_make_hop(1, "1.1.1.1", [5.0]), _make_hop(2, "2.2.2.2", [10.0])]
        infos = {
            "1.1.1.1": _make_info("1.1.1.1"),
            "2.2.2.2": _make_info("2.2.2.2"),
        }
        results = analyze(hops, infos, target_ip="9.9.9.9")
        assert results[-1].segment == "transit"

    def test_last_hop_not_overridden_by_cross_ocean(self):
        """即使最后一跳有巨大延迟跳变，也不应被标记为 international（如果是目标）。"""
        hops = [
            _make_hop(1, "1.1.1.1", [5.0]),
            _make_hop(2, "2.2.2.2", [200.0]),  # 跳变 195ms
        ]
        infos = {
            "1.1.1.1": _make_info("1.1.1.1"),
            "2.2.2.2": _make_info("2.2.2.2"),
        }
        results = analyze(hops, infos, target_ip="2.2.2.2")
        assert results[-1].segment == "target"
        assert not results[-1].is_cross_ocean

    def test_cross_ocean_detection(self):
        hops = [
            _make_hop(1, "1.1.1.1", [5.0]),
            _make_hop(2, "2.2.2.2", [10.0]),
            _make_hop(3, "3.3.3.3", [180.0]),  # 跳变 170ms
            _make_hop(4, "4.4.4.4", [182.0]),
        ]
        infos = {ip: _make_info(ip) for ip in ["1.1.1.1", "2.2.2.2", "3.3.3.3", "4.4.4.4"]}
        results = analyze(hops, infos, target_ip="4.4.4.4")
        assert results[2].is_cross_ocean
        assert results[2].segment == "international"

    def test_private_ip_is_local(self):
        hops = [_make_hop(1, "192.168.1.1", [1.0]), _make_hop(2, "8.8.8.8", [10.0])]
        infos = {
            "192.168.1.1": _make_info("192.168.1.1", is_private=True),
            "8.8.8.8": _make_info("8.8.8.8"),
        }
        results = analyze(hops, infos, target_ip="8.8.8.8")
        assert results[0].segment == "local"

    def test_backbone_segment(self):
        hops = [_make_hop(1, "202.97.1.1", [8.0]), _make_hop(2, "8.8.8.8", [10.0])]
        infos = {
            "202.97.1.1": _make_info("202.97.1.1", backbone="CT 163"),
            "8.8.8.8": _make_info("8.8.8.8"),
        }
        results = analyze(hops, infos, target_ip="8.8.8.8")
        assert results[0].segment == "backbone"

    def test_timeout_hop(self):
        hops = [_make_hop(1, "1.1.1.1", [5.0]), _make_hop(2, timeout=True), _make_hop(3, "3.3.3.3", [10.0])]
        infos = {"1.1.1.1": _make_info("1.1.1.1"), "3.3.3.3": _make_info("3.3.3.3")}
        results = analyze(hops, infos, target_ip="3.3.3.3")
        assert results[1].is_timeout
        assert results[1].segment == "local"

    def test_no_target_ip_never_marks_target(self):
        """不传 target_ip 时，不会标记任何跳为 target。"""
        hops = [_make_hop(1, "1.1.1.1", [5.0]), _make_hop(2, "2.2.2.2", [10.0])]
        infos = {
            "1.1.1.1": _make_info("1.1.1.1"),
            "2.2.2.2": _make_info("2.2.2.2"),
        }
        results = analyze(hops, infos)
        assert all(r.segment != "target" for r in results)
