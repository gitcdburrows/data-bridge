"""/instruments endpoints — ticker search / lookup."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from app.bloomberg.client import BloombergError
from app.bloomberg.service import BloombergService
from app.models.schemas import (
    InstrumentLookupRequest,
    InstrumentLookupResponse,
    InstrumentMatch,
)

router = APIRouter(prefix="/instruments", tags=["instruments"])


@router.post("/lookup", response_model=InstrumentLookupResponse)
async def lookup_instrument(payload: InstrumentLookupRequest) -> InstrumentLookupResponse:
    svc = BloombergService()
    try:
        matches = await run_in_threadpool(
            svc.instrument_lookup,
            payload.query,
            payload.max_results,
            payload.yellow_key_filter,
        )
    except BloombergError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return InstrumentLookupResponse(matches=[InstrumentMatch(**m) for m in matches])
