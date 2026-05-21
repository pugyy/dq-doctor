from pathlib import Path

import pytest

from dqdoctor.demo import create_demo_db
from dqdoctor.profiler import infer_semantic_type, profile_table


@pytest.fixture
def demo_db(tmp_path: Path):
    return create_demo_db(tmp_path / "test.duckdb")


def test_infer_semantic_type():
    assert infer_semantic_type("order_id") == "identifier"
    assert infer_semantic_type("user_id") == "identifier"
    assert infer_semantic_type("total_amount") == "measure"
    assert infer_semantic_type("price") == "measure"
    assert infer_semantic_type("status") == "category"
    assert infer_semantic_type("category") == "category"
    assert infer_semantic_type("created_at") == "timestamp"
    assert infer_semantic_type("updated_at") == "timestamp"
    assert infer_semantic_type("region") == "category"
    assert infer_semantic_type("description") == "unknown"


def test_profile_orders(demo_db: Path):
    profile = profile_table(demo_db, "orders")
    assert profile.table_name == "orders"
    assert profile.row_count == 20

    col_names = [c.name for c in profile.columns]
    assert "order_id" in col_names
    assert "status" in col_names
    assert "total_amount" in col_names

    order_id = next(c for c in profile.columns if c.name == "order_id")
    assert order_id.null_count == 0
    assert order_id.null_rate == 0.0
    assert order_id.distinct_count == 20
    assert order_id.inferred_semantic_type == "identifier"


def test_profile_decimal_min_max(demo_db: Path):
    profile = profile_table(demo_db, "orders")
    amount = next(c for c in profile.columns if c.name == "total_amount")
    assert amount.min_value is not None
    assert amount.max_value is not None
    assert float(amount.min_value) == 45.00
    assert float(amount.max_value) == 680.00


def test_profile_status_category(demo_db: Path):
    profile = profile_table(demo_db, "orders")
    status = next(c for c in profile.columns if c.name == "status")
    assert status.inferred_semantic_type == "category"
    assert status.distinct_count <= 20
    assert len(status.sample_values) > 0
    assert len(status.distinct_values) == status.distinct_count


def test_profile_distinct_values_populated(demo_db: Path):
    profile = profile_table(demo_db, "orders")
    for col in profile.columns:
        if col.distinct_count <= 20:
            assert len(col.distinct_values) == col.distinct_count, (
                f"Column {col.name}: distinct_values length "
                f"!= distinct_count"
            )


def test_profile_users(demo_db: Path):
    profile = profile_table(demo_db, "users")
    email = next(c for c in profile.columns if c.name == "email")
    assert email.null_count == 1

    user_id = next(c for c in profile.columns if c.name == "user_id")
    assert user_id.inferred_semantic_type == "identifier"
    assert user_id.distinct_rate == 1.0


def test_profile_freshness_passes(demo_db: Path):
    profile = profile_table(demo_db, "orders")
    created = next(c for c in profile.columns if c.name == "created_at")
    assert created.min_value is not None
