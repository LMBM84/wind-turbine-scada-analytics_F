"""
Operational KPI computations for wind turbine SCADA data.

Provides compute_kpis() which derives standard wind-farm performance indicators
from a tidy SCADA DataFrame.  Re-exported from analytics.anomaly.detectors for
backwards compatibility.
"""
from __future__ import annotations

from typing import Dict

import pandas as pd

from shared.utils.logging import get_logger

logger = get_logger(__name__)

# Features expected in a typical SCADA DataFrame
MULTIVARIATE_FEATURES = [
    "wind_speed_ms",
    "active_power_kw",
    "rotor_rpm",
    "temp_gearbox_bearing_c",
    "temp_generator_bearing_c",
    "temp_main_bearing_c",
    "pitch_angle_deg",
]

# Default rated power for Kelmarsh MM92 turbines
MM92_RATED_POWER_KW = 2050.0


def compute_kpis(
    df: pd.DataFrame,
    turbine_id: str,
    interval_minutes: int = 10,
    rated_power_kw: float = MM92_RATED_POWER_KW,
) -> Dict:
    """
    Compute operational KPIs from a SCADA DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with SCADA columns (wind_speed_ms, active_power_kw, etc.)
    turbine_id : str
        Turbine identifier — included verbatim in the returned dict.
    interval_minutes : int
        Duration of each row's time interval (default 10 min for SCADA).
    rated_power_kw : float
        Turbine rated power used to compute capacity factor.

    Returns
    -------
    dict
        Keys: turbine_id, total_intervals, hours, total_energy_kwh,
        capacity_factor_pct, p50_power_kw, availability_pct,
        mean_wind_speed_ms, data_completeness_pct.
    """
    total_intervals = len(df)
    hours = total_intervals * interval_minutes / 60.0

    result: Dict = {
        "turbine_id": turbine_id,
        "total_intervals": total_intervals,
        "hours": round(hours, 2),
    }

    if "active_power_kw" in df.columns:
        power = df["active_power_kw"].clip(lower=0)
        result["total_energy_kwh"] = round(float(power.mean() * hours), 1)
        result["capacity_factor_pct"] = round(float(power.mean() / rated_power_kw * 100), 2)
        result["p50_power_kw"] = round(float(power.median()), 1)

    if "availability_flag" in df.columns:
        result["availability_pct"] = round(
            float(df["availability_flag"].mean() * 100), 2
        )

    if "wind_speed_ms" in df.columns:
        result["mean_wind_speed_ms"] = round(float(df["wind_speed_ms"].mean()), 2)

    available_features = [f for f in MULTIVARIATE_FEATURES if f in df.columns]
    if available_features:
        completeness = df[available_features].notna().mean().mean()
        result["data_completeness_pct"] = round(float(completeness * 100), 2)
    else:
        result["data_completeness_pct"] = 0.0

    return result
