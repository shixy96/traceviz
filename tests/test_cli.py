"""cli.py unit tests."""

import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from traceviz.analyzer import AnalyzedHop
from traceviz.cli import (
    _demo_data,
    _format_hop_line,
    _run_batch,
    _run_streaming,
    _serve_or_print,
    main,
)
from traceviz.ip_lookup import IPInfo
from traceviz.tracer import Hop


def _make_args(**overrides):
    args = {
        "target": "example.com",
        "max_hops": 5,
        "port": 8890,
        "token": None,
        "icmp": False,
        "wait": 2,
        "queries": 2,
        "json_output": False,
        "demo": False,
    }
    args.update(overrides)
    return SimpleNamespace(**args)


def _make_analyzed_hop(**overrides):
    data = {
        "hop_number": 1,
        "ip": "8.8.8.8",
        "avg_rtt": 12.3,
        "is_timeout": False,
        "city": "Mountain View",
        "region": "California",
        "country": "US",
        "lat": 37.4056,
        "lon": -122.0775,
        "org": "Google LLC",
        "asn": "AS15169",
        "backbone": "",
        "segment": "target",
        "color": "#4caf50",
        "latency_jump": None,
        "is_cross_ocean": False,
        "hostname": "dns.google",
        "is_anycast": True,
    }
    data.update(overrides)
    return AnalyzedHop(**data)


def _parse_streaming_args(argv):
    with (
        patch.object(sys, "argv", argv),
        patch("traceviz.cli._run_streaming") as run_streaming,
    ):
        main()

    run_streaming.assert_called_once()
    return run_streaming.call_args.args[0]


def _parse_batch_args(argv):
    with (
        patch.object(sys, "argv", argv),
        patch("traceviz.cli._run_batch") as run_batch,
    ):
        main()

    run_batch.assert_called_once()
    return run_batch.call_args.args[0]


def test_main_parses_target_argument():
    args = _parse_streaming_args(["traceviz", "example.com"])

    assert args.target == "example.com"


def test_main_parses_max_hops_argument():
    args = _parse_streaming_args(["traceviz", "example.com", "--max-hops", "12"])

    assert args.max_hops == 12


def test_main_parses_port_argument():
    args = _parse_streaming_args(["traceviz", "example.com", "--port", "9900"])

    assert args.port == 9900


def test_main_parses_token_argument():
    args = _parse_streaming_args(["traceviz", "example.com", "--token", "secret-token"])

    assert args.token == "secret-token"


def test_main_parses_icmp_argument():
    args = _parse_streaming_args(["traceviz", "example.com", "--icmp"])

    assert args.icmp is True


def test_main_parses_wait_argument():
    args = _parse_streaming_args(["traceviz", "example.com", "--wait", "4"])

    assert args.wait == 4


def test_main_parses_queries_argument():
    args = _parse_streaming_args(["traceviz", "example.com", "--queries", "5"])

    assert args.queries == 5


def test_main_parses_short_q_alias():
    args = _parse_batch_args(["traceviz", "example.com", "--json", "-q", "7"])

    assert args.queries == 7


def test_main_routes_json_output_to_batch_runner():
    args = _parse_batch_args(["traceviz", "example.com", "--json"])

    assert args.json_output is True


def test_main_parses_demo_argument():
    demo_results = [_make_analyzed_hop(ip="1.1.1.1")]

    with (
        patch.object(sys, "argv", ["traceviz", "demo.example", "--demo"]),
        patch("traceviz.cli._demo_data", return_value=(demo_results, "demo.example")) as demo_data,
        patch("traceviz.cli._serve_or_print") as serve_or_print,
    ):
        main()

    demo_data.assert_called_once_with("demo.example")
    serve_or_print.assert_called_once()
    args = serve_or_print.call_args.args[2]
    assert args.demo is True


def test_main_routes_demo_mode_to_demo_data_and_output():
    demo_results = [_make_analyzed_hop(ip="1.1.1.1")]

    with (
        patch.object(sys, "argv", ["traceviz", "demo.example", "--demo", "--port", "9911", "--token", "demo-token"]),
        patch("traceviz.cli._demo_data", return_value=(demo_results, "demo.example")) as demo_data,
        patch("traceviz.cli._serve_or_print") as serve_or_print,
    ):
        main()

    demo_data.assert_called_once_with("demo.example")
    serve_or_print.assert_called_once()
    served_results, served_target, served_args = serve_or_print.call_args.args
    assert served_results == demo_results
    assert served_target == "demo.example"
    assert served_args.demo is True
    assert served_args.port == 9911
    assert served_args.token == "demo-token"


def test_streaming_keyboard_interrupt_exits_with_130():
    with (
        patch.object(sys, "argv", ["traceviz", "example.com"]),
        patch("traceviz.cli._run_streaming", side_effect=KeyboardInterrupt),
        pytest.raises(SystemExit) as excinfo,
    ):
        main()

    assert excinfo.value.code == 130


def test_demo_keyboard_interrupt_exits_with_130():
    with (
        patch.object(sys, "argv", ["traceviz", "example.com", "--demo"]),
        patch("traceviz.cli._demo_data", return_value=([], "example.com")),
        patch("traceviz.cli._serve_or_print", side_effect=KeyboardInterrupt),
        pytest.raises(SystemExit) as excinfo,
    ):
        main()

    assert excinfo.value.code == 130


def test_run_batch_analyzes_hops_and_delegates_output(capsys):
    args = _make_args(json_output=True, icmp=True, token="secret")
    hops = [Hop(1, "1.1.1.1", [5.0]), Hop(2, "2.2.2.2", [10.0])]
    ip_infos = {"1.1.1.1": IPInfo(ip="1.1.1.1"), "2.2.2.2": IPInfo(ip="2.2.2.2")}
    analyzed = [_make_analyzed_hop()]

    with (
        patch("traceviz.cli.run_traceroute", return_value=hops) as run_traceroute,
        patch("traceviz.cli.lookup_ips", return_value=ip_infos) as lookup_ips,
        patch("traceviz.cli._resolve_target", return_value="2.2.2.2") as resolve_target,
        patch("traceviz.cli.analyze", return_value=analyzed) as analyze,
        patch("traceviz.cli._serve_or_print") as serve_or_print,
    ):
        _run_batch(args)

    run_traceroute.assert_called_once_with("example.com", max_hops=5, icmp=True, wait=2, queries=2)
    lookup_ips.assert_called_once_with(["1.1.1.1", "2.2.2.2"], token="secret")
    resolve_target.assert_called_once_with("example.com")
    analyze.assert_called_once_with(hops, ip_infos, target_ip="2.2.2.2")
    serve_or_print.assert_called_once_with(analyzed, "example.com", args)

    captured = capsys.readouterr()
    assert "Tracing example.com, max 5 hops, ICMP mode..." in captured.err


def test_run_batch_exits_with_error_when_traceroute_fails(capsys):
    args = _make_args()

    with (
        patch("traceviz.cli.run_traceroute", side_effect=RuntimeError("boom")),
        pytest.raises(SystemExit) as excinfo,
    ):
        _run_batch(args)

    assert excinfo.value.code == 1
    assert "Error: boom" in capsys.readouterr().err


def test_run_batch_exits_with_error_when_no_hops_returned(capsys):
    args = _make_args()

    with (
        patch("traceviz.cli.run_traceroute", return_value=[]),
        pytest.raises(SystemExit) as excinfo,
    ):
        _run_batch(args)

    assert excinfo.value.code == 1
    assert "traceroute returned no hop data" in capsys.readouterr().err


def test_run_streaming_formats_lines_trims_trailing_timeouts_and_serves(capsys):
    args = _make_args(token="secret")
    hops = [
        Hop(1, "1.1.1.1", [5.0]),
        Hop(2, None, [], is_timeout=True),
        Hop(3, "2.2.2.2", [130.0]),
        Hop(4, None, [], is_timeout=True),
    ]
    info_1 = IPInfo(ip="1.1.1.1", org="ISP One", asn="AS64501", city="Shanghai", country="CN")
    info_2 = IPInfo(ip="2.2.2.2", org="ISP Two", asn="AS64502", city="Tokyo", country="JP")
    analyzed = [_make_analyzed_hop(ip="2.2.2.2")]

    with (
        patch("traceviz.cli._resolve_target", return_value="2.2.2.2"),
        patch("traceviz.cli.stream_traceroute", return_value=iter(hops)) as stream_traceroute,
        patch("traceviz.cli.lookup_ip", side_effect=[info_1, info_2]) as lookup_ip,
        patch("traceviz.cli.analyze", return_value=analyzed) as analyze,
        patch("traceviz.cli._serve_or_print") as serve_or_print,
    ):
        _run_streaming(args)

    stream_traceroute.assert_called_once_with("example.com", max_hops=5, icmp=False, wait=2, queries=2)
    assert lookup_ip.call_args_list == [
        (("1.1.1.1",), {"token": "secret"}),
        (("2.2.2.2",), {"token": "secret"}),
    ]
    analyzed_hops, analyzed_infos = analyze.call_args.args[:2]
    assert analyzed_hops == hops[:-1]
    assert analyzed_infos == {"1.1.1.1": info_1, "2.2.2.2": info_2}
    assert analyze.call_args.kwargs == {"target_ip": "2.2.2.2"}
    serve_or_print.assert_called_once_with(analyzed, "example.com", args)

    captured = capsys.readouterr()
    assert "Tracing example.com (2.2.2.2), max 5 hops, UDP mode" in captured.out
    assert "Done: 3 hops" in captured.out
    assert "[AS64501] ISP One" in captured.out
    assert "(+125.0 \U0001f30a)" in captured.out


def test_run_streaming_exits_with_error_when_traceroute_fails(capsys):
    args = _make_args()

    with (
        patch("traceviz.cli._resolve_target", return_value="1.1.1.1"),
        patch("traceviz.cli.stream_traceroute", side_effect=RuntimeError("boom")),
        pytest.raises(SystemExit) as excinfo,
    ):
        _run_streaming(args)

    assert excinfo.value.code == 1
    assert "Error: boom" in capsys.readouterr().err


def test_run_streaming_exits_with_error_when_no_hops_returned(capsys):
    args = _make_args()

    with (
        patch("traceviz.cli._resolve_target", return_value="1.1.1.1"),
        patch("traceviz.cli.stream_traceroute", return_value=iter(())),
        pytest.raises(SystemExit) as excinfo,
    ):
        _run_streaming(args)

    assert excinfo.value.code == 1
    assert "traceroute returned no hop data" in capsys.readouterr().err


def test_format_hop_line_returns_timeout_marker():
    line = _format_hop_line(Hop(3, is_timeout=True), None, prev_rtt=None)
    assert line == "  3  * * *"


def test_format_hop_line_formats_info_and_positive_jump():
    hop = Hop(7, "203.0.113.7", [150.0])
    info = IPInfo(
        ip="203.0.113.7",
        asn="AS64512",
        org="Backbone",
        backbone="CN2",
        city="Hong Kong",
        country="HK",
    )

    line = _format_hop_line(hop, info, prev_rtt=10.0)

    assert "203.0.113.7" in line
    assert "[AS64512] Backbone  CN2  Hong Kong, HK" in line
    assert "(+140.0 \U0001f30a)" in line


def test_format_hop_line_formats_negative_jump_and_missing_rtt():
    negative_line = _format_hop_line(Hop(4, "8.8.8.8", [8.0]), None, prev_rtt=12.5)
    blank_rtt_line = _format_hop_line(Hop(5, "8.8.4.4", []), None, prev_rtt=3.0)

    assert "(4.5)" not in negative_line
    assert "(-4.5)" in negative_line
    assert "8.8.4.4" in blank_rtt_line
    assert "ms" not in blank_rtt_line


def test_serve_or_print_outputs_json_payload(capsys):
    args = _make_args(json_output=True)
    results = [_make_analyzed_hop()]

    _serve_or_print(results, "example.com", args)

    payload = json.loads(capsys.readouterr().out)
    assert payload["target"] == "example.com"
    assert payload["hops"][0]["ip"] == "8.8.8.8"


def test_serve_or_print_starts_server_and_browser_timer(capsys):
    args = _make_args(port=9900)
    results = [_make_analyzed_hop()]
    app = Mock()
    timer = Mock()

    with (
        patch("traceviz.server.create_app", return_value=app) as create_app,
        patch("traceviz.cli.threading.Timer", return_value=timer) as timer_cls,
    ):
        _serve_or_print(results, "example.com", args)

    create_app.assert_called_once_with(results, "example.com")
    timer_cls.assert_called_once_with(1.5, sys.modules["traceviz.cli"].webbrowser.open, args=["http://127.0.0.1:9900"])
    timer.start.assert_called_once_with()
    app.run.assert_called_once_with(host="127.0.0.1", port=9900, debug=False)

    captured = capsys.readouterr()
    assert "Map ready at http://127.0.0.1:9900" in captured.out
    assert "Press Ctrl+C to stop" in captured.out


def test_demo_data_returns_mock_trace_and_default_target():
    hops, target = _demo_data("")

    assert target == "google.com"
    assert len(hops) == 11
    assert hops[0].segment == "local"
    assert hops[3].backbone == "CT 163"
    assert hops[8].is_cross_ocean is True
    assert hops[-1].segment == "target"
