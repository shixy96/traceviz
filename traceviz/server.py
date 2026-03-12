"""Flask 本地服务，提供 API 和静态文件。"""

import dataclasses
from pathlib import Path

from flask import Flask, jsonify

from .analyzer import AnalyzedHop

_static_dir = Path(__file__).parent / "static"


def create_app(trace_results: list[AnalyzedHop], target: str) -> Flask:
    app = Flask(__name__, static_folder=str(_static_dir), static_url_path="")

    @app.route("/")
    def index():
        return app.send_static_file("index.html")

    @app.route("/api/trace")
    def api_trace():
        return jsonify(
            {
                "target": target,
                "hops": [dataclasses.asdict(h) for h in trace_results],
            }
        )

    return app
