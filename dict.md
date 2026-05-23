# Data Dictionary: dirty_orders

- **Database**: dirty.duckdb
- **Rows**: 20

## Columns

| Column | Type | Nullable | Distinct | Min | Max | Semantic |
|--------|------|----------|----------|-----|-----|----------|
| order_id | INTEGER | No | 20 | 1 | 20 | identifier |
| user_id | INTEGER | Yes | 9 | 1 | 99 | identifier |
| status | VARCHAR | Yes | 5 | cancelled | unknown_status | category |
| total_amount | DECIMAL(10,2) | No | 19 | -200.00 | 99999.99 | measure |
| payment_method | VARCHAR | Yes | 5 | alipay | wechat | category |
| created_at | TIMESTAMP | No | 20 | 2026-05-16 11:05:53.345754 | 2026-05-23 10:05:53.345754 | timestamp |
| updated_at | TIMESTAMP | No | 20 | 2026-05-16 12:05:53.345754 | 2026-05-23 10:35:53.345754 | timestamp |

## Quality Rules

| Type | Column | Confidence | Severity | Reason |
|------|--------|------------|----------|--------|
| not_null | order_id | 90% | high | Column 'order_id' has zero nulls across all rows, likely a required field. |
| unique | order_id | 85% | high | Column 'order_id' is an identifier with 100.0% distinct rate, likely unique. |
| range | order_id | 70% | low | Column 'order_id' is numeric, observed range [1, 20]. |
| not_null | user_id | 80% | high | Column 'user_id' is inferred as an identifier and should not be null. |
| range | user_id | 70% | low | Column 'user_id' is numeric, observed range [1, 99]. |
| accepted_values | status | 80% | medium | Column 'status' is a category field with only 5 distinct values. |
| not_null | total_amount | 90% | medium | Column 'total_amount' has zero nulls across all rows, likely a required field. |
| range | total_amount | 70% | low | Column 'total_amount' is numeric, observed range [-200.00, 99999.99]. |
| accepted_values | payment_method | 80% | medium | Column 'payment_method' is a category field with only 5 distinct values. |
| not_null | created_at | 90% | medium | Column 'created_at' has zero nulls across all rows, likely a required field. |
| freshness | created_at | 75% | high | Column 'created_at' is a timestamp field, checking data freshness (max 24h lag). |
| not_null | updated_at | 90% | medium | Column 'updated_at' has zero nulls across all rows, likely a required field. |
| freshness | updated_at | 75% | high | Column 'updated_at' is a timestamp field, checking data freshness (max 24h lag). |
