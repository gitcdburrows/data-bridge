"""Canonical YYYYMMDD date handling for the Bloomberg bridge.

Every date field crossing the HTTP boundary (request or response) is
serialised as an 8-digit ``YYYYMMDD`` string with no separators. This
format is locale-unambiguous and is the only format the Universe Explorer
client's ``plParseDate`` guarantees to accept.

Use ``to_yyyymmdd`` at the serialisation boundary (lenient: accepts
``date``/``datetime``/ISO string) and ``parse_yyyymmdd_strict`` at the
deserialisation boundary (strict: must already be the canonical 8 digits).

Any bond-date response field listed in :data:`KNOWN_DATE_FIELDS` is
coerced to YYYYMMDD even if Bloomberg returns it as a DATETIME or string.
"""

from __future__ import annotations

import datetime as _dt
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

YYYYMMDD_RE = re.compile(r"^\d{8}$")

# Bloomberg mnemonics that are conceptually pure dates (no meaningful time).
# Responses for these fields are forced to YYYYMMDD even when the API
# returns them as DATETIME or a free-form string. Add to this set as more
# bond-date fields are consumed downstream.
KNOWN_DATE_FIELDS = frozenset(
    {
        "ASOF_DATE",
        "AS_OF_DATE",
        "DATE",
        "SETTLE_DT",
        "SETTLEMENT_DATE",
        "MATURITY",
        "MATURITY_DT",
        "MATURITY_DATE",
        "ISSUE_DT",
        "ISSUE_DATE",
        "FIRST_CPN_DT",
        "FIRST_COUPON_DATE",
        "NXT_CPN_DT",
        "NEXT_COUPON_DATE",
        "LAST_UPDATE_DT",
        "ANNOUNCE_DT",
        "WORKOUT_DT",
        "EFFECTIVE_DT",
        "FIRST_SETTLE_DT",
    }
)


class InvalidDate(ValueError):
    """Raised when a value cannot be coerced to a canonical YYYYMMDD string."""


def to_yyyymmdd(value: Any) -> str:
    """Coerce ``value`` to an 8-digit ``YYYYMMDD`` string.

    Accepts ``datetime.date``, ``datetime.datetime`` and strings in
    YYYYMMDD, ISO date (``YYYY-MM-DD``) or ISO datetime
    (``YYYY-MM-DDTHH:MM:SS``). Raises :class:`InvalidDate` on anything
    else so malformed values surface immediately at the boundary.
    """
    if value is None:
        raise InvalidDate("Expected a date, got None")

    if isinstance(value, _dt.datetime):
        return value.strftime("%Y%m%d")
    if isinstance(value, _dt.date):
        return value.strftime("%Y%m%d")
    if isinstance(value, str):
        s = value.strip()
        if not s:
            raise InvalidDate("Expected a date, got empty string")
        if YYYYMMDD_RE.match(s):
            # Validate that it is a real calendar date (rejects 20250230).
            try:
                _dt.datetime.strptime(s, "%Y%m%d")
            except ValueError as exc:
                raise InvalidDate(f"Invalid calendar date {value!r}") from exc
            return s
        # Try ISO calendar date.
        try:
            return _dt.date.fromisoformat(s).strftime("%Y%m%d")
        except ValueError:
            pass
        # Try full ISO datetime (drops time component).
        try:
            return _dt.datetime.fromisoformat(s).strftime("%Y%m%d")
        except ValueError:
            pass
        raise InvalidDate(
            f"Cannot parse {value!r} as a date (expected YYYYMMDD or ISO 8601)"
        )

    raise InvalidDate(
        f"Cannot coerce type {type(value).__name__} to a YYYYMMDD date"
    )


def safe_to_yyyymmdd(value: Any) -> Optional[str]:
    """Best-effort coercion.

    Returns the canonical string on success, ``None`` on failure. Logs a
    warning — used when we'd rather pass through ``null`` than fail the
    whole response because one field is malformed upstream.
    """
    if value is None:
        return None
    try:
        return to_yyyymmdd(value)
    except InvalidDate as exc:
        logger.warning("Dropping malformed date value %r: %s", value, exc)
        return None


def parse_yyyymmdd_strict(value: Any) -> _dt.date:
    """Parse an *already canonical* YYYYMMDD string, raising otherwise.

    Use this on the request path so clients that send ISO or free-form
    dates get a clear 400 error instead of silent coercion.
    """
    if not isinstance(value, str) or not YYYYMMDD_RE.match(value):
        raise InvalidDate(
            f"Expected date in YYYYMMDD format (8 digits, no separators), "
            f"got {value!r}"
        )
    try:
        return _dt.datetime.strptime(value, "%Y%m%d").date()
    except ValueError as exc:
        raise InvalidDate(f"Invalid calendar date {value!r}") from exc


def coerce_field_value(field_name: str, value: Any) -> Any:
    """If ``field_name`` is a known bond-date field, coerce to YYYYMMDD.

    Otherwise return ``value`` unchanged. This runs at the serialisation
    boundary so the downstream client never sees a free-form date string
    for a field it expects to parse.
    """
    if value is None:
        return None
    if field_name.upper() not in KNOWN_DATE_FIELDS:
        return value
    return safe_to_yyyymmdd(value)
