"""
Kelmarsh Wind Farm SCADA connector.

Loads the Zenodo CC-BY-4.0 dataset (Kelmarsh_SCADA_2016-2021) into
pandas DataFrames or yields validated SCADAReading objects one record at a time.

Dataset paper:
  Plumley, C. (2022). Kelmarsh wind farm data.
  Zenodo. https://doi.org/10.5281/zenodo.5841834
"""
from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Iterable, List, Optional

import pandas as pd

from shared.models.domain import SCADAReading
from shared.utils.logging import get_logger

logger = get_logger(__name__)

# Kelmarsh turbine identifiers (as they appear in the dataset filenames)
KELMARSH_TURBINES = ["K1", "K2", "K3", "K4", "K5", "K6"]

# Column mapping: Kelmarsh CSV column → SCADAReading field
COLUMN_MAP = {
    # Wind
    "Wind speed (m/s)": "wind_speed_ms",
    "Wind direction (°)": "wind_direction_deg",
    "Wind speed, Standard deviation (m/s)": "wind_speed_std",
    # Power
    "Power (kW)": "active_power_kw",
    "Reactive Power (kVAr)": "reactive_power_kvar",
    "Power Setpoint (kW)": "power_setpoint_kw",
    # Mechanical
    "Rotor speed (RPM)": "rotor_rpm",
    "Pitch angle A (°)": "pitch_angle_deg",
    "Nacelle direction (°)": "nacelle_direction_deg",
    # Temperatures
    "Ambient temperature (°C)": "temp_ambient_c",
    "Nacelle temperature (°C)": "temp_nacelle_c",
    "Gearbox bearing temperature, Main (°C)": "temp_gearbox_bearing_c",
    "Generator bearing temperature, Drive End (°C)": "temp_generator_bearing_c",
    "Main bearing temperature (°C)": "temp_main_bearing_c",
    # Grid
    "Grid voltage (V)": "grid_voltage_v",
    "Grid frequency (Hz)": "grid_frequency_hz",
}

TIMESTAMP_COL = "# Date and time"


class KelmarshConnector:
    """
    Loads Kelmarsh SCADA data from either:
      - A local .zip archive (as downloaded from Zenodo)
      - A directory of extracted CSV files
      - A single CSV file

    Usage::

        conn = KelmarshConnector(data_path=Path("data/raw/Kelmarsh_SCADA_2016-2021_R0.zip"))
        df = conn.load_dataframe(turbine_id="K1")

        # Or stream as Pydantic models
        for reading in conn.stream_readings("K1"):
            process(reading)
    """

    def __init__(self, data_path: Path):
        self.data_path = Path(data_path)
        if not self.data_path.exists():
            raise FileNotFoundError(f"Kelmarsh data not found at {self.data_path}")

    # ──────────────────────────────────────────────────────────
    #  Public API
    # ──────────────────────────────────────────────────────────

    def load_dataframe(
        self,
        turbine_id: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        columns: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """
        Load SCADA data for one turbine as a tidy DataFrame.

        Returns a DataFrame indexed by UTC timestamp with snake_case column names.
        """
        turbine_id = turbine_id.upper()
        logger.info("Loading Kelmarsh dataframe", turbine=turbine_id)

        raw = self._read_raw_csv(turbine_id)
        df = self._clean_dataframe(raw, turbine_id)

        if start:
            df = df[df.index >= pd.Timestamp(start, tz="UTC")]
        if end:
            df = df[df.index <= pd.Timestamp(end, tz="UTC")]
        if columns:
            available = [c for c in columns if c in df.columns]
            df = df[available]

        logger.info("Loaded dataframe", turbine=turbine_id, rows=len(df))
        return df

    def stream_readings(
        self,
        turbine_id: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        skip_invalid: bool = True,
    ) -> Generator[SCADAReading, None, None]:
        """
        Stream validated SCADAReading Pydantic objects one at a time.
        Memory-efficient for large datasets.
        """
        df = self.load_dataframe(turbine_id, start, end)
        for ts, row in df.iterrows():
            try:
                reading = self._row_to_reading(ts, row, turbine_id)
                yield reading
            except Exception as exc:
                if not skip_invalid:
                    raise
                logger.warning("Skipping invalid row", ts=str(ts), error=str(exc))

    def available_turbines(self) -> List[str]:
        """Return list of turbine IDs present in the data source."""
        if self.data_path.is_file() and self.data_path.suffix == ".zip":
            with zipfile.ZipFile(self.data_path) as zf:
                names = zf.namelist()
            turbines = []
            for tid in KELMARSH_TURBINES:
                if any(tid in n for n in names):
                    turbines.append(tid)
            return turbines
        elif self.data_path.is_dir():
            return [
                tid for tid in KELMARSH_TURBINES
                if list(self.data_path.glob(f"*{tid}*.csv"))
            ]
        return []

    # ──────────────────────────────────────────────────────────
    #  Private helpers
    # ──────────────────────────────────────────────────────────

    def _read_raw_csv(self, turbine_id: str) -> pd.DataFrame:
        if self.data_path.is_file() and self.data_path.suffix == ".zip":
            return self._read_from_zip(turbine_id)
        elif self.data_path.is_dir():
            return self._read_from_dir(turbine_id)
        else:
            # Single CSV file
            return pd.read_csv(self.data_path, low_memory=False)

    def _read_from_zip(self, turbine_id: str) -> pd.DataFrame:
        with zipfile.ZipFile(self.data_path) as zf:
            matching = [n for n in zf.namelist() if turbine_id in n and n.endswith(".csv")]
            if not matching:
                raise ValueError(f"No CSV for turbine {turbine_id} in {self.data_path}")

            frames = []
            for name in sorted(matching):
                with zf.open(name) as f:
                    content = f.read().decode("utf-8", errors="replace")
                    frames.append(pd.read_csv(io.StringIO(content), low_memory=False))
            return pd.concat(frames, ignore_index=True)

    def _read_from_dir(self, turbine_id: str) -> pd.DataFrame:
        csv_files = sorted(self.data_path.glob(f"*{turbine_id}*.csv"))
        if not csv_files:
            raise ValueError(f"No CSV files for turbine {turbine_id} in {self.data_path}")
        frames = [pd.read_csv(f, low_memory=False) for f in csv_files]
        return pd.concat(frames, ignore_index=True)

    def _clean_dataframe(self, raw: pd.DataFrame, turbine_id: str) -> pd.DataFrame:
        """Parse timestamps, rename columns, coerce numeric types."""
        df = raw.copy()

        # Parse timestamp
        ts_col = next((c for c in df.columns if "Date" in c or "time" in c.lower()), None)
        if ts_col is None:
            raise ValueError(f"Cannot find timestamp column in {list(df.columns)[:5]}")

        df[ts_col] = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
        df = df.dropna(subset=[ts_col])
        df = df.set_index(ts_col).sort_index()
        df.index.name = "timestamp"

        # Rename columns using COLUMN_MAP
        rename = {}
        for raw_col, snake_col in COLUMN_MAP.items():
            # Try exact match first, then partial
            if raw_col in df.columns:
                rename[raw_col] = snake_col
            else:
                candidates = [c for c in df.columns if raw_col.split("(")[0].strip().lower() in c.lower()]
                if candidates:
                    rename[candidates[0]] = snake_col

        df = df.rename(columns=rename)

        # Keep only mapped columns plus any extras
        mapped_cols = [c for c in COLUMN_MAP.values() if c in df.columns]
        df = df[mapped_cols]

        # Coerce to numeric
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        # Add turbine_id
        df.insert(0, "turbine_id", turbine_id)

        # Remove duplicates
        df = df[~df.index.duplicated(keep="first")]

        return df

    def _row_to_reading(
        self, ts: pd.Timestamp, row: pd.Series, turbine_id: str
    ) -> SCADAReading:
        data: dict = {"turbine_id": turbine_id, "timestamp": ts.to_pydatetime()}
        for field in SCADAReading.model_fields:
            if field in row.index and pd.notna(row[field]):
                data[field] = row[field]
        return SCADAReading(**data)
