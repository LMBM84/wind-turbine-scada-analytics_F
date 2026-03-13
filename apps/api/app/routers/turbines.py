"""Turbine metadata endpoints."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from shared.models.domain import TurbineMetadata
from shared.utils.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.get("/", response_model=List[TurbineMetadata])
async def list_turbines(db: AsyncSession = Depends(get_db)):
    """List all registered turbines."""
    result = await db.execute(text("SELECT * FROM turbines ORDER BY turbine_id"))
    rows = result.mappings().all()
    return [TurbineMetadata(**dict(r)) for r in rows]


@router.get("/{turbine_id}", response_model=TurbineMetadata)
async def get_turbine(turbine_id: str, db: AsyncSession = Depends(get_db)):
    """Get metadata for a specific turbine."""
    turbine_id = turbine_id.upper()
    result = await db.execute(
        text("SELECT * FROM turbines WHERE turbine_id = :tid"),
        {"tid": turbine_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail=f"Turbine {turbine_id} not found")
    return TurbineMetadata(**dict(row))
