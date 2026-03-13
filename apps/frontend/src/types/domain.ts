// ─────────────────────────────────────────────────────────────
//  Core domain types — mirrors backend Pydantic models
// ─────────────────────────────────────────────────────────────

export type TurbineStatus =
  | 'operating'
  | 'curtailed'
  | 'maintenance'
  | 'fault'
  | 'offline'
  | 'unknown'

export type AnomalySeverity = 'low' | 'medium' | 'high' | 'critical'

export type AnomalyType =
  | 'power_curve_deviation'
  | 'temperature_anomaly'
  | 'vibration_anomaly'
  | 'electrical_anomaly'
  | 'rotor_anomaly'
  | 'gearbox_anomaly'
  | 'generator_anomaly'
  | 'unknown'

// ── Turbine ───────────────────────────────────────────────────

export interface TurbineMetadata {
  turbine_id: string
  farm_id: string
  name: string
  manufacturer: string
  model: string
  rated_power_kw: number
  rotor_diameter_m: number
  hub_height_m: number
  latitude: number
  longitude: number
  commissioning_date: string | null
  status: TurbineStatus
}

// ── SCADA Reading ─────────────────────────────────────────────

export interface SCADAReading {
  turbine_id: string
  timestamp: string
  wind_speed_ms: number | null
  wind_direction_deg: number | null
  active_power_kw: number | null
  reactive_power_kvar: number | null
  rotor_rpm: number | null
  pitch_angle_deg: number | null
  nacelle_direction_deg: number | null
  temp_ambient_c: number | null
  temp_nacelle_c: number | null
  temp_gearbox_bearing_c: number | null
  temp_generator_bearing_c: number | null
  grid_voltage_v: number | null
  grid_frequency_hz: number | null
  availability_flag: boolean
}

export interface ReadingsResponse {
  turbine_id: string
  count: number
  start: string
  end: string
  readings: SCADAReading[]
}

// ── Power Curve ───────────────────────────────────────────────

export interface PowerCurvePoint {
  wind_speed_ms: number
  power_kw: number
  count: number
  power_std: number
  p10: number | null
  p90: number | null
}

export interface PowerCurveResult {
  turbine_id: string
  computed_at: string
  method: string
  wind_speed_bins: number[]
  rated_power_kw: number
  cut_in_ms: number
  cut_out_ms: number
  capacity_factor: number
  annual_energy_production_mwh: number | null
  points: PowerCurvePoint[]
}

// ── Anomaly ───────────────────────────────────────────────────

export interface AnomalyEvent {
  anomaly_id: string
  turbine_id: string
  detected_at: string
  interval_start: string
  anomaly_type: AnomalyType
  severity: AnomalySeverity
  score: number
  model_name: string
  features_used: string[]
  description: string
  acknowledged: boolean
  resolved: boolean
}

// ── Fleet ─────────────────────────────────────────────────────

export interface FleetTurbineSummary {
  turbine_id: string
  timestamp: string
  wind_speed_ms: number | null
  active_power_kw: number | null
  availability_flag: boolean
  temp_nacelle_c: number | null
}

export interface FleetSummary {
  computed_at: string
  total_turbines: number
  operating: number
  total_power_kw: number
  mean_wind_speed_ms: number
  fleet_capacity_factor_pct: number
  turbines: FleetTurbineSummary[]
}

// ── KPIs ──────────────────────────────────────────────────────

export interface TurbineKPIs {
  turbine_id: string
  total_intervals: number
  hours: number
  total_energy_kwh: number
  capacity_factor_pct: number
  p50_power_kw: number
  availability_pct: number
  mean_wind_speed_ms: number
  data_completeness_pct: number
  period_start: string
  period_end: string
}

// ── Production Rollup ─────────────────────────────────────────

export interface ProductionBucket {
  bucket: string
  avg_wind_speed: number | null
  avg_power_kw: number | null
  energy_kwh: number | null
  intervals: number
  availability: number | null
}

export interface ProductionRollup {
  turbine_id: string
  granularity: string
  buckets: ProductionBucket[]
}
