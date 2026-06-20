"""Pydantic request/response schemas used by the HTTP API.

Date contract
-------------
Every bond-date field exchanged with the JS client is a canonical
``YYYYMMDD`` 8-digit string (see :mod:`app.utils.dates`). The
:data:`YyyymmddDate` annotated type enforces that on request payloads;
a non-conforming value is surfaced as HTTP 400 by the global
validation handler in :mod:`app.main`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from app.utils.dates import (
    InvalidDate,
    KNOWN_DATE_FIELDS,
    parse_yyyymmdd_strict,
    safe_to_yyyymmdd,
)


def _validate_yyyymmdd(value: str) -> str:
    try:
        parse_yyyymmdd_strict(value)
    except InvalidDate as exc:
        # Tagged so the global RequestValidationError handler in app.main
        # can map it to HTTP 400 rather than the default 422.
        raise ValueError(f"[YYYYMMDD] {exc}") from exc
    return value


YyyymmddDate = Annotated[
    str,
    Field(
        pattern=r"^\d{8}$",
        description="Date as an 8-digit YYYYMMDD string, e.g. '20250419'.",
        examples=["20250419"],
    ),
]


# ---------- Reference data ------------------------------------------------


class ReferenceDataRequest(BaseModel):
    securities: List[str] = Field(
        ...,
        min_length=1,
        description="Bloomberg security tickers, e.g. ['IBM US Equity', 'AAPL US Equity'].",
    )
    fields: List[str] = Field(
        ...,
        min_length=1,
        description="Bloomberg field mnemonics, e.g. ['PX_LAST', 'NAME'].",
    )
    overrides: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Optional field overrides, e.g. {'VWAP_START_TIME': '09:30'}. "
            "Values for known date overrides (e.g. ASOF_DATE) must be "
            "YYYYMMDD strings."
        ),
    )

    @field_validator("overrides")
    @classmethod
    def _validate_date_overrides(cls, v):
        if not v:
            return v
        for key, value in v.items():
            if key.upper() in KNOWN_DATE_FIELDS:
                try:
                    parse_yyyymmdd_strict(value)
                except InvalidDate as exc:
                    raise ValueError(
                        f"[YYYYMMDD] override {key!r}: {exc}"
                    ) from exc
        return v


class SecurityData(BaseModel):
    security: str
    fields: Dict[str, Any] = Field(default_factory=dict)
    field_exceptions: Dict[str, str] = Field(default_factory=dict)
    security_error: Optional[str] = None

    @field_validator("fields")
    @classmethod
    def _canonicalise_response_dates(cls, v):
        # Belt-and-braces: coerce known bond-date fields here as well,
        # so the serialisation contract holds even if a future code path
        # populates ``fields`` without routing through
        # ``service.coerce_field_value``.
        if not v:
            return v
        out: Dict[str, Any] = {}
        for key, value in v.items():
            if key.upper() in KNOWN_DATE_FIELDS and value is not None:
                out[key] = safe_to_yyyymmdd(value)
            else:
                out[key] = value
        return out


class ReferenceDataResponse(BaseModel):
    data: List[SecurityData]


# ---------- Historical data -----------------------------------------------


class HistoricalDataRequest(BaseModel):
    securities: List[str] = Field(..., min_length=1)
    fields: List[str] = Field(..., min_length=1)
    start_date: YyyymmddDate
    end_date: YyyymmddDate
    periodicity: str = Field(
        default="DAILY",
        description="DAILY | WEEKLY | MONTHLY | QUARTERLY | SEMI_ANNUALLY | YEARLY",
    )
    currency: Optional[str] = Field(
        default=None, description="ISO currency code for FX-converted values."
    )
    non_trading_day_fill_option: Optional[str] = Field(
        default=None,
        description="NON_TRADING_WEEKDAYS | ALL_CALENDAR_DAYS | ACTIVE_DAYS_ONLY",
    )
    non_trading_day_fill_method: Optional[str] = Field(
        default=None, description="PREVIOUS_VALUE | NIL_VALUE"
    )
    max_data_points: Optional[int] = None
    overrides: Optional[Dict[str, Any]] = None

    @field_validator("start_date", "end_date")
    @classmethod
    def _validate_historical_dates(cls, v: str) -> str:
        return _validate_yyyymmdd(v)

    @field_validator("overrides")
    @classmethod
    def _validate_date_overrides(cls, v):
        if not v:
            return v
        for key, value in v.items():
            if key.upper() in KNOWN_DATE_FIELDS:
                try:
                    parse_yyyymmdd_strict(value)
                except InvalidDate as exc:
                    raise ValueError(
                        f"[YYYYMMDD] override {key!r}: {exc}"
                    ) from exc
        return v


class HistoricalBar(BaseModel):
    date: Optional[str] = Field(
        default=None,
        pattern=r"^\d{8}$",
        description="Bar date as YYYYMMDD. Null if the upstream value was unparseable.",
        examples=["20250419"],
    )
    fields: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("fields")
    @classmethod
    def _canonicalise_bar_dates(cls, v):
        if not v:
            return v
        out: Dict[str, Any] = {}
        for key, value in v.items():
            if key.upper() in KNOWN_DATE_FIELDS and value is not None:
                out[key] = safe_to_yyyymmdd(value)
            else:
                out[key] = value
        return out


class HistoricalSecurityData(BaseModel):
    security: str
    bars: List[HistoricalBar] = Field(default_factory=list)
    security_error: Optional[str] = None


class HistoricalDataResponse(BaseModel):
    data: List[HistoricalSecurityData]


# ---------- Intraday bars -------------------------------------------------


class IntradayBarRequest(BaseModel):
    security: str
    event_type: str = Field(
        default="TRADE",
        description="TRADE | BID | ASK | BID_BEST | ASK_BEST | BEST_BID | BEST_ASK",
    )
    interval: int = Field(default=1, ge=1, le=1440, description="Bar length in minutes.")
    start_datetime: datetime
    end_datetime: datetime
    gap_fill_initial_bar: bool = False
    adjustment_normal: bool = False
    adjustment_abnormal: bool = False
    adjustment_split: bool = False
    adjustment_follow_dpdf: bool = True


class IntradayBar(BaseModel):
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    num_events: int
    value: float


class IntradayBarResponse(BaseModel):
    security: str
    bars: List[IntradayBar]


# ---------- Security search / lookup --------------------------------------


class InstrumentLookupRequest(BaseModel):
    query: str = Field(..., min_length=1)
    max_results: int = Field(default=20, ge=1, le=100)
    yellow_key_filter: Optional[str] = Field(
        default=None,
        description="YK_FILTER_CMDT | YK_FILTER_EQTY | YK_FILTER_MUNI | "
        "YK_FILTER_PRFD | YK_FILTER_CLNT | YK_FILTER_MMKT | "
        "YK_FILTER_GOVT | YK_FILTER_CORP | YK_FILTER_INDX | "
        "YK_FILTER_CURR | YK_FILTER_MTGE",
    )


class InstrumentMatch(BaseModel):
    security: str
    description: str


class InstrumentLookupResponse(BaseModel):
    matches: List[InstrumentMatch]


# ---------- Errors --------------------------------------------------------


class ErrorResponse(BaseModel):
    detail: str
