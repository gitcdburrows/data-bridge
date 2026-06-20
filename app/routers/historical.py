"""/historical endpoints — end-of-period time series."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from app.bloomberg.client import BloombergError
from app.bloomberg.service import BloombergService
from app.models.schemas import (
    HistoricalBar,
    HistoricalDataRequest,
    HistoricalDataResponse,
    HistoricalSecurityData,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/historical", tags=["historical"])


@router.post("", response_model=HistoricalDataResponse)
async def get_historical_data(payload: HistoricalDataRequest):
    try:
        svc = BloombergService()
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
    except BloombergError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - surface the real error with CORS
        # An unhandled exception would otherwise bubble to Starlette's
        # ServerErrorMiddleware (outside CORSMiddleware), so the browser would
        # only see "blocked by CORS" with no detail. Returning a JSONResponse
        # keeps the CORS headers and tells us exactly what failed; the full
        # traceback goes to the log (data-bridge.log + console).
        logger.exception("Unhandled error in POST /historical")
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal error while handling the historical request.",
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
