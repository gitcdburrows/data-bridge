"""Pydantic request/response schemas used by the HTTP API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


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
        description="Optional field overrides, e.g. {'VWAP_START_TIME': '09:30'}.",
    )


class SecurityData(BaseModel):
    security: str
    fields: Dict[str, Any] = Field(default_factory=dict)
    field_exceptions: Dict[str, str] = Field(default_factory=dict)
    security_error: Optional[str] = None


class ReferenceDataResponse(BaseModel):
    data: List[SecurityData]


# ---------- Historical data -----------------------------------------------


class HistoricalDataRequest(BaseModel):
    securities: List[str] = Field(..., min_length=1)
    fields: List[str] = Field(..., min_length=1)
    start_date: date
    end_date: date
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


class HistoricalBar(BaseModel):
    date: date
    fields: Dict[str, Any] = Field(default_factory=dict)


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


# ---------- Local SQL -----------------------------------------------------


class SQLQueryRequest(BaseModel):
    sql: str = Field(..., min_length=1, description="SQL statement to execute.")
    params: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Named bind parameters, e.g. {'ticker': 'IBM'} for `:ticker`.",
    )
    max_rows: Optional[int] = Field(
        default=None,
        ge=1,
        description="Per-request row cap. Clamped by server's SQL_MAX_ROWS.",
    )


class SQLQueryResponse(BaseModel):
    columns: List[str]
    rows: List[List[Any]]
    row_count: int
    truncated: bool


class SQLTableList(BaseModel):
    schema_name: Optional[str] = Field(default=None, alias="schema")
    tables: List[str]
    views: List[str]

    model_config = {"populate_by_name": True}


class SQLColumnInfo(BaseModel):
    name: str
    type: str
    nullable: bool
    default: Any = None
    primary_key: bool


class SQLTableSchema(BaseModel):
    schema_name: Optional[str] = Field(default=None, alias="schema")
    table: str
    columns: List[SQLColumnInfo]

    model_config = {"populate_by_name": True}


# ---------- Errors --------------------------------------------------------


class ErrorResponse(BaseModel):
    detail: str
