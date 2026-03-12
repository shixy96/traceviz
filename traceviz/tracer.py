"""Run traceroute and parse output."""

import platform
import re
import subprocess
from collections.abc import Generator
from dataclasses import dataclass, field


@dataclass
class Hop:
    hop_number: int
    ip: str | None = None
    rtts: list[float] = field(default_factory=list)
    is_timeout: bool = False

    @property
    def avg_rtt(self) -> float | None:
        if not self.rtts:
            return None
        return round(sum(self.rtts) / len(self.rtts), 2)


# macOS/Linux traceroute 输出行:
#  1  192.168.1.1  1.234 ms  1.456 ms  1.789 ms
#  2  * * *
#  3  10.0.0.1  5.123 ms  *  5.456 ms
_HOP_RE = re.compile(
    r"^\s*(\d+)\s+"  # 跳数
)
_IP_RE = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3})")
_RTT_RE = re.compile(r"([\d.]+)\s*ms")

# Windows tracert 输出行:
#  1    <1 ms    <1 ms    <1 ms  192.168.1.1
#  2     2 ms     3 ms     2 ms  10.0.0.1
#  3     *        *        *     请求超时。
_WIN_RTT_RE = re.compile(r"<?([\d.]+)\s*ms")


def _parse_line(line: str) -> Hop | None:
    """解析 traceroute 输出的一行。"""
    m = _HOP_RE.match(line)
    if not m:
        return None

    hop_number = int(m.group(1))
    rest = line[m.end() :]

    # 全超时
    if rest.strip().replace("*", "").replace(" ", "") == "":
        return Hop(hop_number=hop_number, is_timeout=True)

    # 提取 IP（取第一个出现的）
    ip_match = _IP_RE.search(rest)
    ip = ip_match.group(1) if ip_match else None

    # 提取所有 RTT
    rtts = [float(x) for x in _RTT_RE.findall(rest)]

    if not ip and not rtts:
        return Hop(hop_number=hop_number, is_timeout=True)

    return Hop(hop_number=hop_number, ip=ip, rtts=rtts)


def _parse_line_windows(line: str) -> Hop | None:
    """解析 Windows tracert 输出的一行。"""
    m = _HOP_RE.match(line)
    if not m:
        return None

    hop_number = int(m.group(1))
    rest = line[m.end() :]

    # Windows 超时行包含"请求超时"或全是 *
    stripped = rest.strip()
    if not stripped or stripped.replace("*", "").replace(" ", "") == "":
        return Hop(hop_number=hop_number, is_timeout=True)

    # 提取 IP（Windows tracert 中 IP 在行尾）
    ip_match = _IP_RE.search(rest)
    ip = ip_match.group(1) if ip_match else None

    # 提取所有 RTT（Windows 格式包含 <1 ms）
    rtts = [float(x) for x in _WIN_RTT_RE.findall(rest)]

    if not ip and not rtts:
        return Hop(hop_number=hop_number, is_timeout=True)

    return Hop(hop_number=hop_number, ip=ip, rtts=rtts)


def run_traceroute(
    target: str,
    max_hops: int = 30,
    icmp: bool = False,
    wait: int = 2,
    queries: int = 2,
) -> list[Hop]:
    """执行 traceroute 并返回解析后的跳列表。

    Args:
        icmp: 使用 ICMP 模式 (-I)，需要 root 权限，穿透性更好
        wait: 每跳等待超时秒数 (默认 2)
        queries: 每跳探测次数 (默认 2)
    """
    system = platform.system().lower()

    if system in ("darwin", "linux"):
        cmd = ["traceroute", "-n", "-q", str(queries), "-w", str(wait), "-m", str(max_hops)]
        if icmp:
            cmd.append("-I")
        cmd.append(target)
    else:
        cmd = ["tracert", "-d", "-h", str(max_hops), "-w", str(wait * 1000), target]

    # 确保 subprocess 超时 > traceroute 自身最大耗时
    # Windows tracert 固定每跳 3 次探测，不支持 -q 参数
    probes = 3 if system == "windows" else queries
    subprocess_timeout = max_hops * wait * probes + 30

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=subprocess_timeout,
        )
        output = proc.stdout

        # traceroute 失败时将 stderr 信息传递给用户
        if proc.returncode != 0 and not output.strip():
            stderr = proc.stderr.strip()
            if stderr:
                raise RuntimeError(f"traceroute failed: {stderr}")
            raise RuntimeError("traceroute failed (no output)")
    except FileNotFoundError as err:
        raise RuntimeError(
            "traceroute not installed, please install: brew install traceroute or apt install traceroute"
        ) from err
    except subprocess.TimeoutExpired as err:
        raise RuntimeError("traceroute timed out") from err

    # 根据平台选择解析函数
    parse_fn = _parse_line_windows if system == "windows" else _parse_line

    # 先解析所有跳
    all_hops = []
    for line in output.splitlines():
        hop = parse_fn(line)
        if hop is not None:
            all_hops.append(hop)

    # 智能截断尾部连续超时跳
    target_ip = _resolve_target(target)
    target_reached = False
    max_trailing_timeouts = 5

    for hop in all_hops:
        if hop.ip and hop.ip == target_ip:
            target_reached = True
            break

    if target_reached:
        # 目标已到达：保留到目标跳，之后最多保留少量超时跳
        hops = []
        after_target = False
        trailing = 0
        for hop in all_hops:
            if after_target and hop.is_timeout:
                trailing += 1
                if trailing >= max_trailing_timeouts:
                    break
            else:
                trailing = 0
            hops.append(hop)
            if hop.ip and hop.ip == target_ip:
                after_target = True
    else:
        # 目标未到达：剥离尾部连续超时跳（中间的超时跳保留）
        hops = list(all_hops)
        while hops and hops[-1].is_timeout:
            hops.pop()

    return hops


def _resolve_target(target: str) -> str | None:
    """Resolve target to IP address (cached)."""
    if not hasattr(_resolve_target, "_cache"):
        _resolve_target._cache = {}
    if target in _resolve_target._cache:
        return _resolve_target._cache[target]

    import socket

    try:
        ip = socket.gethostbyname(target)
    except socket.gaierror:
        ip = target
    _resolve_target._cache[target] = ip
    return ip


def _build_traceroute_cmd(
    target: str,
    max_hops: int = 30,
    icmp: bool = False,
    wait: int = 2,
    queries: int = 2,
) -> tuple[list[str], str]:
    """Build traceroute command and return (cmd, system)."""
    system = platform.system().lower()
    if system in ("darwin", "linux"):
        cmd = ["traceroute", "-n", "-q", str(queries), "-w", str(wait), "-m", str(max_hops)]
        if icmp:
            cmd.append("-I")
        cmd.append(target)
    else:
        cmd = ["tracert", "-d", "-h", str(max_hops), "-w", str(wait * 1000), target]
    return cmd, system


def stream_traceroute(
    target: str,
    max_hops: int = 30,
    icmp: bool = False,
    wait: int = 2,
    queries: int = 2,
) -> Generator[Hop, None, None]:
    """Stream traceroute hops one by one via Popen, yielding each as parsed.

    Terminates early once the target IP is reached.
    """
    cmd, system = _build_traceroute_cmd(target, max_hops, icmp, wait, queries)
    parse_fn = _parse_line_windows if system == "windows" else _parse_line
    target_ip = _resolve_target(target)

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as err:
        raise RuntimeError(
            "traceroute not installed, please install: brew install traceroute or apt install traceroute"
        ) from err

    hop_count = 0
    try:
        for line in proc.stdout:
            hop = parse_fn(line)
            if hop is not None:
                hop_count += 1
                yield hop
                if hop.ip and hop.ip == target_ip:
                    break
    finally:
        terminated_by_us = False
        if proc.poll() is None:
            terminated_by_us = True
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()

        # 检查是否失败且无有效输出（排除我们主动终止的情况）
        if not terminated_by_us and hop_count == 0 and proc.returncode != 0:
            stderr = proc.stderr.read().strip() if proc.stderr else ""
            if stderr:
                raise RuntimeError(f"traceroute failed: {stderr}")
            raise RuntimeError("traceroute failed (no output)")
