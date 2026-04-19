"""Unit tests for the YYYYMMDD helper and the serialisation boundary.

Each bond-date field the bridge emits is covered by an explicit assertion
against ``^\\d{8}$`` so a regression in any one place fails a named test
instead of a generic schema failure.
"""

from __future__ import annotations

import re
from datetime import date, datetime

import pytest

from app.utils.dates import (
    KNOWN_DATE_FIELDS,
    InvalidDate,
    coerce_field_value,
    parse_yyyymmdd_strict,
    safe_to_yyyymmdd,
    to_yyyymmdd,
)

YYYYMMDD = re.compile(r"^\d{8}$")


# ---------------------------------------------------------------------------
# Helper behaviour
# ---------------------------------------------------------------------------


class TestToYyyymmdd:
    def test_accepts_date(self):
        assert to_yyyymmdd(date(2025, 4, 19)) == "20250419"

    def test_accepts_datetime(self):
        assert to_yyyymmdd(datetime(2025, 4, 19, 13, 30)) == "20250419"

    def test_accepts_already_canonical_string(self):
        assert to_yyyymmdd("20250419") == "20250419"

    def test_accepts_iso_date_string(self):
        assert to_yyyymmdd("2025-04-19") == "20250419"

    def test_accepts_iso_datetime_string(self):
        assert to_yyyymmdd("2025-04-19T13:30:00") == "20250419"

    def test_rejects_ambiguous_dd_mm_yyyy(self):
        # This is the exact bug class the Explorer fix was guarding
        # against — "01/02/2025" could mean Jan 2 or Feb 1. We refuse.
        with pytest.raises(InvalidDate):
            to_yyyymmdd("01/02/2025")

    def test_rejects_non_date_calendar(self):
        with pytest.raises(InvalidDate):
            to_yyyymmdd("20250230")

    def test_rejects_empty_string(self):
        with pytest.raises(InvalidDate):
            to_yyyymmdd("")

    def test_rejects_none(self):
        with pytest.raises(InvalidDate):
            to_yyyymmdd(None)

    def test_output_always_matches_regex(self):
        for value in [date(2025, 4, 19), "2025-04-19", "20250419", datetime(2000, 1, 1)]:
            assert YYYYMMDD.match(to_yyyymmdd(value))


class TestSafeToYyyymmdd:
    def test_returns_none_for_invalid(self, caplog):
        assert safe_to_yyyymmdd("not a date") is None

    def test_passthrough_none(self):
        assert safe_to_yyyymmdd(None) is None

    def test_coerces_valid(self):
        assert safe_to_yyyymmdd("2025-04-19") == "20250419"


class TestParseStrict:
    @pytest.mark.parametrize(
        "bad",
        ["2025-04-19", "19-04-2025", "20250419T00", "abcdefgh", "", None, 20250419],
    )
    def test_rejects_non_canonical(self, bad):
        with pytest.raises(InvalidDate):
            parse_yyyymmdd_strict(bad)

    def test_accepts_canonical(self):
        assert parse_yyyymmdd_strict("20250419") == date(2025, 4, 19)


# ---------------------------------------------------------------------------
# Field-level coercion — one assertion per bond-date field
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field_name",
    sorted(KNOWN_DATE_FIELDS),
)
def test_known_date_field_is_canonicalised(field_name):
    """Every bond-date field must emit ^\\d{8}$ regardless of upstream type."""
    for upstream in [
        date(2030, 6, 15),
        datetime(2030, 6, 15, 0, 0, 0),
        "2030-06-15",
        "20300615",
    ]:
        out = coerce_field_value(field_name, upstream)
        assert out is not None, f"{field_name} dropped value {upstream!r}"
        assert YYYYMMDD.match(out), f"{field_name} → {out!r} (upstream {upstream!r})"


def test_unknown_field_passes_through():
    # Non-date fields must not be touched.
    assert coerce_field_value("PX_LAST", 123.45) == 123.45
    assert coerce_field_value("NAME", "International Business Machines") == (
        "International Business Machines"
    )


def test_known_date_field_with_unparseable_upstream_returns_none():
    # Rather than leak "01/02/2030" through, we drop it and the client
    # sees null — which its strict parser handles safely.
    assert coerce_field_value("MATURITY", "01/02/2030") is None


# ---------------------------------------------------------------------------
# Schema-level validation — request side
# ---------------------------------------------------------------------------


def test_historical_request_accepts_yyyymmdd():
    from app.models.schemas import HistoricalDataRequest

    req = HistoricalDataRequest(
        securities=["IBM US Equity"],
        fields=["PX_LAST"],
        start_date="20250101",
        end_date="20250419",
    )
    assert req.start_date == "20250101"
    assert req.end_date == "20250419"


@pytest.mark.parametrize("bad", ["2025-01-01", "01/01/2025", "20250101T00", "2025010", "abcdefgh"])
def test_historical_request_rejects_non_yyyymmdd(bad):
    from pydantic import ValidationError

    from app.models.schemas import HistoricalDataRequest

    with pytest.raises(ValidationError):
        HistoricalDataRequest(
            securities=["IBM US Equity"],
            fields=["PX_LAST"],
            start_date=bad,
            end_date="20250419",
        )


def test_reference_request_rejects_bad_date_override():
    from pydantic import ValidationError

    from app.models.schemas import ReferenceDataRequest

    with pytest.raises(ValidationError):
        ReferenceDataRequest(
            securities=["IBM US Equity"],
            fields=["PX_LAST"],
            overrides={"ASOF_DATE": "2025-04-19"},
        )


def test_reference_request_accepts_good_date_override():
    from app.models.schemas import ReferenceDataRequest

    req = ReferenceDataRequest(
        securities=["IBM US Equity"],
        fields=["PX_LAST"],
        overrides={"ASOF_DATE": "20250419"},
    )
    assert req.overrides == {"ASOF_DATE": "20250419"}


# ---------------------------------------------------------------------------
# Schema-level serialisation — response side
# ---------------------------------------------------------------------------


def test_security_data_canonicalises_known_date_fields():
    from app.models.schemas import SecurityData

    sd = SecurityData(
        security="XS1234567890 Corp",
        fields={
            "PX_LAST": 100.25,
            "MATURITY": date(2032, 3, 15),
            "ISSUE_DT": "2022-03-15",
            "SETTLE_DT": datetime(2025, 4, 21, 0, 0),
            "FIRST_CPN_DT": "20220915",
        },
    )
    for field in ("MATURITY", "ISSUE_DT", "SETTLE_DT", "FIRST_CPN_DT"):
        assert YYYYMMDD.match(sd.fields[field]), f"{field} = {sd.fields[field]!r}"
    assert sd.fields["PX_LAST"] == 100.25


def test_historical_bar_date_is_yyyymmdd():
    from app.models.schemas import HistoricalBar

    bar = HistoricalBar(date="20250419", fields={"PX_LAST": 123.45})
    assert YYYYMMDD.match(bar.date)


def test_historical_bar_rejects_iso_date():
    from pydantic import ValidationError

    from app.models.schemas import HistoricalBar

    with pytest.raises(ValidationError):
        HistoricalBar(date="2025-04-19", fields={})


def test_historical_bar_accepts_null_date():
    from app.models.schemas import HistoricalBar

    bar = HistoricalBar(date=None, fields={})
    assert bar.date is None


# ---------------------------------------------------------------------------
# End-to-end: bad request → HTTP 400 (not 422)
# ---------------------------------------------------------------------------


class _NoopBloombergClient:
    """Test double used in place of the blpapi-backed client."""

    _session = None

    def start(self):
        pass

    def stop(self):
        pass

    def open_service(self, _name):
        from app.bloomberg.client import BloombergError

        raise BloombergError("test stub: bloomberg unavailable")

    def send_request(self, _request):
        from app.bloomberg.client import BloombergError

        raise BloombergError("test stub: bloomberg unavailable")


def _patch_bloomberg(monkeypatch):
    from app.bloomberg import client as bb_client
    from app.bloomberg import service as bb_service

    stub = _NoopBloombergClient()
    monkeypatch.setattr(bb_client, "get_client", lambda: stub)
    monkeypatch.setattr(bb_service, "get_client", lambda: stub)


def test_bad_date_on_request_returns_400(monkeypatch):
    from fastapi.testclient import TestClient

    _patch_bloomberg(monkeypatch)

    from app.main import create_app

    app = create_app()
    with TestClient(app) as tc:
        resp = tc.post(
            "/historical",
            json={
                "securities": ["IBM US Equity"],
                "fields": ["PX_LAST"],
                "start_date": "2025-01-01",
                "end_date": "20250419",
            },
        )
        assert resp.status_code == 400, resp.text
        body = resp.json()
        assert "YYYYMMDD" in body["detail"]


def test_bad_date_in_override_returns_400(monkeypatch):
    from fastapi.testclient import TestClient

    _patch_bloomberg(monkeypatch)

    from app.main import create_app

    app = create_app()
    with TestClient(app) as tc:
        resp = tc.post(
            "/reference",
            json={
                "securities": ["IBM US Equity"],
                "fields": ["PX_LAST"],
                "overrides": {"ASOF_DATE": "19/04/2025"},
            },
        )
        assert resp.status_code == 400, resp.text
        assert "YYYYMMDD" in resp.json()["detail"]


def test_valid_date_on_request_passes_schema(monkeypatch):
    """Body parses cleanly; we expect a 502 from the stubbed backend,
    confirming the request got past validation."""
    from fastapi.testclient import TestClient

    _patch_bloomberg(monkeypatch)

    from app.main import create_app

    app = create_app()
    with TestClient(app) as tc:
        resp = tc.post(
            "/historical",
            json={
                "securities": ["IBM US Equity"],
                "fields": ["PX_LAST"],
                "start_date": "20250101",
                "end_date": "20250419",
            },
        )
        assert resp.status_code == 502, resp.text  # reached the backend
