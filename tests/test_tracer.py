"""tracer.py unit tests."""

from unittest.mock import MagicMock, patch

from traceviz.tracer import _parse_line, _parse_line_windows, stream_traceroute


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
