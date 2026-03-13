"""
SCADA data REST endpoints.

GET  /api/v1/scada/{turbine_id}/readings   — paginated time-series readings
GET  /api/v1/scada/{turbine_id}/latest     — most recent reading
POST /api/v1/scada/ingest                  — ingest a batch of readings
GET  /api/v1/scada/{turbine_id}/stats      — summary statistics for a window
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from shared.models.domain import SCADAReading
from shared.utils.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


# ── Request / Response schemas ────────────────────────────────

class ReadingsResponse(BaseModel):
    turbine_id: str
    count: int
    start: datetime
    end: datetime
    readings: List[SCADAReading]


class IngestRequest(BaseModel):
    readings: List[SCADAReading]
    source: str = "api"


class IngestResponse(BaseModel):
    accepted: int
    rejected: int
    message: str


class SignalStats(BaseModel):
    turbine_id: str
    signal: str
    period_start: datetime
    period_end: datetime
    count: int
    mean: Optional[float]
    std: Optional[float]
    min: Optional[float]
    p25: Optional[float]
    p50: Optional[float]
    p75: Optional[float]
    max: Optional[float]


# ── Endpoints ─────────────────────────────────────────────────

@router.get("/{turbine_id}/readings", response_model=ReadingsResponse)
async def get_readings(
    turbine_id: str,
    start: Optional[datetime] = Query(
        default=None,
        description="ISO8601 start time (UTC). Defaults to 24h ago."
    ),
    end: Optional[datetime] = Query(
        default=None,
        description="ISO8601 end time (UTC). Defaults to now."
    ),
    limit: int = Query(default=1000, le=10000, ge=1),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve paginated SCADA readings for a turbine."""
    now = datetime.now(tz=timezone.utc)
    if start is None:
        start = now - timedelta(hours=24)
    if end is None:
        end = now

    turbine_id = turbine_id.upper()

    query = text("""
        SELECT
            turbine_id, timestamp,
            wind_speed_ms, wind_direction_deg,
            active_power_kw, reactive_power_kvar,
            rotor_rpm, pitch_angle_deg, nacelle_direction_deg,
            temp_ambient_c, temp_nacelle_c,
            temp_gearbox_bearing_c, temp_generator_bearing_c,
            availability_flag
        FROM scada_readings
        WHERE turbine_id = :turbine_id
          AND timestamp BETWEEN :start AND :end
        ORDER BY timestamp ASC
        LIMIT :limit OFFSET :offset
    """)

    result = await db.execute(
        query,
        {
            "turbine_id": turbine_id,
            "start": start,
            "end": end,
            "limit": limit,
            "offset": offset,
        },
    )
    rows = result.mappings().all()

    if not rows:
        logger.info("No readings found", turbine=turbine_id, start=start, end=end)

    readings = [SCADAReading(**dict(row)) for row in rows]
    return ReadingsResponse(
        turbine_id=turbine_id,
        count=len(readings),
        start=start,
        end=end,
        readings=readings,
    )


@router.get("/{turbine_id}/latest", response_model=Optional[SCADAReading])
async def get_latest_reading(
    turbine_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get the most recent SCADA reading for a turbine."""
    turbine_id = turbine_id.upper()
    result = await db.execute(
        text("""
            SELECT * FROM scada_readings
            WHERE turbine_id = :turbine_id
            ORDER BY timestamp DESC
            LIMIT 1
        """),
        {"turbine_id": turbine_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail=f"No readings for turbine {turbine_id}")
    return SCADAReading(**dict(row))


@router.post("/ingest", response_model=IngestResponse)
async def ingest_readings(
    payload: IngestRequest,
    db: AsyncSession = Depends(get_db),
):
    """Batch-ingest SCADA readings into TimescaleDB."""
    accepted = 0
    rejected = 0

    for reading in payload.readings:
        try:
            await db.execute(
                text("""
                    INSERT INTO scada_readings (
                        turbine_id, timestamp,
                        wind_speed_ms, wind_direction_deg, wind_speed_std,
                        active_power_kw, reactive_power_kvar, power_setpoint_kw,
                        rotor_rpm, pitch_angle_deg, nacelle_direction_deg,
                        temp_ambient_c, temp_nacelle_c,
                        temp_gearbox_bearing_c, temp_generator_bearing_c,
                        grid_voltage_v, grid_frequency_hz,
                        availability_flag, status_code
                    ) VALUES (
                        :turbine_id, :timestamp,
                        :wind_speed_ms, :wind_direction_deg, :wind_speed_std,
                        :active_power_kw, :reactive_power_kvar, :power_setpoint_kw,
                        :rotor_rpm, :pitch_angle_deg, :nacelle_direction_deg,
                        :temp_ambient_c, :temp_nacelle_c,
                        :temp_gearbox_bearing_c, :temp_generator_bearing_c,
                        :grid_voltage_v, :grid_frequency_hz,
                        :availability_flag, :status_code
                    )
                    ON CONFLICT (turbine_id, timestamp) DO NOTHING
                """),
                reading.model_dump(),
            )
            accepted += 1
        except Exception as exc:
            logger.warning("Failed to insert reading", error=str(exc))
            rejected += 1

    await db.commit()
    logger.info("Ingest complete", accepted=accepted, rejected=rejected, source=payload.source)
    return IngestResponse(
        accepted=accepted,
        rejected=rejected,
        message=f"Ingested {accepted} readings, rejected {rejected}",
    )


@router.get("/{turbine_id}/stats", response_model=List[SignalStats])
async def get_signal_stats(
    turbine_id: str,
    signals: List[str] = Query(
        default=["wind_speed_ms", "active_power_kw", "temp_gearbox_bearing_c"],
        description="Signal names to compute stats for",
    ),
    hours: int = Query(default=24, ge=1, le=8760),
    db: AsyncSession = Depends(get_db),
):
    """Compute descriptive statistics for specified signals over a time window."""
    turbine_id = turbine_id.upper()
    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(hours=hours)

    # Hardcoded SQL fragments — never interpolate user input directly into SQL.
    # This lookup maps each allowed signal name to its exact, pre-approved SQL column
    # identifier, eliminating any SQL injection risk even if the allowlist check above
    # were somehow bypassed.
    SIGNAL_SQL: dict = {
        "wind_speed_ms":           "wind_speed_ms",
        "active_power_kw":         "active_power_kw",
        "rotor_rpm":               "rotor_rpm",
        "pitch_angle_deg":         "pitch_angle_deg",
        "temp_ambient_c":          "temp_ambient_c",
        "temp_nacelle_c":          "temp_nacelle_c",
        "temp_gearbox_bearing_c":  "temp_gearbox_bearing_c",
        "temp_generator_bearing_c":"temp_generator_bearing_c",
        "reactive_power_kvar":     "reactive_power_kvar",
    }
    signals = [s for s in signals if s in SIGNAL_SQL]

    results = []
    for signal in signals:
        col = SIGNAL_SQL[signal]   # safe: value comes from the dict above, not user input
        result = await db.execute(
            text(f"""
                SELECT
                    COUNT(*) as count,
                    AVG({col}) as mean,
                    STDDEV({col}) as std,
                    MIN({col}) as min,
                    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY {col}) as p25,
                    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY {col}) as p50,
                    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY {col}) as p75,
                    MAX({col}) as max
                FROM scada_readings
                WHERE turbine_id = :turbine_id
                  AND timestamp BETWEEN :start AND :end
                  AND {col} IS NOT NULL
            """),
            {"turbine_id": turbine_id, "start": start, "end": end},
        )
        row = result.mappings().first()
        if row and row["count"]:
            results.append(
                SignalStats(
                    turbine_id=turbine_id,
                    signal=signal,
                    period_start=start,
                    period_end=end,
                    **{k: (float(v) if v is not None else None) for k, v in row.items()},
                )
            )

    return results
