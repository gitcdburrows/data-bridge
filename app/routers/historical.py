"""/historical endpoints — end-of-period time series."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from app.bloomberg.client import BloombergError
from app.bloomberg.service import BloombergService
from app.models.schemas import (
    HistoricalBar,
    HistoricalDataRequest,
    HistoricalDataResponse,
    HistoricalSecurityData,
)

router = APIRouter(prefix="/historical", tags=["historical"])


@router.post("", response_model=HistoricalDataResponse)
async def get_historical_data(payload: HistoricalDataRequest) -> HistoricalDataResponse:
    svc = BloombergService()
    try:
        rows = await run_in_threadpool(
            svc.historical_data,
            securities=payload.securities,
            fields=payload.fields,
            start_date=payload.start_date,   # already validated YYYYMMDD
            end_date=payload.end_date,       # already validated YYYYMMDD
            periodicity=payload.periodicity,
            currency=payload.currency,
            non_trading_day_fill_option=payload.non_trading_day_fill_option,
            non_trading_day_fill_method=payload.non_trading_day_fill_method,
            max_data_points=payload.max_data_points,
            overrides=payload.overrides,
        )
    except BloombergError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return HistoricalDataResponse(
        data=[
            HistoricalSecurityData(
                security=row["security"],
                security_error=row["security_error"],
                bars=[HistoricalBar(**bar) for bar in row["bars"]],
            )
            for row in rows
        ]
    )
