"""/sql endpoints — run queries against the local database."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import SQLAlchemyError

from app.db.engine import DatabaseNotConfigured
from app.db.service import SQLError, SQLService
from app.models.schemas import (
    SQLQueryRequest,
    SQLQueryResponse,
    SQLTableList,
    SQLTableSchema,
)
from app.security import require_api_key

router = APIRouter(
    prefix="/sql",
    tags=["sql"],
    dependencies=[Depends(require_api_key)],
)


def _service() -> SQLService:
    try:
        return SQLService()
    except DatabaseNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/query", response_model=SQLQueryResponse)
async def run_query(payload: SQLQueryRequest) -> SQLQueryResponse:
    svc = _service()
    try:
        result = await run_in_threadpool(
            svc.execute, payload.sql, payload.params, payload.max_rows
        )
    except SQLError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=502, detail=str(exc.__cause__ or exc)) from exc
    return SQLQueryResponse(**result)


@router.get("/tables", response_model=SQLTableList)
async def list_tables(
    schema: Optional[str] = Query(default=None, description="Optional DB schema name."),
) -> SQLTableList:
    svc = _service()
    try:
        result = await run_in_threadpool(svc.list_tables, schema)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=502, detail=str(exc.__cause__ or exc)) from exc
    return SQLTableList(schema=result["schema"], tables=result["tables"], views=result["views"])


@router.get("/tables/{table}", response_model=SQLTableSchema)
async def describe_table(
    table: str,
    schema: Optional[str] = Query(default=None),
) -> SQLTableSchema:
    svc = _service()
    try:
        result = await run_in_threadpool(svc.describe_table, table, schema)
    except SQLError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=502, detail=str(exc.__cause__ or exc)) from exc
    return SQLTableSchema(
        schema=result["schema"], table=result["table"], columns=result["columns"]
    )
