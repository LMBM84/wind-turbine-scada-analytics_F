"""
Core Pydantic domain models shared across all services.
These represent the canonical data contracts for SCADA readings, turbines, and anomalies.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ─────────────────────────────────────────────────────────────
#  Enumerations
# ─────────────────────────────────────────────────────────────

class TurbineStatus(str, Enum):
    OPERATING = "operating"
    CURTAILED = "curtailed"
    MAINTENANCE = "maintenance"
    FAULT = "fault"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class AnomalyType(str, Enum):
    POWER_CURVE = "power_curve_deviation"
    TEMPERATURE = "temperature_anomaly"
    VIBRATION = "vibration_anomaly"
    ELECTRICAL = "electrical_anomaly"
    ROTOR = "rotor_anomaly"
    GEARBOX = "gearbox_anomaly"
    GENERATOR = "generator_anomaly"
    UNKNOWN = "unknown"


class AnomalySeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ─────────────────────────────────────────────────────────────
#  Core SCADA Reading
# ─────────────────────────────────────────────────────────────

class SCADAReading(BaseModel):
    """A single 10-minute SCADA interval for one turbine."""

    turbine_id: str = Field(..., description="Turbine identifier, e.g. 'K1'")
    timestamp: datetime = Field(..., description="Interval start time (UTC)")

    # Wind
    wind_speed_ms: Optional[float] = Field(None, ge=0, le=50, description="Wind speed (m/s)")
    wind_direction_deg: Optional[float] = Field(None, ge=0, lt=360, description="Wind direction (°)")
    wind_speed_std: Optional[float] = Field(None, ge=0, description="Wind speed std dev")

    # Power
    active_power_kw: Optional[float] = Field(None, description="Active power output (kW)")
    reactive_power_kvar: Optional[float] = Field(None, description="Reactive power (kVAR)")
    power_setpoint_kw: Optional[float] = Field(None, ge=0)

    # Mechanical
    rotor_rpm: Optional[float] = Field(None, ge=0, le=30)
    pitch_angle_deg: Optional[float] = Field(None, ge=-5, le=90)
    nacelle_direction_deg: Optional[float] = Field(None, ge=0, lt=360)

    # Temperatures (°C)
    temp_ambient_c: Optional[float] = Field(None, ge=-40, le=60)
    temp_nacelle_c: Optional[float] = Field(None, ge=-20, le=100)
    temp_gearbox_bearing_c: Optional[float] = Field(None, ge=-20, le=150)
    temp_generator_bearing_c: Optional[float] = Field(None, ge=-20, le=150)
    temp_main_bearing_c: Optional[float] = Field(None, ge=-20, le=150)

    # Grid
    grid_voltage_v: Optional[float] = Field(None, ge=0)
    grid_frequency_hz: Optional[float] = Field(None, ge=45, le=65)

    # Status
    status_code: Optional[int] = None
    availability_flag: bool = True

    @field_validator("turbine_id")
    @classmethod
    def validate_turbine_id(cls, v: str) -> str:
        return v.strip().upper()

    @model_validator(mode="after")
    def validate_power_vs_wind(self) -> "SCADAReading":
        """
        Basic physics sanity check: flag positive power output below cut-in wind speed.
        We log a warning rather than rejecting the reading — the turbine could
        legitimately be in motoring/reactive-compensation mode.
        """
        import warnings as _warnings
        if (
            self.active_power_kw is not None
            and self.wind_speed_ms is not None
            and self.active_power_kw > 0
            and self.wind_speed_ms < 2.5  # cut-in is typically ~3 m/s
        ):
            _warnings.warn(
                f"Turbine {self.turbine_id} reports {self.active_power_kw:.1f} kW "
                f"at wind speed {self.wind_speed_ms:.1f} m/s (below cut-in). "
                "This may indicate motoring mode or a sensor fault.",
                UserWarning,
                stacklevel=2,
            )
        return self

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


# ─────────────────────────────────────────────────────────────
#  Turbine Metadata
# ─────────────────────────────────────────────────────────────

class TurbineMetadata(BaseModel):
    turbine_id: str
    farm_id: str
    name: str
    manufacturer: str = "Senvion"
    model: str = "MM92"
    rated_power_kw: float = 2050.0
    rotor_diameter_m: float = 92.0
    hub_height_m: float = 80.0
    latitude: float
    longitude: float
    commissioning_date: Optional[datetime] = None
    status: TurbineStatus = TurbineStatus.UNKNOWN


# ─────────────────────────────────────────────────────────────
#  Power Curve
# ─────────────────────────────────────────────────────────────

class PowerCurvePoint(BaseModel):
    wind_speed_ms: float
    power_kw: float
    count: int = 0
    power_std: float = 0.0
    p10: Optional[float] = None
    p90: Optional[float] = None


class PowerCurveResult(BaseModel):
    turbine_id: str
    computed_at: datetime
    method: str = "IEC-61400-12-1"
    wind_speed_bins: List[float]
    rated_power_kw: float
    cut_in_ms: float
    cut_out_ms: float
    capacity_factor: float
    annual_energy_production_mwh: Optional[float] = None
    points: List[PowerCurvePoint]


# ─────────────────────────────────────────────────────────────
#  Anomaly
# ─────────────────────────────────────────────────────────────

class AnomalyEvent(BaseModel):
    anomaly_id: str
    turbine_id: str
    detected_at: datetime
    interval_start: datetime
    anomaly_type: AnomalyType
    severity: AnomalySeverity
    score: float = Field(..., ge=0.0, le=1.0, description="Normalised anomaly score")
    model_name: str
    features_used: List[str] = Field(default_factory=list)
    shap_values: Optional[Dict[str, float]] = None
    description: str = ""
    acknowledged: bool = False
    resolved: bool = False

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


# ─────────────────────────────────────────────────────────────
#  KPI Snapshot
# ─────────────────────────────────────────────────────────────

class TurbineKPI(BaseModel):
    turbine_id: str
    period_start: datetime
    period_end: datetime
    availability_pct: float = Field(ge=0, le=100)
    capacity_factor_pct: float = Field(ge=0, le=100)
    mean_wind_speed_ms: float
    total_energy_kwh: float
    p50_power_kw: float
    anomaly_count: int = 0
    data_completeness_pct: float = Field(ge=0, le=100)
