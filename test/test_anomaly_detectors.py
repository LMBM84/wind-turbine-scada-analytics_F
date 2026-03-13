"""
Unit tests for anomaly detection models.
No database or Kafka required — all tests use synthetic SCADA data.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def make_scada_df(n: int = 500, seed: int = 42, inject_anomalies: bool = False) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    wind = rng.weibull(2, n) * 10.0
    power = np.clip(wind ** 2.5 * 10 + rng.normal(0, 30, n), 0, 2050)
    rpm = np.clip(wind * 1.2 + rng.normal(0, 0.3, n), 0, 20)
    temp_gear = 50 + power / 2050 * 15 + rng.normal(0, 1, n)
    temp_gen = 55 + power / 2050 * 20 + rng.normal(0, 1, n)
    pitch = np.where(wind < 12, 2.0, 15.0) + rng.normal(0, 0.5, n)
    timestamps = pd.date_range("2020-01-01", periods=n, freq="10min", tz="UTC")

    df = pd.DataFrame({
        "wind_speed_ms": wind,
        "active_power_kw": power,
        "rotor_rpm": rpm,
        "temp_gearbox_bearing_c": temp_gear,
        "temp_generator_bearing_c": temp_gen,
        "pitch_angle_deg": pitch,
        "availability_flag": rng.choice([True, False], n, p=[0.97, 0.03]),
    }, index=timestamps)

    if inject_anomalies:
        # Inject clear gear-temp spikes at known indices
        df.iloc[100:105, df.columns.get_loc("temp_gearbox_bearing_c")] += 30.0
        df.iloc[200:203, df.columns.get_loc("active_power_kw")] = 0.0

    return df


@pytest.fixture(scope="module")
def train_df():
    return make_scada_df(n=1000)


@pytest.fixture(scope="module")
def anomaly_df():
    return make_scada_df(n=200, seed=99, inject_anomalies=True)


# ── Skip all tests if the analytics package is not installed ──
pytestmark = pytest.mark.skipif(
    not __import__("importlib").util.find_spec("analytics"),
    reason="analytics package not installed",
)


class TestIsolationForestDetector:
    def test_fit_does_not_raise(self, train_df):
        from analytics.anomaly.detectors import IsolationForestDetector
        det = IsolationForestDetector(contamination=0.02)
        det.fit(train_df)
        assert det._fitted is True

    def test_score_range(self, train_df):
        from analytics.anomaly.detectors import IsolationForestDetector
        det = IsolationForestDetector()
        det.fit(train_df)
        scores = det.score(train_df)
        assert scores.min() >= 0.0
        assert scores.max() <= 1.0

    def test_score_stable_across_windows(self, train_df):
        """Scores from two non-overlapping windows should use the same scale."""
        from analytics.anomaly.detectors import IsolationForestDetector
        det = IsolationForestDetector()
        det.fit(train_df)
        s1 = det.score(train_df.iloc[:100])
        s2 = det.score(train_df.iloc[100:200])
        # Both windows must stay in [0, 1] — they used training-time normalisation
        assert s1.min() >= 0.0 and s1.max() <= 1.0
        assert s2.min() >= 0.0 and s2.max() <= 1.0

    def test_injected_anomalies_flagged(self, train_df, anomaly_df):
        from analytics.anomaly.detectors import IsolationForestDetector
        det = IsolationForestDetector(contamination=0.02)
        det.fit(train_df)
        scores = det.score(anomaly_df)
        # Injected anomaly window (rows 100-104) should have higher scores on average
        anomaly_window_mean = scores.iloc[100:105].mean()
        normal_window_mean = scores.iloc[50:55].mean()
        assert anomaly_window_mean > normal_window_mean, (
            f"Anomaly window score {anomaly_window_mean:.3f} should exceed "
            f"normal window score {normal_window_mean:.3f}"
        )

    def test_to_anomaly_events_returns_list(self, train_df):
        from analytics.anomaly.detectors import IsolationForestDetector
        det = IsolationForestDetector()
        det.fit(train_df)
        events = det.to_anomaly_events(train_df.iloc[:50], turbine_id="K1", threshold=0.7)
        assert isinstance(events, list)
        for e in events:
            assert e.turbine_id == "K1"
            assert 0.0 <= e.score <= 1.0

    def test_fit_required_before_score(self, train_df):
        from analytics.anomaly.detectors import IsolationForestDetector
        det = IsolationForestDetector()
        with pytest.raises(RuntimeError, match="not fitted"):
            det.score(train_df)

    def test_missing_features_handled_gracefully(self, train_df):
        """Detector should work even if some feature columns are absent."""
        from analytics.anomaly.detectors import IsolationForestDetector
        det = IsolationForestDetector()
        partial_df = train_df[["wind_speed_ms", "active_power_kw"]]
        det.fit(partial_df)
        scores = det.score(partial_df)
        assert len(scores) == len(partial_df)


class TestStatisticalDetector:
    def test_fit_and_detect(self, train_df):
        from analytics.anomaly.detectors import StatisticalDetector
        det = StatisticalDetector(z_threshold=3.0)
        det.fit(train_df)
        flags = det.detect(train_df)
        assert not flags.empty
        assert all(c.endswith("_anomaly") for c in flags.columns)

    def test_injected_spikes_flagged(self, train_df, anomaly_df):
        from analytics.anomaly.detectors import StatisticalDetector
        det = StatisticalDetector(z_threshold=2.5)
        det.fit(train_df)
        flags = det.detect(anomaly_df)
        gear_col = "temp_gearbox_bearing_c_anomaly"
        if gear_col in flags.columns:
            # The injected +30°C spike should be flagged
            assert flags[gear_col].iloc[100:105].any(), "Injected gearbox temp spike not flagged"

    def test_anomaly_summary_returns_signal_list(self, train_df, anomaly_df):
        from analytics.anomaly.detectors import StatisticalDetector
        det = StatisticalDetector(z_threshold=2.5)
        det.fit(train_df)
        summary = det.anomaly_summary(anomaly_df)
        if len(summary) > 0:
            assert "anomalous_signals" in summary.columns


class TestComputeKPIs:
    def test_kpis_keys_present(self, train_df):
        from analytics.kpis.kpis import compute_kpis
        kpis = compute_kpis(train_df, turbine_id="K1")
        expected = {"turbine_id", "total_intervals", "hours", "total_energy_kwh",
                    "capacity_factor_pct", "p50_power_kw", "availability_pct",
                    "mean_wind_speed_ms", "data_completeness_pct"}
        assert expected.issubset(set(kpis.keys()))

    def test_capacity_factor_range(self, train_df):
        from analytics.kpis.kpis import compute_kpis
        kpis = compute_kpis(train_df, turbine_id="K1")
        assert 0 <= kpis["capacity_factor_pct"] <= 100

    def test_availability_range(self, train_df):
        from analytics.kpis.kpis import compute_kpis
        kpis = compute_kpis(train_df, turbine_id="K1")
        assert 0 <= kpis["availability_pct"] <= 100

    def test_completeness_range(self, train_df):
        from analytics.kpis.kpis import compute_kpis
        kpis = compute_kpis(train_df, turbine_id="K1")
        assert 0 <= kpis["data_completeness_pct"] <= 100
