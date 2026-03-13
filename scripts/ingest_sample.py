#!/usr/bin/env python3
"""
Load sample CSVs from data/sample/ directly into TimescaleDB.
Used for: local dev bootstrap, CI seeding, demos.

Run: python scripts/ingest_sample.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from packages.shared.shared.config.settings import settings

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "data" / "sample"

COLUMN_MAP = {
    "# Date and time": "timestamp",
    "Wind speed (m/s)": "wind_speed_ms",
    "Wind direction (°)": "wind_direction_deg",
    "Wind speed, Standard deviation (m/s)": "wind_speed_std",
    "Power (kW)": "active_power_kw",
    "Reactive Power (kVAr)": "reactive_power_kvar",
    "Rotor speed (RPM)": "rotor_rpm",
    "Pitch angle A (°)": "pitch_angle_deg",
    "Nacelle direction (°)": "nacelle_direction_deg",
    "Ambient temperature (°C)": "temp_ambient_c",
    "Nacelle temperature (°C)": "temp_nacelle_c",
    "Gearbox bearing temperature, Main (°C)": "temp_gearbox_bearing_c",
    "Generator bearing temperature, Drive End (°C)": "temp_generator_bearing_c",
    "Main bearing temperature (°C)": "temp_main_bearing_c",
    "Grid voltage (V)": "grid_voltage_v",
    "Grid frequency (Hz)": "grid_frequency_hz",
}

INSERT_COLS = [
    "turbine_id", "timestamp",
    "wind_speed_ms", "wind_direction_deg", "wind_speed_std",
    "active_power_kw", "reactive_power_kvar",
    "rotor_rpm", "pitch_angle_deg", "nacelle_direction_deg",
    "temp_ambient_c", "temp_nacelle_c",
    "temp_gearbox_bearing_c", "temp_generator_bearing_c",
    "grid_voltage_v", "grid_frequency_hz",
]


def ingest_csv(path: Path, turbine_id: str, conn) -> int:
    df = pd.read_csv(path, comment=None, low_memory=False)

    # Strip leading # from column name if present
    df.columns = [c.lstrip("# ") if c.startswith("#") else c for c in df.columns]
    df = df.rename(columns=COLUMN_MAP)

    if "timestamp" not in df.columns:
        # Try fallback
        ts_col = next((c for c in df.columns if "date" in c.lower() or "time" in c.lower()), None)
        if ts_col:
            df = df.rename(columns={ts_col: "timestamp"})

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"])
    df.insert(0, "turbine_id", turbine_id)

    rows = []
    for _, row in df.iterrows():
        record = []
        for col in INSERT_COLS:
            val = row.get(col)
            if pd.isna(val):
                record.append(None)
            else:
                record.append(val)
        rows.append(tuple(record))

    if not rows:
        print(f"  ⚠  No valid rows in {path.name}")
        return 0

    cols_str = ", ".join(INSERT_COLS)
    placeholders = ", ".join(["%s"] * len(INSERT_COLS))
    sql = f"""
        INSERT INTO scada_readings ({cols_str})
        VALUES %s
        ON CONFLICT (turbine_id, timestamp) DO NOTHING
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, rows, template=f"({placeholders})")
    conn.commit()
    return len(rows)


def main():
    print("🌱  Loading sample SCADA data...")
    conn = psycopg2.connect(settings.database_url_sync)

    csv_files = sorted(SAMPLE_DIR.glob("*.csv"))
    if not csv_files:
        print(f"  No CSVs found in {SAMPLE_DIR}")
        return

    total = 0
    for f in csv_files:
        # Extract turbine ID from filename, e.g. kelmarsh_K1_sample.csv → K1
        parts = f.stem.split("_")
        turbine_id = next((p for p in parts if p.startswith("K") and p[1:].isdigit()), "K1")
        n = ingest_csv(f, turbine_id, conn)
        print(f"  ✓  {f.name} → {n} rows ({turbine_id})")
        total += n

    conn.close()
    print(f"\n✅  Ingested {total} total readings")


if __name__ == "__main__":
    main()
