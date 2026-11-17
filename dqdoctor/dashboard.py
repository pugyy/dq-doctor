"""Read-only web view over an existing JSON report.

The dashboard renders what a ``check --json`` already produced; it never
touches databases. Table names and messages are escaped by Jinja's
autoescape (fixing 0.7's raw-interpolation hole).
"""
from __future__ import annotations

import json
from pathlib import Path

from dqdoctor.models import CheckOutcome
from dqdoctor.outputs import render_html


def run_dashboard(report: Path, host: str = "127.0.0.1", port: int = 8501) -> None:
    try:
        from flask import Flask, send_file
    except ImportError as exc:
        raise ImportError(
            "Flask is required for the dashboard. "
            "Install with: pip install 'dq-doctor[dashboard]'"
        ) from exc

    report_path = Path(report)
    if not report_path.exists():
        raise FileNotFoundError(f"Report not found: {report_path}")

    app = Flask(__name__)

    @app.route("/")
    def index():
        outcome = CheckOutcome.model_validate(
            json.loads(report_path.read_text(encoding="utf-8"))
        )
        return render_html(outcome)

    @app.route("/report.json")
    def raw():
        return send_file(report_path, mimetype="application/json")

    print(f"dq-doctor dashboard serving {report_path} at http://{host}:{port}")
    app.run(host=host, port=port, debug=False)
