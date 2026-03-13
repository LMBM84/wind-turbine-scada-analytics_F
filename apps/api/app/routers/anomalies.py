"""
Anomaly detection endpoints.

GET  /api/v1/anomalies/{turbine_id}        — list anomalies for a turbine
GET  /api/v1/anomalies/fleet/active        — active anomalies across all turbines
POST /api/v1/anomalies/{anomaly_id}/ack    — acknowledge an anomaly
POST /api/v1/anomalies/run-detection       — trigger ad-hoc ML detection
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from analytics.anomaly.detectors import IsolationForestDetector, StatisticalDetector
from shared.models.domain import AnomalyEvent, AnomalySeverity
from shared.utils.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


class AnomalyListResponse(BaseModel):
    turbine_id: str
    total: int
    anomalies: List[AnomalyEvent]


class AckResponse(BaseModel):
    anomaly_id: str
    acknowledged: bool


class DetectionRequest(BaseModel):
    turbine_id: str
    hours: int = 24
    model: str = "isolation_forest"
    threshold: float = 0.7


class DetectionResponse(BaseModel):
    turbine_id: str
    anomalies_found: int
    events: List[AnomalyEvent]


@router.get("/fleet/active", response_model=List[AnomalyEvent])
async def get_fleet_active_anomalies(
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Return the most recent unresolved anomalies across the entire fleet."""
    result = await db.execute(
        text("""
            SELECT * FROM anomaly_events
            WHERE resolved = FALSE
            ORDER BY detected_at DESC
            LIMIT :limit
        """),
        {"limit": limit},
    )
    rows = result.mappings().all()
    return [AnomalyEvent(**dict(r)) for r in rows]


@router.get("/{turbine_id}", response_model=AnomalyListResponse)
async def list_anomalies(
    turbine_id: str,
    hours: int = Query(default=168, ge=1, le=8760, description="Window in hours"),
    severity: Optional[AnomalySeverity] = Query(default=None),
    unresolved_only: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
):
    """List anomaly events for a turbine."""
    turbine_id = turbine_id.upper()
    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(hours=hours)

    where_clauses = [
        "turbine_id = :turbine_id",
        "detected_at BETWEEN :start AND :end",
    ]
    params: dict = {"turbine_id": turbine_id, "start": start, "end": end}

    if severity:
        where_clauses.append("severity = :severity")
        params["severity"] = severity.value

    if unresolved_only:
        where_clauses.append("resolved = FALSE")

    where_sql = " AND ".join(where_clauses)

    result = await db.execute(
        text(f"SELECT * FROM anomaly_events WHERE {where_sql} ORDER BY detected_at DESC"),
        params,
    )
    rows = result.mappings().all()
    events = [AnomalyEvent(**dict(r)) for r in rows]

    return AnomalyListResponse(turbine_id=turbine_id, total=len(events), anomalies=events)




@router.post("/{anomaly_id}/ack", response_model=AckResponse)
async def acknowledge_anomaly(
    anomaly_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Mark an anomaly as acknowledged."""
    await db.execute(
        text("""
            UPDATE anomaly_events
            SET acknowledged = TRUE
            WHERE anomaly_id = :anomaly_id
        """),
        {"anomaly_id": anomaly_id},
    )
    await db.commit()
    return AckResponse(anomaly_id=anomaly_id, acknowledged=True)


@router.post("/run-detection", response_model=DetectionResponse)
async def run_detection(
    request: DetectionRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger ML anomaly detection on recent SCADA data.
    Uses the last 30 days to fit the model, scores the requested window.
    """
    turbine_id = request.turbine_id.upper()
    now = datetime.now(tz=timezone.utc)
    score_start = now - timedelta(hours=request.hours)
    train_start = now - timedelta(days=30)

    # Fetch training data
    train_result = await db.execute(
        text("""
            SELECT timestamp, wind_speed_ms, active_power_kw, rotor_rpm,
                   pitch_angle_deg, temp_gearbox_bearing_c, temp_generator_bearing_c
            FROM scada_readings
            WHERE turbine_id = :tid AND timestamp BETWEEN :start AND :end
            ORDER BY timestamp
        """),
        {"tid": turbine_id, "start": train_start, "end": now},
    )
    train_rows = train_result.mappings().all()

    if len(train_rows) < 200:
        return DetectionResponse(
            turbine_id=turbine_id,
            anomalies_found=0,
            events=[],
        )

    train_df = pd.DataFrame([dict(r) for r in train_rows])
    train_df["timestamp"] = pd.to_datetime(train_df["timestamp"], utc=True)
    train_df = train_df.set_index("timestamp")

    score_df = train_df[train_df.index >= pd.Timestamp(score_start, tz="UTC")]

    # Fit and detect
    detector = IsolationForestDetector(contamination=0.02)
    detector.fit(train_df)
    events = detector.to_anomaly_events(score_df, turbine_id, threshold=request.threshold)

    # Persist events in background
    if events:
        background_tasks.add_task(_persist_anomalies, events, db)

    logger.info("Detection complete", turbine=turbine_id, found=len(events))
    return DetectionResponse(
        turbine_id=turbine_id,
        anomalies_found=len(events),
        events=events,
    )


async def _persist_anomalies(events: List[AnomalyEvent], db: AsyncSession) -> None:
    """Background task to write detected anomalies to the database."""
    for event in events:
        try:
            await db.execute(
                text("""
                    INSERT INTO anomaly_events
                    (anomaly_id, turbine_id, detected_at, interval_start,
                     anomaly_type, severity, score, model_name, description)
                    VALUES
                    (:anomaly_id, :turbine_id, :detected_at, :interval_start,
                     :anomaly_type, :severity, :score, :model_name, :description)
                    ON CONFLICT (anomaly_id) DO NOTHING
                """),
                event.model_dump(exclude={"shap_values", "features_used"}),
            )
        except Exception as exc:
            logger.error("Failed to persist anomaly", error=str(exc))
    await db.commit()
