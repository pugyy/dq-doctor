from dqdoctor.models import (
    ColumnProfile,
    ProfileResult,
    ReportResult,
    RuleSuggestion,
    ValidationResult,
)


def test_column_profile_creation():
    col = ColumnProfile(
        name="order_id",
        dtype="INTEGER",
        null_count=0,
        null_rate=0.0,
        distinct_count=20,
        distinct_rate=1.0,
        min_value=1,
        max_value=20,
        sample_values=[1, 2, 3],
        inferred_semantic_type="identifier",
    )
    assert col.name == "order_id"
    assert col.inferred_semantic_type == "identifier"


def test_column_profile_defaults():
    col = ColumnProfile(
        name="col_a",
        dtype="VARCHAR",
        null_count=5,
        null_rate=0.25,
        distinct_count=10,
        distinct_rate=0.5,
    )
    assert col.min_value is None
    assert col.max_value is None
    assert col.sample_values == []
    assert col.inferred_semantic_type == "unknown"


def test_profile_result_serialization():
    profile = ProfileResult(
        db_path="test.duckdb",
        table_name="orders",
        row_count=100,
        columns=[
            ColumnProfile(
                name="id",
                dtype="INTEGER",
                null_count=0,
                null_rate=0.0,
                distinct_count=100,
                distinct_rate=1.0,
            )
        ],
    )
    json_str = profile.model_dump_json()
    restored = ProfileResult.model_validate_json(json_str)
    assert restored.table_name == "orders"
    assert restored.row_count == 100
    assert len(restored.columns) == 1


def test_rule_suggestion():
    rule = RuleSuggestion(
        rule_id="not_null.order_id.1",
        rule_type="not_null",
        column="order_id",
        params={},
        confidence=0.9,
        severity="high",
        reason="Column has zero nulls.",
        source="heuristic",
    )
    assert rule.source == "heuristic"
    json_str = rule.model_dump_json()
    restored = RuleSuggestion.model_validate_json(json_str)
    assert restored.confidence == 0.9


def test_validation_result():
    result = ValidationResult(
        rule_id="not_null.order_id.1",
        rule_type="not_null",
        column="order_id",
        passed=True,
        failed_count=0,
        total_count=100,
        message="All 100 rows have non-null 'order_id'.",
    )
    assert result.passed is True
    json_str = result.model_dump_json()
    restored = ValidationResult.model_validate_json(json_str)
    assert restored.total_count == 100


def test_report_result():
    report = ReportResult(
        db_path="test.duckdb",
        table_name="orders",
        row_count=100,
        column_count=5,
        total_rules=8,
        passed_rules=7,
        failed_rules=1,
        profile=ProfileResult(
            db_path="test.duckdb",
            table_name="orders",
            row_count=100,
            columns=[],
        ),
        rules=[],
        results=[],
    )
    assert report.total_rules == 8
    json_str = report.model_dump_json()
    restored = ReportResult.model_validate_json(json_str)
    assert restored.passed_rules == 7
