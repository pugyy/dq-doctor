from __future__ import annotations

import re
from typing import Any

_PII_PATTERNS: list[tuple[str, re.Pattern]] = [
    (
        "email",
        re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"),
    ),
    (
        "phone_cn",
        re.compile(r"^1[3-9]\d{9}$"),
    ),
    (
        "id_card_cn",
        re.compile(r"^[1-9]\d{5}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]$"),
    ),
    (
        "bank_card",
        re.compile(r"^[3-6]\d{15,18}$"),
    ),
    (
        "ip_address",
        re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"),
    ),
    (
        "ipv6_address",
        re.compile(r"^([0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}$"),
    ),
    (
        "mac_address",
        re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$"),
    ),
]

_PII_NAME_HINTS: dict[str, str] = {
    "email": "email",
    "phone": "phone_cn",
    "mobile": "phone_cn",
    "tel": "phone_cn",
    "id_card": "id_card_cn",
    "identity": "id_card_cn",
    "ssn": "id_card_cn",
    "bank": "bank_card",
    "card_no": "bank_card",
    "ip": "ip_address",
    "mac": "mac_address",
}


def detect_pii_type(column_name: str, sample_values: list[Any]) -> str | None:
    lower = column_name.lower()
    for hint, pii_type in _PII_NAME_HINTS.items():
        if hint in lower:
            if _verify_pii(pii_type, sample_values):
                return pii_type
            return None

    for pii_type, pattern in _PII_PATTERNS:
        if _verify_pii(pii_type, sample_values):
            return pii_type

    return None


def _verify_pii(pii_type: str, sample_values: list[Any], threshold: float = 0.5) -> bool:
    pattern = next((p for t, p in _PII_PATTERNS if t == pii_type), None)
    if pattern is None:
        return False
    if not sample_values:
        return False
    str_values = [str(v) for v in sample_values if v is not None]
    if not str_values:
        return False
    matches = sum(1 for v in str_values if pattern.match(v))
    return matches / len(str_values) >= threshold


def detect_pii_for_columns(
    columns: list[dict],
    sample_fetcher: Any,
) -> dict[str, str]:
    result = {}
    for col in columns:
        name = col["name"]
        samples = sample_fetcher(name)
        pii_type = detect_pii_type(name, samples)
        if pii_type:
            result[name] = pii_type
    return result
