from __future__ import annotations

from pathlib import Path

import pytest

from dqdoctor.correlation import detect_correlations
from dqdoctor.demo import create_demo_db
from dqdoctor.drift import compare_profiles, load_profile, save_profile
from dqdoctor.fk_discovery import discover_foreign_keys
from dqdoctor.lineage import discover_lineage
from dqdoctor.pii_detector import detect_pii_type
from dqdoctor.profiler import profile_table


@pytest.fixture
def demo_db(tmp_path: Path):
    return create_demo_db(tmp_path / "test.duckdb")


def test_detect_email():
    assert detect_pii_type("email", ["user@example.com", "admin@test.org"]) == "email"


def test_detect_phone_cn():
    assert detect_pii_type("phone", ["13800138000", "15912345678"]) == "phone_cn"


def test_detect_id_card_cn():
    assert detect_pii_type("id_card", ["110101199001011234", "31010120000101123X"]) == "id_card_cn"


def test_detect_ip():
    assert detect_pii_type("ip", ["192.168.1.1", "10.0.0.1", "172.16.0.1"]) == "ip_address"


def test_no_pii():
    assert detect_pii_type("status", ["pending", "shipped"]) is None


def test_pii_wrong_values():
    assert detect_pii_type("email", ["not-an-email", "also-not"]) is None


def test_pii_in_profile(demo_db: Path):
    profile = profile_table(demo_db, "orders")
    for col in profile.columns:
        assert hasattr(col, "pii_type")


def test_discover_fk(demo_db: Path):
    relationships = discover_foreign_keys(demo_db)
    assert isinstance(relationships, list)
    fk_pairs = [(r.from_table, r.from_column, r.to_table) for r in relationships]
    has_user_ref = any(
        ft == "orders" and fc == "user_id" and tt == "users" for ft, fc, tt in fk_pairs
    )
    assert has_user_ref


def test_fk_confidence_range(demo_db: Path):
    relationships = discover_foreign_keys(demo_db)
    for r in relationships:
        assert 0.0 <= r.confidence <= 1.0
        assert 0.0 <= r.overlap_rate <= 1.0


def test_correlation(demo_db: Path):
    corrs = detect_correlations(demo_db, "orders")
    assert isinstance(corrs, list)


def test_correlation_confidence_range(demo_db: Path):
    corrs = detect_correlations(demo_db, "orders")
    for c in corrs:
        assert 0.0 <= c.confidence <= 1.0


def test_drift_no_change(demo_db: Path):
    profile = profile_table(demo_db, "orders")
    result = compare_profiles(profile, profile)
    assert len(result.drifts) == 0


def test_drift_null_rate(demo_db: Path):
    from dqdoctor.models import ColumnProfile, ProfileResult

    old = ProfileResult(
        db_path="old",
        table_name="t",
        row_count=100,
        columns=[
            ColumnProfile(
                name="col1",
                dtype="INTEGER",
                null_count=0,
                null_rate=0.0,
                distinct_count=50,
                distinct_rate=0.5,
            )
        ],
    )
    new = ProfileResult(
        db_path="new",
        table_name="t",
        row_count=100,
        columns=[
            ColumnProfile(
                name="col1",
                dtype="INTEGER",
                null_count=20,
                null_rate=0.2,
                distinct_count=50,
                distinct_rate=0.5,
            )
        ],
    )
    result = compare_profiles(old, new)
    assert len(result.drifts) == 1
    assert result.drifts[0].metric == "null_rate"
    assert result.drifts[0].severity == "high"


def test_drift_dtype_change():
    from dqdoctor.models import ColumnProfile, ProfileResult

    old = ProfileResult(
        db_path="old",
        table_name="t",
        row_count=10,
        columns=[
            ColumnProfile(
                name="col1",
                dtype="INTEGER",
                null_count=0,
                null_rate=0.0,
                distinct_count=5,
                distinct_rate=0.5,
            )
        ],
    )
    new = ProfileResult(
        db_path="new",
        table_name="t",
        row_count=10,
        columns=[
            ColumnProfile(
                name="col1",
                dtype="VARCHAR",
                null_count=0,
                null_rate=0.0,
                distinct_count=5,
                distinct_rate=0.5,
            )
        ],
    )
    result = compare_profiles(old, new)
    assert any(d.metric == "dtype" for d in result.drifts)


def test_save_load_profile(demo_db: Path, tmp_path: Path):
    profile = profile_table(demo_db, "orders")
    path = save_profile(profile, tmp_path / "profile.json")
    assert path.exists()
    loaded = load_profile(path)
    assert loaded.table_name == "orders"
    assert loaded.row_count == 20


def test_lineage(demo_db: Path):
    result = discover_lineage(demo_db)
    assert isinstance(result.edges, list)
    assert "lineage" in result.summary.lower() or "edge" in result.summary.lower()


def test_drift_column_added():
    from dqdoctor.models import ColumnProfile, ProfileResult

    old = ProfileResult(
        db_path="old",
        table_name="t",
        row_count=10,
        columns=[
            ColumnProfile(
                name="a",
                dtype="INTEGER",
                null_count=0,
                null_rate=0.0,
                distinct_count=5,
                distinct_rate=0.5,
            )
        ],
    )
    new = ProfileResult(
        db_path="new",
        table_name="t",
        row_count=10,
        columns=[
            ColumnProfile(
                name="a",
                dtype="INTEGER",
                null_count=0,
                null_rate=0.0,
                distinct_count=5,
                distinct_rate=0.5,
            ),
            ColumnProfile(
                name="b",
                dtype="VARCHAR",
                null_count=0,
                null_rate=0.0,
                distinct_count=3,
                distinct_rate=0.3,
            ),
        ],
    )
    result = compare_profiles(old, new)
    assert any(d.metric == "existence" and d.column == "b" for d in result.drifts)
