"""tracer.py unit tests."""

import socket
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from traceviz.tracer import (
    _build_traceroute_cmd,
    _parse_line,
    _parse_line_windows,
    _resolve_target,
    run_traceroute,
    stream_traceroute,
)


class TestParseLineUnix:
    def test_normal_hop(self):
        hop = _parse_line("  1  192.168.1.1  1.234 ms  1.456 ms")
        assert hop is not None
        assert hop.hop_number == 1
        assert hop.ip == "192.168.1.1"
        assert hop.rtts == [1.234, 1.456]
        assert not hop.is_timeout

    def test_timeout_hop(self):
        hop = _parse_line("  2  * * *")
        assert hop is not None
        assert hop.hop_number == 2
        assert hop.is_timeout

    def test_partial_timeout(self):
        hop = _parse_line("  3  10.0.0.1  5.123 ms  *  5.456 ms")
        assert hop is not None
        assert hop.ip == "10.0.0.1"
        assert hop.rtts == [5.123, 5.456]
        assert not hop.is_timeout

    def test_non_hop_line(self):
        assert _parse_line("traceroute to google.com (142.250.196.110)") is None

    def test_empty_line(self):
        assert _parse_line("") is None

    def test_garbage_hop_becomes_timeout(self):
        hop = _parse_line("  4  ???")
        assert hop is not None
        assert hop.is_timeout


class TestParseLineWindows:
    def test_normal_hop(self):
        hop = _parse_line_windows("  1     2 ms     3 ms     2 ms  10.0.0.1")
        assert hop is not None
        assert hop.hop_number == 1
        assert hop.ip == "10.0.0.1"
        assert hop.rtts == [2.0, 3.0, 2.0]

    def test_sub_millisecond(self):
        hop = _parse_line_windows("  1    <1 ms    <1 ms    <1 ms  192.168.1.1")
        assert hop is not None
        assert hop.ip == "192.168.1.1"
        assert hop.rtts == [1.0, 1.0, 1.0]

    def test_timeout_hop(self):
        hop = _parse_line_windows("  3     *        *        *")
        assert hop is not None
        assert hop.is_timeout

    def test_garbage_hop_becomes_timeout(self):
        hop = _parse_line_windows("  4  Request timed out.")
        assert hop is not None
        assert hop.is_timeout


class TestRunTraceroute:
    def test_builds_unix_command_and_stops_after_too_many_timeouts_post_target(self):
        proc = MagicMock()
        proc.stdout = "\n".join(
            [
                "  1  192.168.1.1  1.0 ms  1.5 ms",
                "  2  1.2.3.4  20.0 ms  21.0 ms",
                "  3  * * *",
                "  4  * * *",
                "  5  * * *",
                "  6  * * *",
                "  7  * * *",
            ]
        )
        proc.stderr = ""
        proc.returncode = 0

        with (
            patch("traceviz.tracer.platform.system", return_value="Darwin"),
            patch("traceviz.tracer.subprocess.run", return_value=proc) as run,
            patch("traceviz.tracer._resolve_target", return_value="1.2.3.4"),
        ):
            hops = run_traceroute("example.com", max_hops=6, icmp=True, wait=4, queries=2)

        run.assert_called_once_with(
            ["traceroute", "-n", "-q", "2", "-w", "4", "-m", "6", "-I", "example.com"],
            capture_output=True,
            text=True,
            timeout=78,
        )
        assert len(hops) == 6
        assert hops[1].ip == "1.2.3.4"
        assert all(hop.is_timeout for hop in hops[2:])

    def test_builds_windows_command_and_trims_trailing_timeouts_when_target_not_reached(self):
        proc = MagicMock()
        proc.stdout = "\n".join(
            [
                "  1     2 ms     3 ms     2 ms  10.0.0.1",
                "  2     *        *        *",
                "  3     7 ms     8 ms     7 ms  203.0.113.7",
                "  4     *        *        *",
                "  5     *        *        *",
            ]
        )
        proc.stderr = ""
        proc.returncode = 0

        with (
            patch("traceviz.tracer.platform.system", return_value="Windows"),
            patch("traceviz.tracer.subprocess.run", return_value=proc) as run,
            patch("traceviz.tracer._resolve_target", return_value="203.0.113.8"),
        ):
            hops = run_traceroute("example.com", max_hops=5, wait=2)

        run.assert_called_once_with(
            ["tracert", "-d", "-h", "5", "-w", "2000", "example.com"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert len(hops) == 3
        assert hops[1].is_timeout
        assert hops[-1].ip == "203.0.113.7"

    def test_raises_with_stderr_when_command_fails(self):
        proc = MagicMock(stdout="", stderr="permission denied", returncode=1)

        with (
            patch("traceviz.tracer.platform.system", return_value="Linux"),
            patch("traceviz.tracer.subprocess.run", return_value=proc),
            pytest.raises(RuntimeError, match="permission denied"),
        ):
            run_traceroute("example.com")

    def test_raises_generic_error_when_command_fails_without_output(self):
        proc = MagicMock(stdout="", stderr="", returncode=1)

        with (
            patch("traceviz.tracer.platform.system", return_value="Linux"),
            patch("traceviz.tracer.subprocess.run", return_value=proc),
            pytest.raises(RuntimeError, match="no output"),
        ):
            run_traceroute("example.com")

    def test_raises_when_binary_is_missing(self):
        with (
            patch("traceviz.tracer.platform.system", return_value="Linux"),
            patch("traceviz.tracer.subprocess.run", side_effect=FileNotFoundError),
            pytest.raises(RuntimeError, match="not installed"),
        ):
            run_traceroute("example.com")

    def test_raises_when_traceroute_times_out(self):
        with (
            patch("traceviz.tracer.platform.system", return_value="Linux"),
            patch(
                "traceviz.tracer.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="traceroute", timeout=30),
            ),
            pytest.raises(RuntimeError, match="timed out"),
        ):
            run_traceroute("example.com")


class TestResolveTarget:
    def teardown_method(self):
        if hasattr(_resolve_target, "_cache"):
            delattr(_resolve_target, "_cache")

    def test_caches_dns_lookups(self):
        with patch("socket.gethostbyname", return_value="1.2.3.4") as gethostbyname:
            first = _resolve_target("example.com")
            second = _resolve_target("example.com")

        assert first == "1.2.3.4"
        assert second == "1.2.3.4"
        gethostbyname.assert_called_once_with("example.com")

    def test_falls_back_to_original_target_on_dns_failure(self):
        with patch("socket.gethostbyname", side_effect=socket.gaierror):
            resolved = _resolve_target("unresolvable.example")

        assert resolved == "unresolvable.example"


class TestBuildTracerouteCmd:
    def test_builds_unix_icmp_command(self):
        with patch("traceviz.tracer.platform.system", return_value="Linux"):
            cmd, system = _build_traceroute_cmd("example.com", max_hops=8, icmp=True, wait=5, queries=4)

        assert system == "linux"
        assert cmd == ["traceroute", "-n", "-q", "4", "-w", "5", "-m", "8", "-I", "example.com"]

    def test_builds_windows_command(self):
        with patch("traceviz.tracer.platform.system", return_value="Windows"):
            cmd, system = _build_traceroute_cmd("example.com", max_hops=8, wait=5)

        assert system == "windows"
        assert cmd == ["tracert", "-d", "-h", "8", "-w", "5000", "example.com"]


class TestStreamTraceroute:
    def test_yields_hops_and_stops_at_target(self):
        fake_output = [
            "traceroute to 1.2.3.4 (1.2.3.4), 30 hops max\n",
            "  1  192.168.1.1  1.234 ms  1.456 ms\n",
            "  2  * * *\n",
            "  3  10.0.0.1  5.123 ms  5.456 ms\n",
            "  4  1.2.3.4  20.100 ms  19.800 ms\n",
            "  5  5.5.5.5  25.000 ms  25.100 ms\n",
        ]

        mock_proc = MagicMock()
        mock_proc.stdout = iter(fake_output)
        mock_proc.poll.return_value = None
        mock_proc.wait.return_value = 0

        with (
            patch("traceviz.tracer.subprocess.Popen", return_value=mock_proc),
            patch("traceviz.tracer._resolve_target", return_value="1.2.3.4"),
        ):
            hops = list(stream_traceroute("1.2.3.4"))

        assert len(hops) == 4
        assert hops[0].hop_number == 1
        assert hops[0].ip == "192.168.1.1"
        assert hops[1].is_timeout
        assert hops[2].ip == "10.0.0.1"
        assert hops[3].ip == "1.2.3.4"
        # Should have terminated the process
        mock_proc.terminate.assert_called_once()

    def test_all_hops_yielded_when_target_not_reached(self):
        fake_output = [
            "  1  192.168.1.1  1.0 ms\n",
            "  2  * * *\n",
            "  3  10.0.0.1  5.0 ms\n",
        ]

        mock_proc = MagicMock()
        mock_proc.stdout = iter(fake_output)
        mock_proc.poll.return_value = 0  # already exited
        mock_proc.returncode = 0

        with (
            patch("traceviz.tracer.subprocess.Popen", return_value=mock_proc),
            patch("traceviz.tracer._resolve_target", return_value="99.99.99.99"),
        ):
            hops = list(stream_traceroute("example.com"))

        assert len(hops) == 3

    def test_raises_on_missing_traceroute(self):
        with (
            patch("traceviz.tracer.subprocess.Popen", side_effect=FileNotFoundError),
            patch("traceviz.tracer._resolve_target", return_value="1.2.3.4"),
        ):
            try:
                list(stream_traceroute("1.2.3.4"))
                raise AssertionError("Should have raised RuntimeError")
            except RuntimeError as e:
                assert "not installed" in str(e)

    def test_kills_process_when_terminate_wait_times_out(self):
        mock_proc = MagicMock()
        mock_proc.stdout = iter(["  1  192.168.1.1  1.0 ms\n"])
        mock_proc.poll.return_value = None
        mock_proc.wait.side_effect = subprocess.TimeoutExpired(cmd="traceroute", timeout=3)

        with (
            patch("traceviz.tracer.subprocess.Popen", return_value=mock_proc),
            patch("traceviz.tracer._resolve_target", return_value="9.9.9.9"),
        ):
            hops = list(stream_traceroute("example.com"))

        assert len(hops) == 1
        mock_proc.kill.assert_called_once_with()

    def test_raises_with_stderr_when_process_exits_without_any_hops(self):
        mock_proc = MagicMock()
        mock_proc.stdout = iter([])
        mock_proc.poll.return_value = 1
        mock_proc.returncode = 1
        mock_proc.stderr.read.return_value = "permission denied"

        with (
            patch("traceviz.tracer.subprocess.Popen", return_value=mock_proc),
            patch("traceviz.tracer._resolve_target", return_value="1.2.3.4"),
            pytest.raises(RuntimeError, match="permission denied"),
        ):
            list(stream_traceroute("example.com"))

    def test_raises_generic_error_when_process_exits_without_output(self):
        mock_proc = MagicMock()
        mock_proc.stdout = iter([])
        mock_proc.poll.return_value = 1
        mock_proc.returncode = 1
        mock_proc.stderr.read.return_value = ""

        with (
            patch("traceviz.tracer.subprocess.Popen", return_value=mock_proc),
            patch("traceviz.tracer._resolve_target", return_value="1.2.3.4"),
            pytest.raises(RuntimeError, match="no output"),
        ):
            list(stream_traceroute("example.com"))

    def test_uses_windows_parser_when_requested(self):
        mock_proc = MagicMock()
        mock_proc.stdout = iter(["  1     2 ms     3 ms     2 ms  10.0.0.1\n"])
        mock_proc.poll.return_value = 0
        mock_proc.returncode = 0

        with (
            patch("traceviz.tracer._build_traceroute_cmd", return_value=(["tracert"], "windows")),
            patch("traceviz.tracer.subprocess.Popen", return_value=mock_proc),
            patch("traceviz.tracer._resolve_target", return_value="99.99.99.99"),
        ):
            hops = list(stream_traceroute("example.com"))

        assert len(hops) == 1
        assert hops[0].ip == "10.0.0.1"
        assert hops[0].rtts == [2.0, 3.0, 2.0]
