"""PII detection for dq-doctor 1.0.

Fixes over 0.7:

- Column-name hints match on word boundaries (``tel`` no longer hijacks
  ``hotel_id``), and a failed hint falls through to the pattern scan
  instead of aborting detection.
- IPs are validated with :mod:`ipaddress` (no ``999.999.999.999``, no
  ``12:34:56`` TIME strings mistaken for IPv6, no ``1.2.3.4`` version
  strings in ``*_version`` columns reported as IPs).
- Results carry evidence (matched fraction, sample size) and never carry
  raw sample values.
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

# Word-boundary name hints: (compiled hint regex, candidate pii type).
_NAME_HINTS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bemail\b", re.I), "email"),
    (re.compile(r"\bphone\b|\bmobile\b|\btel\b|\bmsisdn\b", re.I), "phone_cn"),
    (re.compile(r"\bid_?card\b|\bidentity\b|\bssn\b|\bresident_?id\b", re.I), "id_card_cn"),
    (re.compile(r"\bbank_?card\b|\bcard_?no\b|\bpan\b", re.I), "bank_card"),
    (re.compile(r"\bip_?addr|\bipaddr\b|\bip\b", re.I), "ip_address"),
    (re.compile(r"\bipv6\b", re.I), "ipv6_address"),
    (re.compile(r"\bmac_?addr|\bmac\b", re.I), "mac_address"),
]

# Columns whose values look like IPs but usually are not (version strings,
# build numbers, user agents, coordinates, durations).
_NOT_IP_NAME = re.compile(
    r"version|ver\b|build|revis|release|agent|platform|firmware|os\b|score|grade|rating",
    re.I,
)

_RE_EMAIL = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
_RE_PHONE_CN = re.compile(r"^1[3-9]\d{9}$")
_RE_ID_CARD_CN = re.compile(
    r"^[1-9]\d{5}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]$"
)
_RE_BANK_CARD = re.compile(r"^[3-6]\d{15,18}$")
_RE_MAC = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$")
_RE_IPV4ISH = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
_RE_IPV6ISH = re.compile(r"^[0-9A-Fa-f:]*:[0-9A-Fa-f:]*$")


@dataclass
class PIIEvidence:
    pii_type: str
    matched_fraction: float
    sample_size: int


def _matchers() -> dict[str, Callable[[str], bool]]:
    return {
        "email": lambda v: bool(_RE_EMAIL.match(v)),
        "phone_cn": lambda v: bool(_RE_PHONE_CN.match(v)),
        "id_card_cn": lambda v: bool(_RE_ID_CARD_CN.match(v)),
        "bank_card": lambda v: bool(_RE_BANK_CARD.match(v)),
        "mac_address": lambda v: bool(_RE_MAC.match(v)),
        "ip_address": _is_ipv4,
        "ipv6_address": _is_ipv6,
    }


def _is_ipv4(value: str) -> bool:
    if not _RE_IPV4ISH.match(value):
        return False
    try:
        ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError:
        return False
    return True


def _is_ipv6(value: str) -> bool:
    if ":" not in value or not _RE_IPV6ISH.match(value):
        return False
    try:
        ipaddress.IPv6Address(value)
    except ipaddress.AddressValueError:
        return False
    return True


def _verify(
    pii_type: str,
    str_values: list[str],
    matcher: Callable[[str], bool],
    threshold: float = 0.5,
) -> Optional[PIIEvidence]:
    if not str_values:
        return None
    hits = sum(1 for v in str_values if matcher(v))
    fraction = hits / len(str_values)
    if fraction >= threshold:
        return PIIEvidence(pii_type=pii_type, matched_fraction=round(fraction, 3),
                           sample_size=len(str_values))
    return None


def detect_pii(column_name: str, sample_values: list[Any]) -> Optional[PIIEvidence]:
    """Detect the PII type of a column from its name plus sample evidence.

    Raw sample values are inspected but never stored in the result.
    """
    str_values = [str(v) for v in sample_values if v is not None]
    if not str_values:
        return None

    matchers = _matchers()

    # 1. Name hints, word-boundary anchored. First hint whose values verify wins.
    for hint, pii_type in _NAME_HINTS:
        if hint.search(column_name):
            if pii_type in ("ip_address", "ipv6_address") and _NOT_IP_NAME.search(
                column_name
            ):
                continue
            evidence = _verify(pii_type, str_values, matchers[pii_type])
            if evidence:
                return evidence

    # 2. Fall through to a full pattern scan (name hints are only priors).
    if _NOT_IP_NAME.search(column_name):
        scan_types = [t for t in matchers if not t.startswith("ip")]
    else:
        scan_types = list(matchers)
    for pii_type in scan_types:
        evidence = _verify(pii_type, str_values, matchers[pii_type])
        if evidence:
            return evidence
    return None
