"""High-level Bloomberg operations used by the HTTP routers.

Every method here builds a ``blpapi.Request``, ships it through
``BloombergClient.send_request`` and normalises the response into plain
Python dicts/lists so FastAPI can serialise them to JSON for the JS client.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional

from app.bloomberg.client import BloombergClient, BloombergError, get_client

logger = logging.getLogger(__name__)

REFDATA_SERVICE = "//blp/refdata"
MKTDATA_SERVICE = "//blp/mktdata"
INSTRUMENTS_SERVICE = "//blp/instruments"


def _element_to_py(element) -> Any:
    """Recursively convert a blpapi.Element into a native Python value."""
    import blpapi  # noqa: WPS433

    if element.isNull():
        return None

    if element.isArray():
        return [_element_to_py(element.getValueAsElement(i)) for i in range(element.numValues())]

    if element.numElements() > 0:  # complex sub-element
        out: Dict[str, Any] = {}
        for i in range(element.numElements()):
            child = element.getElement(i)
            out[str(child.name())] = _element_to_py(child)
        return out

    # Scalar
    datatype = element.datatype()
    if datatype == blpapi.DataType.FLOAT32 or datatype == blpapi.DataType.FLOAT64:
        return element.getValueAsFloat()
    if datatype in (
        blpapi.DataType.INT32,
        blpapi.DataType.INT64,
    ):
        return element.getValueAsInteger()
    if datatype == blpapi.DataType.BOOL:
        return element.getValueAsBool()
    if datatype == blpapi.DataType.DATE:
        return element.getValueAsDatetime().date().isoformat()
    if datatype == blpapi.DataType.DATETIME or datatype == blpapi.DataType.TIME:
        return element.getValueAsDatetime().isoformat()
    try:
        return element.getValueAsString()
    except Exception:  # pragma: no cover
        return str(element)


class BloombergService:
    def __init__(self, client: Optional[BloombergClient] = None) -> None:
        self._client = client or get_client()

    # ------------------------------------------------------------------
    # Reference data
    # ------------------------------------------------------------------

    def reference_data(
        self,
        securities: List[str],
        fields: List[str],
        overrides: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        service = self._client.open_service(REFDATA_SERVICE)
        request = service.createRequest("ReferenceDataRequest")
        _append_all(request.getElement("securities"), securities)
        _append_all(request.getElement("fields"), fields)
        if overrides:
            ovr_el = request.getElement("overrides")
            for k, v in overrides.items():
                ov = ovr_el.appendElement()
                ov.setElement("fieldId", k)
                ov.setElement("value", v)

        messages = self._client.send_request(request)
        return _parse_reference_data(messages)

    # ------------------------------------------------------------------
    # Historical data
    # ------------------------------------------------------------------

    def historical_data(
        self,
        *,
        securities: List[str],
        fields: List[str],
        start_date: date,
        end_date: date,
        periodicity: str = "DAILY",
        currency: Optional[str] = None,
        non_trading_day_fill_option: Optional[str] = None,
        non_trading_day_fill_method: Optional[str] = None,
        max_data_points: Optional[int] = None,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        service = self._client.open_service(REFDATA_SERVICE)
        request = service.createRequest("HistoricalDataRequest")
        _append_all(request.getElement("securities"), securities)
        _append_all(request.getElement("fields"), fields)
        request.set("periodicitySelection", periodicity)
        request.set("startDate", start_date.strftime("%Y%m%d"))
        request.set("endDate", end_date.strftime("%Y%m%d"))
        if currency:
            request.set("currency", currency)
        if non_trading_day_fill_option:
            request.set("nonTradingDayFillOption", non_trading_day_fill_option)
        if non_trading_day_fill_method:
            request.set("nonTradingDayFillMethod", non_trading_day_fill_method)
        if max_data_points is not None:
            request.set("maxDataPoints", max_data_points)
        if overrides:
            ovr_el = request.getElement("overrides")
            for k, v in overrides.items():
                ov = ovr_el.appendElement()
                ov.setElement("fieldId", k)
                ov.setElement("value", v)

        messages = self._client.send_request(request)
        return _parse_historical_data(messages)

    # ------------------------------------------------------------------
    # Intraday bars
    # ------------------------------------------------------------------

    def intraday_bars(
        self,
        *,
        security: str,
        event_type: str,
        interval: int,
        start_datetime: datetime,
        end_datetime: datetime,
        gap_fill_initial_bar: bool = False,
        adjustment_normal: bool = False,
        adjustment_abnormal: bool = False,
        adjustment_split: bool = False,
        adjustment_follow_dpdf: bool = True,
    ) -> List[Dict[str, Any]]:
        service = self._client.open_service(REFDATA_SERVICE)
        request = service.createRequest("IntradayBarRequest")
        request.set("security", security)
        request.set("eventType", event_type)
        request.set("interval", interval)
        request.set("startDateTime", start_datetime)
        request.set("endDateTime", end_datetime)
        request.set("gapFillInitialBar", gap_fill_initial_bar)
        request.set("adjustmentNormal", adjustment_normal)
        request.set("adjustmentAbnormal", adjustment_abnormal)
        request.set("adjustmentSplit", adjustment_split)
        request.set("adjustmentFollowDPDF", adjustment_follow_dpdf)

        messages = self._client.send_request(request)
        return _parse_intraday_bars(messages)

    # ------------------------------------------------------------------
    # Instrument lookup
    # ------------------------------------------------------------------

    def instrument_lookup(
        self,
        query: str,
        max_results: int = 20,
        yellow_key_filter: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        service = self._client.open_service(INSTRUMENTS_SERVICE)
        request = service.createRequest("instrumentListRequest")
        request.set("query", query)
        request.set("maxResults", max_results)
        if yellow_key_filter:
            request.set("yellowKeyFilter", yellow_key_filter)

        messages = self._client.send_request(request)
        return _parse_instrument_lookup(messages)


# ---------- Helpers --------------------------------------------------------


def _append_all(element, values: Iterable[Any]) -> None:
    for v in values:
        element.appendValue(v)


def _parse_reference_data(messages) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for msg in messages:
        if not msg.hasElement("securityData"):
            if msg.hasElement("responseError"):
                raise BloombergError(
                    msg.getElement("responseError").getElementAsString("message")
                )
            continue
        securities_array = msg.getElement("securityData")
        for i in range(securities_array.numValues()):
            sec = securities_array.getValueAsElement(i)
            entry: Dict[str, Any] = {
                "security": sec.getElementAsString("security"),
                "fields": {},
                "field_exceptions": {},
                "security_error": None,
            }
            if sec.hasElement("securityError"):
                entry["security_error"] = sec.getElement("securityError").getElementAsString(
                    "message"
                )
            if sec.hasElement("fieldData"):
                fd = sec.getElement("fieldData")
                for j in range(fd.numElements()):
                    child = fd.getElement(j)
                    entry["fields"][str(child.name())] = _element_to_py(child)
            if sec.hasElement("fieldExceptions"):
                fx = sec.getElement("fieldExceptions")
                for j in range(fx.numValues()):
                    fe = fx.getValueAsElement(j)
                    field_id = fe.getElementAsString("fieldId")
                    info = fe.getElement("errorInfo")
                    entry["field_exceptions"][field_id] = info.getElementAsString("message")
            results.append(entry)
    return results


def _parse_historical_data(messages) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for msg in messages:
        if msg.hasElement("responseError"):
            raise BloombergError(
                msg.getElement("responseError").getElementAsString("message")
            )
        if not msg.hasElement("securityData"):
            continue
        sec = msg.getElement("securityData")
        entry: Dict[str, Any] = {
            "security": sec.getElementAsString("security"),
            "bars": [],
            "security_error": None,
        }
        if sec.hasElement("securityError"):
            entry["security_error"] = sec.getElement("securityError").getElementAsString(
                "message"
            )
        fd = sec.getElement("fieldData")
        for i in range(fd.numValues()):
            point = fd.getValueAsElement(i)
            bar: Dict[str, Any] = {"date": None, "fields": {}}
            for j in range(point.numElements()):
                child = point.getElement(j)
                name = str(child.name())
                if name == "date":
                    bar["date"] = _element_to_py(child)
                else:
                    bar["fields"][name] = _element_to_py(child)
            entry["bars"].append(bar)
        results.append(entry)
    return results


def _parse_intraday_bars(messages) -> List[Dict[str, Any]]:
    bars: List[Dict[str, Any]] = []
    for msg in messages:
        if msg.hasElement("responseError"):
            raise BloombergError(
                msg.getElement("responseError").getElementAsString("message")
            )
        if not msg.hasElement("barData"):
            continue
        bar_data = msg.getElement("barData")
        if not bar_data.hasElement("barTickData"):
            continue
        tick_data = bar_data.getElement("barTickData")
        for i in range(tick_data.numValues()):
            tick = tick_data.getValueAsElement(i)
            bars.append(
                {
                    "time": tick.getElementAsDatetime("time").isoformat(),
                    "open": tick.getElementAsFloat("open"),
                    "high": tick.getElementAsFloat("high"),
                    "low": tick.getElementAsFloat("low"),
                    "close": tick.getElementAsFloat("close"),
                    "volume": tick.getElementAsInteger("volume"),
                    "num_events": tick.getElementAsInteger("numEvents"),
                    "value": tick.getElementAsFloat("value"),
                }
            )
    return bars


def _parse_instrument_lookup(messages) -> List[Dict[str, str]]:
    matches: List[Dict[str, str]] = []
    for msg in messages:
        if not msg.hasElement("results"):
            continue
        arr = msg.getElement("results")
        for i in range(arr.numValues()):
            item = arr.getValueAsElement(i)
            matches.append(
                {
                    "security": item.getElementAsString("security"),
                    "description": item.getElementAsString("description"),
                }
            )
    return matches
