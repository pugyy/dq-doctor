from dqdoctor.llm.client import _parse_response


def test_parse_response_valid_json():
    text = (
        '[{"rule_type": "regex_pattern", "column": "email", '
        '"confidence": 0.8, "severity": "medium", "reason": "test"}]'
    )
    result = _parse_response(text)
    assert len(result) == 1
    assert result[0]["rule_type"] == "regex_pattern"


def test_parse_response_with_code_block():
    text = (
        '```json\n[{"rule_type": "test", "column": "x", '
        '"confidence": 0.5, "severity": "low", "reason": "r"}]\n```'
    )
    result = _parse_response(text)
    assert len(result) == 1


def test_parse_response_empty():
    assert _parse_response("") == []
    assert _parse_response("no json here") == []


def test_suggest_rules_llm_no_key():
    from dqdoctor.llm.client import suggest_rules_llm
    from dqdoctor.models import ColumnProfile

    col = ColumnProfile(
        name="id",
        dtype="INTEGER",
        null_count=0,
        null_rate=0.0,
        distinct_count=10,
        distinct_rate=1.0,
    )
    result = suggest_rules_llm([col], api_key=None)
    assert result == []
