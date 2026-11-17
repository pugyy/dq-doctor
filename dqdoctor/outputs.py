"""Versioned outputs: JSON, JUnit XML and HTML.

Redaction policy: raw samples never leave the process. Profile JSON
replaces text min/max with fingerprints; PII findings carry evidence
counts only; FK issues carry counts only. Connection strings were already
redacted at the datasource layer.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from dqdoctor.models import CheckOutcome, RuleStatus
from dqdoctor.redact import redact_scalar

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def _redacted_payload(outcome: CheckOutcome) -> dict:
    data = json.loads(outcome.model_dump_json())
    for table in data.get("tables", []):
        columns = (table.get("profile") or {}).get("columns", [])
        for col in columns:
            col["min_value"] = redact_scalar(col.get("min_value"))
            col["max_value"] = redact_scalar(col.get("max_value"))
    return data


def write_json(outcome: CheckOutcome, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_redacted_payload(outcome), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def write_junit(outcome: CheckOutcome, path: Path) -> Path:
    """JUnit XML for CI systems (one testsuite per table)."""
    root = ET.Element("testsuites", {
        "name": "dq-doctor",
        "time": "0",
    })
    for table in outcome.tables:
        failures = sum(
            1 for r in table.rule_results if r.status is RuleStatus.FAIL
            and not r.exempted
        )
        errors = sum(1 for r in table.rule_results if r.status is RuleStatus.ERROR)
        # A testcase is "skipped" when it produced a <skipped> element: SKIP
        # results, baseline-exempted failures and suggestions. The count must
        # match the elements, or CI dashboards mis-report.
        skipped = sum(
            1 for r in table.rule_results
            if r.status is RuleStatus.SKIP
            or r.status is RuleStatus.SUGGESTION
            or (r.status is RuleStatus.FAIL and r.exempted)
        )
        suite = ET.SubElement(root, "testsuite", {
            "name": f"dq-doctor.{table.table_name}",
            "tests": str(len(table.rule_results)),
            "failures": str(failures),
            "errors": str(errors),
            "skipped": str(skipped),
        })
        for r in table.rule_results:
            case = ET.SubElement(suite, "testcase", {
                "classname": f"dq.{table.table_name}",
                "name": r.rule_id,
            })
            if r.status is RuleStatus.FAIL and not r.exempted:
                fail = ET.SubElement(case, "failure", {
                    "type": f"quality.{r.rule_type}",
                    "message": r.message,
                })
                fail.text = r.message
            elif r.status is RuleStatus.FAIL and r.exempted:
                ET.SubElement(case, "skipped", {
                    "message": f"baseline-exempted: {r.message}"
                })
            elif r.status is RuleStatus.ERROR:
                err = ET.SubElement(case, "error", {
                    "type": "execution", "message": r.message,
                })
                err.text = r.message
            elif r.status is RuleStatus.SKIP:
                ET.SubElement(case, "skipped", {"message": r.message})
            elif r.status is RuleStatus.SUGGESTION:
                ET.SubElement(case, "skipped", {"message": f"suggestion: {r.message}"})
    ET.indent(root, space="  ")
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    return path


def render_html(outcome: CheckOutcome) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
    )
    template = env.get_template("report.html")
    return template.render(outcome=outcome, redact=redact_scalar)


def write_html(outcome: CheckOutcome, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(outcome), encoding="utf-8")
    return path
