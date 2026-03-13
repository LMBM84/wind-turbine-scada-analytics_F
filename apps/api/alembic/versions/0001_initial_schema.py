"""Initial schema — turbines, scada_readings hypertable, anomaly_events, power_curve_cache.

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2025-01-01 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Extensions ──────────────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")

    # ── Turbines ─────────────────────────────────────────────
    op.create_table(
        "turbines",
        sa.Column("turbine_id",         sa.Text,             primary_key=True),
        sa.Column("farm_id",            sa.Text,             nullable=False, server_default="kelmarsh"),
        sa.Column("name",               sa.Text,             nullable=False),
        sa.Column("manufacturer",       sa.Text,             nullable=False, server_default="Senvion"),
        sa.Column("model",              sa.Text,             nullable=False, server_default="MM92"),
        sa.Column("rated_power_kw",     sa.Numeric,          nullable=False, server_default="2050.0"),
        sa.Column("rotor_diameter_m",   sa.Numeric,          nullable=False, server_default="92.0"),
        sa.Column("hub_height_m",       sa.Numeric,          nullable=False, server_default="80.0"),
        sa.Column("latitude",           sa.Float,            nullable=False),
        sa.Column("longitude",          sa.Float,            nullable=False),
        sa.Column("commissioning_date", sa.TIMESTAMP(timezone=True)),
        sa.Column("status",             sa.Text,             nullable=False, server_default="unknown"),
        sa.Column("created_at",         sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at",         sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )

    # ── SCADA readings ────────────────────────────────────────
    op.create_table(
        "scada_readings",
        sa.Column("turbine_id",                 sa.Text,    nullable=False),
        sa.Column("timestamp",                  sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("wind_speed_ms",              sa.Float),
        sa.Column("wind_direction_deg",         sa.Float),
        sa.Column("wind_speed_std",             sa.Float),
        sa.Column("active_power_kw",            sa.Float),
        sa.Column("reactive_power_kvar",        sa.Float),
        sa.Column("power_setpoint_kw",          sa.Float),
        sa.Column("rotor_rpm",                  sa.Float),
        sa.Column("pitch_angle_deg",            sa.Float),
        sa.Column("nacelle_direction_deg",      sa.Float),
        sa.Column("temp_ambient_c",             sa.Float),
        sa.Column("temp_nacelle_c",             sa.Float),
        sa.Column("temp_gearbox_bearing_c",     sa.Float),
        sa.Column("temp_generator_bearing_c",   sa.Float),
        sa.Column("temp_main_bearing_c",        sa.Float),
        sa.Column("grid_voltage_v",             sa.Float),
        sa.Column("grid_frequency_hz",          sa.Float),
        sa.Column("status_code",                sa.Integer),
        sa.Column("availability_flag",          sa.Boolean, nullable=False, server_default="TRUE"),
        sa.Column("ingested_at",                sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("source",                     sa.Text,    nullable=False, server_default="kelmarsh"),
        sa.PrimaryKeyConstraint("turbine_id", "timestamp"),
    )
    # Convert to TimescaleDB hypertable
    op.execute(
        "SELECT create_hypertable('scada_readings', 'timestamp', "
        "chunk_time_interval => INTERVAL '1 month', if_not_exists => TRUE)"
    )
    # Compression
    op.execute(
        "ALTER TABLE scada_readings SET ("
        "timescaledb.compress, "
        "timescaledb.compress_orderby = 'timestamp ASC', "
        "timescaledb.compress_segmentby = 'turbine_id')"
    )
    op.execute(
        "SELECT add_compression_policy('scada_readings', INTERVAL '7 days', if_not_exists => TRUE)"
    )
    op.execute(
        "SELECT add_retention_policy('scada_readings', INTERVAL '5 years', if_not_exists => TRUE)"
    )

    # ── Anomaly events ────────────────────────────────────────
    op.create_table(
        "anomaly_events",
        sa.Column("anomaly_id",     sa.Text,    primary_key=True),
        sa.Column("turbine_id",     sa.Text,    nullable=False),
        sa.Column("detected_at",    sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("interval_start", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("anomaly_type",   sa.Text,    nullable=False, server_default="unknown"),
        sa.Column("severity",       sa.Text,    nullable=False, server_default="low"),
        sa.Column("score",          sa.Float,   nullable=False),
        sa.Column("model_name",     sa.Text,    nullable=False),
        sa.Column("features_used",  postgresql.ARRAY(sa.Text)),
        sa.Column("shap_values",    postgresql.JSONB),
        sa.Column("description",    sa.Text,    nullable=False, server_default=""),
        sa.Column("acknowledged",   sa.Boolean, nullable=False, server_default="FALSE"),
        sa.Column("resolved",       sa.Boolean, nullable=False, server_default="FALSE"),
        sa.Column("resolved_at",    sa.TIMESTAMP(timezone=True)),
        sa.Column("created_at",     sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint("score BETWEEN 0 AND 1", name="ck_anomaly_score_range"),
    )
    op.create_index("idx_anomaly_turbine_time", "anomaly_events", ["turbine_id", sa.text("detected_at DESC")])
    op.create_index("idx_anomaly_severity",     "anomaly_events", ["severity"],
                    postgresql_where=sa.text("resolved = FALSE"))

    # ── Power curve cache ─────────────────────────────────────
    op.create_table(
        "power_curve_cache",
        sa.Column("id",             sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("turbine_id",     sa.Text,    nullable=False),
        sa.Column("computed_at",    sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("method",         sa.Text,    nullable=False, server_default="IEC-61400-12-1"),
        sa.Column("months_data",    sa.Integer, nullable=False),
        sa.Column("rated_power_kw", sa.Float,   nullable=False),
        sa.Column("cut_in_ms",      sa.Float),
        sa.Column("cut_out_ms",     sa.Float),
        sa.Column("capacity_factor",sa.Float),
        sa.Column("aep_mwh",        sa.Float),
        sa.Column("curve_json",     postgresql.JSONB, nullable=False),
        sa.UniqueConstraint("turbine_id", "computed_at", name="uq_power_curve_turbine_time"),
    )

    # ── Seed turbine metadata ─────────────────────────────────
    op.execute("""
        INSERT INTO turbines (turbine_id, farm_id, name, latitude, longitude, commissioning_date)
        VALUES
            ('K1', 'kelmarsh', 'Kelmarsh 1', 52.3931, -0.9950, '2015-01-01'),
            ('K2', 'kelmarsh', 'Kelmarsh 2', 52.3938, -0.9942, '2015-01-01'),
            ('K3', 'kelmarsh', 'Kelmarsh 3', 52.3945, -0.9935, '2015-01-01'),
            ('K4', 'kelmarsh', 'Kelmarsh 4', 52.3920, -0.9960, '2015-01-01'),
            ('K5', 'kelmarsh', 'Kelmarsh 5', 52.3912, -0.9968, '2015-01-01'),
            ('K6', 'kelmarsh', 'Kelmarsh 6', 52.3905, -0.9975, '2015-01-01')
        ON CONFLICT (turbine_id) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table("power_curve_cache")
    op.drop_index("idx_anomaly_severity",     table_name="anomaly_events")
    op.drop_index("idx_anomaly_turbine_time", table_name="anomaly_events")
    op.drop_table("anomaly_events")
    op.drop_table("scada_readings")
    op.drop_table("turbines")
