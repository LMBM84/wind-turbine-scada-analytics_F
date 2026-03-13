"""
IEC 61400-12-1 compliant power curve analysis.

Implements:
  - Bin-averaging method (0.5 m/s bins, 1–16 m/s)
  - Air density correction
  - Capacity factor calculation
  - AEP estimation via Rayleigh wind speed distribution
  - Reference vs operational curve comparison
"""
from __future__ import annotations

import warnings
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from shared.models.domain import PowerCurvePoint, PowerCurveResult
from shared.utils.logging import get_logger

logger = get_logger(__name__)

# IEC 61400-12-1 standard bin centres (0.5 m/s width, 1.0 to 25.0 m/s)
IEC_BINS = np.arange(1.0, 25.5, 0.5)
IEC_BIN_WIDTH = 0.5

# Standard air density (kg/m³)
STD_AIR_DENSITY = 1.225

# Typical MM92 rated values
MM92_RATED_POWER_KW = 2050.0
MM92_CUT_IN_MS = 3.0
MM92_CUT_OUT_MS = 24.0
MM92_ROTOR_AREA_M2 = np.pi * (92 / 2) ** 2


def compute_power_curve(
    df: pd.DataFrame,
    turbine_id: str,
    wind_col: str = "wind_speed_ms",
    power_col: str = "active_power_kw",
    temp_col: Optional[str] = "temp_ambient_c",
    density_correction: bool = True,
    min_samples_per_bin: int = 3,
    availability_col: Optional[str] = "availability_flag",
    rated_power_kw: float = MM92_RATED_POWER_KW,
) -> PowerCurveResult:
    """
    Compute a power curve following IEC 61400-12-1 bin-averaging method.

    Parameters
    ----------
    df : pd.DataFrame
        SCADA DataFrame with at minimum wind speed and power columns.
    turbine_id : str
        Turbine identifier for the result metadata.
    density_correction : bool
        Apply air density normalisation if ambient temperature is available.
    min_samples_per_bin : int
        Minimum data points required for a bin to be included.

    Returns
    -------
    PowerCurveResult
    """
    logger.info("Computing power curve", turbine=turbine_id, rows=len(df))

    # ── 1. Filter valid records ───────────────────────────────
    mask = df[wind_col].notna() & df[power_col].notna()
    if availability_col and availability_col in df.columns:
        mask &= df[availability_col].astype(bool)
    data = df[mask].copy()

    if len(data) < 100:
        warnings.warn(f"Very few valid samples ({len(data)}) for turbine {turbine_id}")

    # ── 2. Air density correction ─────────────────────────────
    ws = data[wind_col].values.copy()
    if density_correction and temp_col and temp_col in data.columns:
        temp_k = data[temp_col].fillna(15.0).values + 273.15
        rho = 353.049 / temp_k  # approximate from ideal gas law
        ws = ws * (rho / STD_AIR_DENSITY) ** (1 / 3)
        logger.debug("Applied air density correction", turbine=turbine_id)

    data = data.copy()
    data["_ws_corr"] = ws
    data["_power"] = data[power_col].clip(lower=0, upper=rated_power_kw * 1.05)

    # ── 3. Bin assignment ─────────────────────────────────────
    bin_edges = np.append(IEC_BINS - IEC_BIN_WIDTH / 2, IEC_BINS[-1] + IEC_BIN_WIDTH / 2)
    data["_bin"] = pd.cut(
        data["_ws_corr"],
        bins=bin_edges,
        labels=IEC_BINS,
        include_lowest=True,
    )

    # ── 4. Aggregate per bin ──────────────────────────────────
    grouped = data.groupby("_bin", observed=True)["_power"].agg(
        ["mean", "std", "count",
         lambda x: np.percentile(x, 10),
         lambda x: np.percentile(x, 90)]
    )
    grouped.columns = ["power_kw", "power_std", "count", "p10", "p90"]
    grouped.index = grouped.index.astype(float)
    grouped = grouped[grouped["count"] >= min_samples_per_bin]

    # ── 5. Detect cut-in / cut-out ────────────────────────────
    generating = grouped[grouped["power_kw"] > 10.0]
    cut_in = float(generating.index.min()) if not generating.empty else MM92_CUT_IN_MS
    cut_out = float(generating.index.max()) if not generating.empty else MM92_CUT_OUT_MS

    # ── 6. Capacity factor (from available data) ──────────────
    capacity_factor = float(data["_power"].mean() / rated_power_kw)

    # ── 7. AEP from Rayleigh distribution ─────────────────────
    mean_ws = float(data["_ws_corr"].mean())
    aep = _estimate_aep_rayleigh(grouped, mean_ws, rated_power_kw)

    # ── 8. Build result ───────────────────────────────────────
    points = [
        PowerCurvePoint(
            wind_speed_ms=float(ws_bin),
            power_kw=float(row["power_kw"]),
            count=int(row["count"]),
            power_std=float(row["power_std"]) if not np.isnan(row["power_std"]) else 0.0,
            p10=float(row["p10"]),
            p90=float(row["p90"]),
        )
        for ws_bin, row in grouped.iterrows()
    ]

    return PowerCurveResult(
        turbine_id=turbine_id,
        computed_at=datetime.now(tz=timezone.utc),
        method="IEC-61400-12-1",
        wind_speed_bins=list(grouped.index.astype(float)),
        rated_power_kw=rated_power_kw,
        cut_in_ms=cut_in,
        cut_out_ms=cut_out,
        capacity_factor=round(capacity_factor, 4),
        annual_energy_production_mwh=aep,
        points=points,
    )


def compute_power_deviation(
    df: pd.DataFrame,
    reference_curve: PowerCurveResult,
    wind_col: str = "wind_speed_ms",
    power_col: str = "active_power_kw",
) -> pd.Series:
    """
    Compute per-reading power deviation from a reference curve.

    Returns a Series of fractional deviations: (actual - expected) / rated_power.
    Positive values mean higher-than-expected generation; negative means under-performance.
    """
    ref_df = pd.DataFrame(
        [(p.wind_speed_ms, p.power_kw) for p in reference_curve.points],
        columns=["ws", "power"],
    ).set_index("ws").sort_index()

    expected = np.interp(
        df[wind_col].values,
        ref_df.index.values,
        ref_df["power"].values,
        left=0.0,
        right=reference_curve.rated_power_kw,
    )
    expected = np.where(expected < 1.0, np.nan, expected)
    deviation = (df[power_col].values - expected) / reference_curve.rated_power_kw
    return pd.Series(deviation, index=df.index, name="power_deviation")


# ──────────────────────────────────────────────────────────────
#  Internal helpers
# ──────────────────────────────────────────────────────────────

def _estimate_aep_rayleigh(
    curve: pd.DataFrame,
    mean_ws: float,
    rated_power_kw: float,
    hours_per_year: float = 8760.0,
) -> float:
    """
    Estimate Annual Energy Production using a Rayleigh wind speed distribution.
    AEP (MWh) = Σ P(v_bin) × f_Rayleigh(v_bin) × hours_per_year
    """
    if mean_ws < 1.0:
        return 0.0

    k = np.pi / 4  # Rayleigh shape parameter
    v_bins = curve.index.values.astype(float)
    p_bins = curve["power_kw"].values

    # Rayleigh PDF evaluated at each bin
    scale = mean_ws / np.sqrt(np.pi / 2)
    pdf = (v_bins / scale**2) * np.exp(-(v_bins**2) / (2 * scale**2))
    pdf = pdf / pdf.sum()  # normalise to sum=1

    aep_kwh = float(np.sum(p_bins * pdf) * hours_per_year)
    return round(aep_kwh / 1000.0, 1)  # → MWh
