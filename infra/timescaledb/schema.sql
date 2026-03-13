-- ═══════════════════════════════════════════════════════════════════
--  Wind Turbine SCADA Analytics — TimescaleDB Schema
--  Run after: CREATE EXTENSION IF NOT EXISTS timescaledb;
-- ═══════════════════════════════════════════════════════════════════

-- ── Extensions ────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- ── Turbine metadata ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS turbines (
    turbine_id          TEXT        PRIMARY KEY,
    farm_id             TEXT        NOT NULL DEFAULT 'kelmarsh',
    name                TEXT        NOT NULL,
    manufacturer        TEXT        NOT NULL DEFAULT 'Senvion',
    model               TEXT        NOT NULL DEFAULT 'MM92',
    rated_power_kw      NUMERIC     NOT NULL DEFAULT 2050.0,
    rotor_diameter_m    NUMERIC     NOT NULL DEFAULT 92.0,
    hub_height_m        NUMERIC     NOT NULL DEFAULT 80.0,
    latitude            DOUBLE PRECISION NOT NULL,
    longitude           DOUBLE PRECISION NOT NULL,
    commissioning_date  TIMESTAMPTZ,
    status              TEXT        NOT NULL DEFAULT 'unknown',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Raw SCADA readings — TimescaleDB hypertable ────────────────────
CREATE TABLE IF NOT EXISTS scada_readings (
    turbine_id              TEXT            NOT NULL,
    timestamp               TIMESTAMPTZ     NOT NULL,

    -- Wind signals
    wind_speed_ms           DOUBLE PRECISION,
    wind_direction_deg      DOUBLE PRECISION,
    wind_speed_std          DOUBLE PRECISION,

    -- Power signals
    active_power_kw         DOUBLE PRECISION,
    reactive_power_kvar     DOUBLE PRECISION,
    power_setpoint_kw       DOUBLE PRECISION,

    -- Mechanical
    rotor_rpm               DOUBLE PRECISION,
    pitch_angle_deg         DOUBLE PRECISION,
    nacelle_direction_deg   DOUBLE PRECISION,

    -- Temperatures (°C)
    temp_ambient_c          DOUBLE PRECISION,
    temp_nacelle_c          DOUBLE PRECISION,
    temp_gearbox_bearing_c  DOUBLE PRECISION,
    temp_generator_bearing_c DOUBLE PRECISION,
    temp_main_bearing_c     DOUBLE PRECISION,

    -- Grid
    grid_voltage_v          DOUBLE PRECISION,
    grid_frequency_hz       DOUBLE PRECISION,

    -- Status
    status_code             INTEGER,
    availability_flag       BOOLEAN         NOT NULL DEFAULT TRUE,

    -- Ingestion metadata
    ingested_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    source                  TEXT            NOT NULL DEFAULT 'kelmarsh',

    PRIMARY KEY (turbine_id, timestamp)
);

-- Convert to hypertable partitioned by timestamp
SELECT create_hypertable(
    'scada_readings',
    'timestamp',
    chunk_time_interval => INTERVAL '1 month',
    if_not_exists => TRUE
);

-- Add compression policy (compress chunks older than 7 days)
ALTER TABLE scada_readings SET (
    timescaledb.compress,
    timescaledb.compress_orderby = 'timestamp ASC',
    timescaledb.compress_segmentby = 'turbine_id'
);

SELECT add_compression_policy('scada_readings', INTERVAL '7 days', if_not_exists => TRUE);

-- Retention: keep 5 years of raw data
SELECT add_retention_policy('scada_readings', INTERVAL '5 years', if_not_exists => TRUE);

-- ── Continuous Aggregates — hourly rollup ─────────────────────────
CREATE MATERIALIZED VIEW IF NOT EXISTS scada_hourly
WITH (timescaledb.continuous) AS
SELECT
    turbine_id,
    time_bucket('1 hour', timestamp)           AS hour,
    AVG(wind_speed_ms)                         AS avg_wind_speed_ms,
    STDDEV(wind_speed_ms)                      AS std_wind_speed_ms,
    AVG(active_power_kw)                       AS avg_power_kw,
    SUM(active_power_kw * 10.0 / 60.0)        AS energy_kwh,      -- 10-min intervals
    AVG(rotor_rpm)                             AS avg_rotor_rpm,
    AVG(temp_gearbox_bearing_c)               AS avg_temp_gearbox_c,
    AVG(temp_generator_bearing_c)             AS avg_temp_generator_c,
    AVG(availability_flag::int)               AS availability_ratio,
    COUNT(*)                                   AS interval_count
FROM scada_readings
GROUP BY turbine_id, hour
WITH NO DATA;

SELECT add_continuous_aggregate_policy(
    'scada_hourly',
    start_offset => INTERVAL '3 hours',
    end_offset   => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- Daily rollup
CREATE MATERIALIZED VIEW IF NOT EXISTS scada_daily
WITH (timescaledb.continuous) AS
SELECT
    turbine_id,
    time_bucket('1 day', timestamp)            AS day,
    AVG(wind_speed_ms)                         AS avg_wind_speed_ms,
    AVG(active_power_kw)                       AS avg_power_kw,
    SUM(active_power_kw * 10.0 / 60.0)        AS energy_kwh,
    AVG(availability_flag::int)               AS availability_ratio,
    COUNT(*)                                   AS interval_count
FROM scada_readings
GROUP BY turbine_id, day
WITH NO DATA;

SELECT add_continuous_aggregate_policy(
    'scada_daily',
    start_offset => INTERVAL '2 days',
    end_offset   => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- ── Anomaly events ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS anomaly_events (
    anomaly_id      TEXT            PRIMARY KEY,
    turbine_id      TEXT            NOT NULL,
    detected_at     TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    interval_start  TIMESTAMPTZ     NOT NULL,
    anomaly_type    TEXT            NOT NULL DEFAULT 'unknown',
    severity        TEXT            NOT NULL DEFAULT 'low',
    score           DOUBLE PRECISION NOT NULL CHECK (score BETWEEN 0 AND 1),
    model_name      TEXT            NOT NULL,
    features_used   TEXT[],
    shap_values     JSONB,
    description     TEXT            NOT NULL DEFAULT '',
    acknowledged    BOOLEAN         NOT NULL DEFAULT FALSE,
    resolved        BOOLEAN         NOT NULL DEFAULT FALSE,
    resolved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_anomaly_turbine_time
    ON anomaly_events (turbine_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_anomaly_severity
    ON anomaly_events (severity) WHERE resolved = FALSE;

-- ── Power curve cache ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS power_curve_cache (
    id              SERIAL          PRIMARY KEY,
    turbine_id      TEXT            NOT NULL,
    computed_at     TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    method          TEXT            NOT NULL DEFAULT 'IEC-61400-12-1',
    months_data     INTEGER         NOT NULL,
    rated_power_kw  DOUBLE PRECISION NOT NULL,
    cut_in_ms       DOUBLE PRECISION,
    cut_out_ms      DOUBLE PRECISION,
    capacity_factor DOUBLE PRECISION,
    aep_mwh         DOUBLE PRECISION,
    curve_json      JSONB           NOT NULL,
    UNIQUE (turbine_id, computed_at)
);

-- ── Seed Kelmarsh turbine metadata ────────────────────────────────
INSERT INTO turbines (turbine_id, farm_id, name, latitude, longitude, commissioning_date)
VALUES
    ('K1', 'kelmarsh', 'Kelmarsh 1', 52.3931, -0.9950, '2015-01-01'),
    ('K2', 'kelmarsh', 'Kelmarsh 2', 52.3938, -0.9942, '2015-01-01'),
    ('K3', 'kelmarsh', 'Kelmarsh 3', 52.3945, -0.9935, '2015-01-01'),
    ('K4', 'kelmarsh', 'Kelmarsh 4', 52.3920, -0.9960, '2015-01-01'),
    ('K5', 'kelmarsh', 'Kelmarsh 5', 52.3912, -0.9968, '2015-01-01'),
    ('K6', 'kelmarsh', 'Kelmarsh 6', 52.3905, -0.9975, '2015-01-01')
ON CONFLICT (turbine_id) DO NOTHING;
