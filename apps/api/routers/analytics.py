"""
Analytics endpoints — power curves, KPIs, production statistics.

GET  /api/v1/analytics/{turbine_id}/power-curve    — IEC 61400-12-1 power curve
GET  /api/v1/analytics/{turbine_id}/kpis           — operational KPIs
GET  /api/v1/analytics/fleet/overview              — multi-turbine fleet summary
GET  /api/v1/analytics/{turbine_id}/production     — hourly/daily production rollup
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from analytics.power_curve.iec_power_curve import compute_power_curve
from analytics.anomaly.detectors import compute_kpis
from shared.models.domain import PowerCurveResult, TurbineKPI
from shared.utils.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


class FleetSummary(BaseModel):
    computed_at: datetime
    total_turbines: int
    operating: int
    total_power_kw: float
    mean_wind_speed_ms: float
    fleet_capacity_factor_pct: float
    turbines: List[Dict[str, Any]]


class ProductionRollup(BaseModel):
    turbine_id: str
    granularity: str
    buckets: List[Dict[str, Any]]


# ── Power Curve ───────────────────────────────────────────────

@router.get("/{turbine_id}/power-curve", response_model=PowerCurveResult)
async def get_power_curve(
    turbine_id: str,
    months: int = Query(default=12, ge=1, le=60, description="Trailing months of data"),
    density_correction: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
):
    """
    Compute IEC 61400-12-1 power curve from stored SCADA data.
    Uses bin-averaging with optional air density correction.
    """
    turbine_id = turbine_id.upper()
    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(days=months * 30)

    result = await db.execute(
        text("""
            SELECT timestamp, wind_speed_ms, active_power_kw,
                   temp_ambient_c, availability_flag
            FROM scada_readings
            WHERE turbine_id = :turbine_id
              AND timestamp BETWEEN :start AND :end
              AND wind_speed_ms IS NOT NULL
              AND active_power_kw IS NOT NULL
            ORDER BY timestamp ASC
        """),
        {"turbine_id": turbine_id, "start": start, "end": end},
    )
    rows = result.mappings().all()

    if len(rows) < 100:
        raise HTTPException(
            status_code=422,
            detail=f"Insufficient data for power curve ({len(rows)} points, need ≥ 100)"
        )

    df = pd.DataFrame([dict(r) for r in rows])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp")

    curve = compute_power_curve(
        df,
        turbine_id=turbine_id,
        density_correction=density_correction,
    )
    return curve


# ── KPIs ──────────────────────────────────────────────────────

@router.get("/{turbine_id}/kpis", response_model=Dict[str, Any])
async def get_kpis(
    turbine_id: str,
    hours: int = Query(default=720, ge=1, le=8760, description="Window in hours (720 = 30 days)"),
    db: AsyncSession = Depends(get_db),
):
    """Return operational KPIs for a turbine over a rolling window."""
    turbine_id = turbine_id.upper()
    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(hours=hours)

    result = await db.execute(
        text("""
            SELECT wind_speed_ms, active_power_kw, availability_flag,
                   temp_gearbox_bearing_c, temp_generator_bearing_c
            FROM scada_readings
            WHERE turbine_id = :turbine_id
              AND timestamp BETWEEN :start AND :end
        """),
        {"turbine_id": turbine_id, "start": start, "end": end},
    )
    rows = result.mappings().all()

    if not rows:
        raise HTTPException(status_code=404, detail=f"No data for turbine {turbine_id}")

    df = pd.DataFrame([dict(r) for r in rows])
    kpis = compute_kpis(df, turbine_id)
    kpis["period_start"] = start.isoformat()
    kpis["period_end"] = end.isoformat()
    return kpis


# ── Fleet Overview ────────────────────────────────────────────

@router.get("/fleet/overview", response_model=FleetSummary)
async def get_fleet_overview(db: AsyncSession = Depends(get_db)):
    """
    Real-time fleet snapshot: latest reading per turbine, aggregate power, wind.
    """
    result = await db.execute(text("""
        SELECT DISTINCT ON (turbine_id)
            turbine_id,
            timestamp,
            wind_speed_ms,
            active_power_kw,
            availability_flag,
            temp_nacelle_c
        FROM scada_readings
        WHERE timestamp > NOW() - INTERVAL '2 hours'
        ORDER BY turbine_id, timestamp DESC
    """))
    rows = result.mappings().all()

    turbines = [dict(r) for r in rows]
    operating = sum(1 for t in turbines if t.get("availability_flag"))
    total_power = sum(t.get("active_power_kw") or 0 for t in turbines)
    mean_ws = (
        sum(t.get("wind_speed_ms") or 0 for t in turbines) / len(turbines)
        if turbines else 0.0
    )
    rated_fleet = len(turbines) * 2050.0
    cf = (total_power / rated_fleet * 100) if rated_fleet > 0 else 0.0

    return FleetSummary(
        computed_at=datetime.now(tz=timezone.utc),
        total_turbines=len(turbines),
        operating=operating,
        total_power_kw=round(total_power, 1),
        mean_wind_speed_ms=round(mean_ws, 2),
        fleet_capacity_factor_pct=round(cf, 2),
        turbines=turbines,
    )


# ── Production Rollup ─────────────────────────────────────────

@router.get("/{turbine_id}/production", response_model=ProductionRollup)
async def get_production_rollup(
    turbine_id: str,
    granularity: str = Query(default="1 hour", regex=r"^(10 minutes|1 hour|1 day)$"),
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """
    Aggregated power production bucketed by time granularity.
    Uses TimescaleDB time_bucket for efficient rollups.
    """
    turbine_id = turbine_id.upper()
    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(days=days)

    result = await db.execute(
        text(f"""
            SELECT
                time_bucket('{granularity}', timestamp) AS bucket,
                AVG(wind_speed_ms) AS avg_wind_speed,
                AVG(active_power_kw) AS avg_power_kw,
                SUM(active_power_kw * 10.0 / 60.0) AS energy_kwh,
                COUNT(*) AS intervals,
                AVG(availability_flag::int) AS availability
            FROM scada_readings
            WHERE turbine_id = :turbine_id
              AND timestamp BETWEEN :start AND :end
            GROUP BY bucket
            ORDER BY bucket ASC
        """),
        {"turbine_id": turbine_id, "start": start, "end": end},
    )
    buckets = [
        {k: (float(v) if isinstance(v, (int, float)) else str(v) if v else None)
         for k, v in dict(row).items()}
        for row in result.mappings().all()
    ]

    return ProductionRollup(
        turbine_id=turbine_id,
        granularity=granularity,
        buckets=buckets,
    )
