"""/intraday endpoints — intraday OHLCV bars."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool

from app.bloomberg.client import BloombergError
from app.bloomberg.service import BloombergService
from app.models.schemas import IntradayBar, IntradayBarRequest, IntradayBarResponse
from app.security import require_api_key

router = APIRouter(
    prefix="/intraday",
    tags=["intraday"],
    dependencies=[Depends(require_api_key)],
)


@router.post("/bars", response_model=IntradayBarResponse)
async def get_intraday_bars(payload: IntradayBarRequest) -> IntradayBarResponse:
    svc = BloombergService()
    try:
        bars = await run_in_threadpool(
            svc.intraday_bars,
            security=payload.security,
            event_type=payload.event_type,
            interval=payload.interval,
            start_datetime=payload.start_datetime,
            end_datetime=payload.end_datetime,
            gap_fill_initial_bar=payload.gap_fill_initial_bar,
            adjustment_normal=payload.adjustment_normal,
            adjustment_abnormal=payload.adjustment_abnormal,
            adjustment_split=payload.adjustment_split,
            adjustment_follow_dpdf=payload.adjustment_follow_dpdf,
        )
    except BloombergError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return IntradayBarResponse(
        security=payload.security,
        bars=[IntradayBar(**bar) for bar in bars],
    )
