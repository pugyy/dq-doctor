from __future__ import annotations

import json
import webbrowser

from dqdoctor.demo import list_tables
from dqdoctor.profiler import profile_table
from dqdoctor.reporter import build_report, render_html
from dqdoctor.rule_engine import generate_rules
from dqdoctor.validator import validate_rules


def create_app(db_path: str):
    try:
        from flask import Flask, jsonify
    except ImportError:
        raise ImportError(
            "Flask is required for dashboard mode. "
            "Install with: pip install dq-doctor[dashboard]"
        )

    app = Flask(__name__)

    @app.route("/")
    def index():
        tables = list_tables(db_path)
        links = "".join(
            f'<li><a href="/table/{t}">{t}</a></li>' for t in tables
        )
        return f"<html><body><h1>dq-doctor Dashboard</h1><ul>{links}</ul></body></html>"

    @app.route("/table/<table_name>")
    def table_view(table_name: str):
        profile = profile_table(db_path, table_name)
        rules = generate_rules(profile)
        results = validate_rules(db_path, table_name, rules)
        report = build_report(profile, rules, results)
        return render_html(report)

    @app.route("/api/profile/<table_name>")
    def api_profile(table_name: str):
        profile = profile_table(db_path, table_name)
        return json.loads(profile.model_dump_json())

    @app.route("/api/tables")
    def api_tables():
        return jsonify(list_tables(db_path))

    return app


def run_dashboard(db_path: str, host: str = "127.0.0.1", port: int = 8501):
    app = create_app(db_path)
    url = f"http://{host}:{port}"
    print(f"dq-doctor dashboard starting at {url}")
    webbrowser.open(url)
    app.run(host=host, port=port, debug=False)
