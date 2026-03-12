"""延迟突变检测与网络段分类。"""

from dataclasses import dataclass

from .ip_lookup import IPInfo
from .tracer import Hop

# 延迟突变阈值 (ms)
LATENCY_JUMP_THRESHOLD = 100

# 网络段类型及对应颜色
SEGMENT_COLORS = {
    "local": "#9e9e9e",  # 灰色 - 局域网/私有
    "backbone": "#ff9800",  # 琥珀色 - 国内骨干网
    "transit": "#2196f3",  # 蓝色 - 普通转发
    "international": "#f44336",  # 红色 - 国际段
    "target": "#4caf50",  # 绿色 - 目标
}


@dataclass
class AnalyzedHop:
    hop_number: int
    ip: str | None
    avg_rtt: float | None
    is_timeout: bool
    city: str
    region: str
    country: str
    lat: float | None
    lon: float | None
    org: str
    asn: str
    backbone: str
    segment: str
    color: str
    latency_jump: float | None  # latency delta from previous hop
    is_cross_ocean: bool  # possible cross-ocean hop
    hostname: str = ""
    is_anycast: bool = False


def _classify_segment(
    hop: Hop,
    info: IPInfo | None,
    is_target: bool,
) -> str:
    """判断某跳属于哪个网络段。"""
    if is_target:
        return "target"

    if info is None or info.is_private:
        return "local"

    if info.backbone:
        return "backbone"

    return "transit"


def analyze(
    hops: list[Hop],
    ip_infos: dict[str, "IPInfo"],
    target_ip: str | None = None,
) -> list[AnalyzedHop]:
    """分析 traceroute 结果，返回带分析信息的跳列表。"""
    results: list[AnalyzedHop] = []
    prev_rtt: float | None = None

    for hop in hops:
        is_target = hop.ip is not None and hop.ip == target_ip
        info = ip_infos.get(hop.ip) if hop.ip else None

        segment = _classify_segment(hop, info, is_target)

        # 计算延迟跳变
        latency_jump: float | None = None
        is_cross_ocean = False
        avg_rtt = hop.avg_rtt

        if avg_rtt is not None and prev_rtt is not None:
            latency_jump = round(avg_rtt - prev_rtt, 2)
            if latency_jump > LATENCY_JUMP_THRESHOLD and not is_target:
                is_cross_ocean = True
                segment = "international"

        if avg_rtt is not None:
            prev_rtt = avg_rtt

        color = SEGMENT_COLORS.get(segment, SEGMENT_COLORS["transit"])

        results.append(
            AnalyzedHop(
                hop_number=hop.hop_number,
                ip=hop.ip,
                avg_rtt=avg_rtt,
                is_timeout=hop.is_timeout,
                city=info.city if info else "",
                region=info.region if info else "",
                country=info.country if info else "",
                lat=info.lat if info else None,
                lon=info.lon if info else None,
                org=info.org if info else "",
                asn=info.asn if info else "",
                backbone=info.backbone if info else "",
                segment=segment,
                color=color,
                latency_jump=latency_jump,
                is_cross_ocean=is_cross_ocean,
                hostname=info.hostname if info else "",
                is_anycast=info.is_anycast if info else False,
            )
        )

    return results
