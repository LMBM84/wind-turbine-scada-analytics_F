"""
Unit tests for the Kelmarsh SCADA connector.
Uses the bundled sample CSV — no network or full dataset required.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

# Project root
SAMPLE_CSV = Path(__file__).resolve().parents[1] / "data" / "sample" / "kelmarsh_K1_sample.csv"

# We import inside tests to avoid package resolution issues in CI
# where packages may not yet be installed


@pytest.fixture
def sample_df() -> pd.DataFrame:
    """Load the sample CSV directly (bypasses the connector for isolation)."""
    df = pd.read_csv(SAMPLE_CSV, low_memory=False)
    df.columns = [c.lstrip("# ") if c.startswith("#") else c for c in df.columns]
    df["Date and time"] = pd.to_datetime(df["Date and time"], utc=True, errors="coerce")
    df = df.dropna(subset=["Date and time"]).set_index("Date and time")
    return df


def test_sample_csv_exists():
    assert SAMPLE_CSV.exists(), f"Sample CSV not found at {SAMPLE_CSV}"


def test_sample_csv_has_expected_columns(sample_df):
    expected = {"Wind speed (m/s)", "Power (kW)", "Ambient temperature (°C)"}
    assert expected.issubset(set(sample_df.columns))


def test_sample_csv_row_count(sample_df):
    assert len(sample_df) >= 10, "Expected at least 10 rows in sample CSV"


def test_power_values_reasonable(sample_df):
    power = sample_df["Power (kW)"].dropna()
    assert power.min() >= 0, "Power should not be negative"
    assert power.max() <= 2200, "Power exceeds rated + 10% tolerance"


def test_wind_speed_range(sample_df):
    ws = sample_df["Wind speed (m/s)"].dropna()
    assert ws.min() >= 0
    assert ws.max() <= 50


def test_timestamps_are_utc_sorted(sample_df):
    assert sample_df.index.is_monotonic_increasing


@pytest.mark.skipif(
    not Path(
        Path(__file__).resolve().parents[1] / "packages" / "connectors" / "connectors"
    ).exists(),
    reason="connectors package not installed",
)
class TestKelmarshConnector:
    def test_connector_loads_sample(self):
        from connectors.kelmarsh.loader import KelmarshConnector
        conn = KelmarshConnector(SAMPLE_CSV)
        df = conn.load_dataframe("K1")
        assert len(df) > 0
        assert "active_power_kw" in df.columns

    def test_connector_streams_readings(self):
        from connectors.kelmarsh.loader import KelmarshConnector
        conn = KelmarshConnector(SAMPLE_CSV)
        readings = list(conn.stream_readings("K1"))
        assert len(readings) > 0
        assert all(r.turbine_id == "K1" for r in readings)

    def test_reading_timestamps_are_utc(self):
        from connectors.kelmarsh.loader import KelmarshConnector
        conn = KelmarshConnector(SAMPLE_CSV)
        readings = list(conn.stream_readings("K1"))
        for r in readings:
            assert r.timestamp.tzinfo is not None
