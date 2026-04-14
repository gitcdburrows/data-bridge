"""/reference endpoints — snapshots for one or more securities."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool

from app.bloomberg.client import BloombergError
from app.bloomberg.service import BloombergService
from app.models.schemas import (
    ReferenceDataRequest,
    ReferenceDataResponse,
    SecurityData,
)
from app.security import require_api_key

router = APIRouter(
    prefix="/reference",
    tags=["reference"],
    dependencies=[Depends(require_api_key)],
)


@router.post("", response_model=ReferenceDataResponse)
async def get_reference_data(payload: ReferenceDataRequest) -> ReferenceDataResponse:
    svc = BloombergService()
    try:
        rows = await run_in_threadpool(
            svc.reference_data,
            payload.securities,
            payload.fields,
            payload.overrides,
        )
    except BloombergError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ReferenceDataResponse(data=[SecurityData(**row) for row in rows])
