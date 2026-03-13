"""
Unit tests for IEC 61400-12-1 power curve computation.
Uses synthetic data — no external dependencies.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def make_synthetic_scada(n: int = 5000, seed: int = 42) -> pd.DataFrame:
    """
    Generate synthetic SCADA readings that follow a plausible MM92 power curve
    with realistic scatter.
    """
    rng = np.random.default_rng(seed)

    # Weibull wind distribution (k=2, λ=10 m/s)
    wind = rng.weibull(2, n) * 10.0

    # Simple piecewise power curve (cut-in 3, rated at 12, cut-out 24 m/s)
    def theoretical_power(ws):
        if ws < 3.0:
            return 0.0
        elif ws > 24.0:
            return 0.0
        elif ws >= 12.0:
            return 2050.0
        else:
            return 2050.0 * ((ws - 3.0) / (12.0 - 3.0)) ** 3

    expected = np.array([theoretical_power(w) for w in wind])
    noise = rng.normal(0, 40, n)
    power = np.clip(expected + noise, 0, 2100)

    timestamps = pd.date_range("2020-01-01", periods=n, freq="10min", tz="UTC")
    return pd.DataFrame(
        {
            "wind_speed_ms": wind,
            "active_power_kw": power,
            "temp_ambient_c": rng.normal(10, 5, n),
            "availability_flag": rng.choice([True, False], n, p=[0.97, 0.03]),
        },
        index=timestamps,
    )


@pytest.fixture(scope="module")
def synthetic_df():
    return make_synthetic_scada()


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("analytics"),
    reason="analytics package not installed",
)
class TestPowerCurve:
    def test_returns_power_curve_result(self, synthetic_df):
        from analytics.power_curve.iec_power_curve import compute_power_curve
        result = compute_power_curve(synthetic_df, turbine_id="TEST")
        assert result.turbine_id == "TEST"
        assert len(result.points) > 5

    def test_cut_in_is_near_3ms(self, synthetic_df):
        from analytics.power_curve.iec_power_curve import compute_power_curve
        result = compute_power_curve(synthetic_df, turbine_id="TEST")
        assert 2.5 <= result.cut_in_ms <= 4.5, f"cut-in was {result.cut_in_ms}"

    def test_capacity_factor_between_0_and_1(self, synthetic_df):
        from analytics.power_curve.iec_power_curve import compute_power_curve
        result = compute_power_curve(synthetic_df, turbine_id="TEST")
        assert 0 < result.capacity_factor < 1

    def test_points_are_non_negative(self, synthetic_df):
        from analytics.power_curve.iec_power_curve import compute_power_curve
        result = compute_power_curve(synthetic_df, turbine_id="TEST")
        for pt in result.points:
            assert pt.power_kw >= 0
            assert pt.wind_speed_ms > 0

    def test_rated_power_not_exceeded(self, synthetic_df):
        from analytics.power_curve.iec_power_curve import compute_power_curve
        result = compute_power_curve(synthetic_df, turbine_id="TEST")
        for pt in result.points:
            assert pt.power_kw <= result.rated_power_kw * 1.02  # 2% tolerance

    def test_aep_is_positive(self, synthetic_df):
        from analytics.power_curve.iec_power_curve import compute_power_curve
        result = compute_power_curve(synthetic_df, turbine_id="TEST")
        if result.annual_energy_production_mwh is not None:
            assert result.annual_energy_production_mwh > 0

    def test_method_label(self, synthetic_df):
        from analytics.power_curve.iec_power_curve import compute_power_curve
        result = compute_power_curve(synthetic_df, turbine_id="TEST")
        assert result.method == "IEC-61400-12-1"


class TestPowerCurveSynthetic:
    """Tests that work without installing the analytics package."""

    def test_synthetic_data_shape(self, synthetic_df):
        assert len(synthetic_df) == 5000
        assert "wind_speed_ms" in synthetic_df.columns
        assert "active_power_kw" in synthetic_df.columns

    def test_power_is_zero_below_cut_in(self, synthetic_df):
        below_cut_in = synthetic_df[synthetic_df["wind_speed_ms"] < 3.0]
        if len(below_cut_in) > 0:
            # Some noise is allowed, but mean should be near zero
            mean_power = below_cut_in["active_power_kw"].mean()
            assert mean_power < 100, f"Mean power below cut-in was {mean_power:.1f} kW"

    def test_weibull_wind_distribution(self, synthetic_df):
        ws = synthetic_df["wind_speed_ms"]
        assert ws.min() >= 0
        assert ws.mean() > 5  # typical for good wind site
        assert ws.mean() < 20
