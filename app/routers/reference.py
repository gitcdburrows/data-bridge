"""/reference endpoints — snapshots for one or more securities."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from app.bloomberg.client import BloombergError
from app.bloomberg.service import BloombergService
from app.models.schemas import (
    ReferenceDataRequest,
    ReferenceDataResponse,
    SecurityData,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reference", tags=["reference"])


@router.post("", response_model=ReferenceDataResponse)
async def get_reference_data(payload: ReferenceDataRequest):
    try:
        svc = BloombergService()
        rows = await run_in_threadpool(
            svc.reference_data,
            payload.securities,
            payload.fields,
            payload.overrides,
        )
        return ReferenceDataResponse(data=[SecurityData(**row) for row in rows])
    except BloombergError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - surface the real error with CORS
        # See app/routers/historical.py: catch-and-return keeps the CORS
        # headers on a 500 and reports the actual exception instead of an
        # opaque "blocked by CORS" in the browser.
        logger.exception("Unhandled error in POST /reference")
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal error while handling the reference request.",
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
