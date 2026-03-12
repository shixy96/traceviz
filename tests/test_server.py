"""server.py unit tests."""

from traceviz.analyzer import AnalyzedHop
from traceviz.server import create_app


def _make_hop() -> AnalyzedHop:
    return AnalyzedHop(
        hop_number=1,
        ip="8.8.8.8",
        avg_rtt=12.3,
        is_timeout=False,
        city="Mountain View",
        region="California",
        country="US",
        lat=37.4056,
        lon=-122.0775,
        org="Google LLC",
        asn="AS15169",
        backbone="",
        segment="target",
        color="#4caf50",
        latency_jump=None,
        is_cross_ocean=False,
        hostname="dns.google",
        is_anycast=True,
    )


def test_api_trace_returns_expected_payload():
    app = create_app([_make_hop()], "example.com")
    client = app.test_client()

    resp = client.get("/api/trace")

    assert resp.status_code == 200
    assert resp.get_json() == {
        "target": "example.com",
        "hops": [
            {
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
        ],
    }


def test_api_trace_does_not_enable_cross_origin_access():
    app = create_app([_make_hop()], "example.com")
    client = app.test_client()

    resp = client.get("/api/trace", headers={"Origin": "https://evil.example"})

    assert "Access-Control-Allow-Origin" not in resp.headers
