/**
 * Fleet Dashboard — main landing page.
 * Shows fleet-level KPIs, power output, anomaly feed, and turbine status grid.
 */
import React, { useState } from 'react'
import {
  Wind,
  Zap,
  AlertTriangle,
  Activity,
  TrendingUp,
  RefreshCw,
  ChevronRight,
} from 'lucide-react'
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  BarChart,
  Bar,
} from 'recharts'
import { format, parseISO } from 'date-fns'
import { useFleetOverview, useFleetAnomalies, useProduction } from '@/hooks/useApi'
import type { AnomalyEvent, FleetTurbineSummary } from '@/types/domain'
import { clsx } from 'clsx'

// ── Colour helpers ──────────────────────────────────────────────

const SEVERITY_COLORS: Record<string, string> = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#eab308',
  low: '#22c55e',
}

const STATUS_DOT: Record<string, string> = {
  operating: 'bg-emerald-400',
  curtailed: 'bg-yellow-400',
  maintenance: 'bg-blue-400',
  fault: 'bg-red-500',
  offline: 'bg-zinc-500',
  unknown: 'bg-zinc-600',
}

// ── Sub-components ──────────────────────────────────────────────

function KPICard({
  label,
  value,
  unit,
  icon: Icon,
  color = 'text-cyan-400',
  sub,
}: {
  label: string
  value: string | number
  unit?: string
  icon: React.ElementType
  color?: string
  sub?: string
}) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-mono text-zinc-500 uppercase tracking-widest">{label}</span>
        <Icon size={16} className={color} />
      </div>
      <div className="flex items-end gap-1.5">
        <span className={clsx('text-3xl font-black tabular-nums', color)}>{value}</span>
        {unit && <span className="text-sm text-zinc-500 mb-1">{unit}</span>}
      </div>
      {sub && <span className="text-xs text-zinc-600">{sub}</span>}
    </div>
  )
}

function TurbineCard({ turbine }: { turbine: FleetTurbineSummary }) {
  const power = turbine.active_power_kw ?? 0
  const wind = turbine.wind_speed_ms ?? 0
  const pct = Math.min((power / 2050) * 100, 100)
  const status = turbine.availability_flag ? 'operating' : 'offline'

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 hover:border-zinc-600 transition-colors cursor-pointer group">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className={clsx('w-2 h-2 rounded-full', STATUS_DOT[status])} />
          <span className="font-mono font-bold text-sm text-zinc-100">{turbine.turbine_id}</span>
        </div>
        <ChevronRight size={14} className="text-zinc-600 group-hover:text-zinc-400 transition-colors" />
      </div>

      <div className="space-y-2">
        <div className="flex justify-between text-xs text-zinc-500">
          <span>Power</span>
          <span className="text-zinc-300 font-mono">{power.toFixed(0)} kW</span>
        </div>
        {/* Power bar */}
        <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-cyan-500 to-emerald-400 rounded-full transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="flex justify-between text-xs text-zinc-500">
          <span>Wind</span>
          <span className="text-zinc-300 font-mono">{wind.toFixed(1)} m/s</span>
        </div>
      </div>
    </div>
  )
}

function AnomalyRow({ event }: { event: AnomalyEvent }) {
  const color = SEVERITY_COLORS[event.severity] ?? '#71717a'
  return (
    <div className="flex items-start gap-3 py-3 border-b border-zinc-800 last:border-0">
      <div className="w-2 h-2 rounded-full mt-1.5 flex-shrink-0" style={{ background: color }} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <span className="font-mono text-xs text-zinc-300 font-semibold">{event.turbine_id}</span>
          <span
            className="text-xs font-mono uppercase px-2 py-0.5 rounded-full border"
            style={{ color, borderColor: color + '44', background: color + '11' }}
          >
            {event.severity}
          </span>
        </div>
        <p className="text-xs text-zinc-500 mt-0.5 truncate">{event.description || event.anomaly_type}</p>
        <span className="text-xs text-zinc-700 font-mono">
          {format(parseISO(event.detected_at), 'HH:mm dd MMM')}
        </span>
      </div>
    </div>
  )
}

// ── Main Dashboard ──────────────────────────────────────────────

export default function FleetDashboard() {
  const [selectedTurbine] = useState<string | null>(null)

  const { data: fleet, isLoading: fleetLoading, dataUpdatedAt, refetch } = useFleetOverview()
  const { data: anomalies } = useFleetAnomalies()
  // Use the first available turbine for the production chart (falls back to K1)
  const chartTurbineId = fleet?.turbines?.[0]?.turbine_id ?? 'K1'
  const { data: production } = useProduction(chartTurbineId, '1 hour', 7)

  const productionChartData = production?.buckets.map((b) => ({
    time: format(parseISO(b.bucket), 'dd MMM HH:mm'),
    power: b.avg_power_kw ? Math.round(b.avg_power_kw) : 0,
    wind: b.avg_wind_speed ? +b.avg_wind_speed.toFixed(1) : 0,
    energy: b.energy_kwh ? Math.round(b.energy_kwh) : 0,
  })) ?? []

  const lastUpdated = dataUpdatedAt
    ? format(new Date(dataUpdatedAt), 'HH:mm:ss')
    : '—'

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 font-sans">
      {/* ── Header ── */}
      <header className="border-b border-zinc-800 px-6 py-4 flex items-center justify-between sticky top-0 bg-zinc-950/90 backdrop-blur z-10">
        <div className="flex items-center gap-3">
          <Wind size={20} className="text-cyan-400" />
          <span className="font-black text-lg tracking-tight">SCADA</span>
          <span className="text-zinc-600 text-sm">/ Fleet Dashboard</span>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-xs font-mono text-zinc-600">Updated {lastUpdated}</span>
          <button
            onClick={() => refetch()}
            className="p-1.5 rounded-lg hover:bg-zinc-800 transition-colors text-zinc-500 hover:text-zinc-200"
          >
            <RefreshCw size={14} />
          </button>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8 space-y-8">

        {/* ── KPI Row ── */}
        {fleetLoading ? (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-28 bg-zinc-900 rounded-xl animate-pulse" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <KPICard
              label="Fleet Power"
              value={fleet ? (fleet.total_power_kw / 1000).toFixed(2) : '—'}
              unit="MW"
              icon={Zap}
              color="text-cyan-400"
              sub={`${fleet?.operating ?? 0} of ${fleet?.total_turbines ?? 0} turbines producing`}
            />
            <KPICard
              label="Mean Wind"
              value={fleet?.mean_wind_speed_ms.toFixed(1) ?? '—'}
              unit="m/s"
              icon={Wind}
              color="text-emerald-400"
              sub="10-min average across farm"
            />
            <KPICard
              label="Capacity Factor"
              value={fleet?.fleet_capacity_factor_pct.toFixed(1) ?? '—'}
              unit="%"
              icon={TrendingUp}
              color="text-violet-400"
              sub="Rated 12.3 MW fleet"
            />
            <KPICard
              label="Active Alerts"
              value={anomalies?.filter((a) => !a.acknowledged).length ?? 0}
              icon={AlertTriangle}
              color="text-amber-400"
              sub="Unacknowledged anomalies"
            />
          </div>
        )}

        {/* ── Power chart + Turbine grid ── */}
        <div className="grid lg:grid-cols-3 gap-6">

          {/* Power timeline */}
          <div className="lg:col-span-2 bg-zinc-900 border border-zinc-800 rounded-xl p-5">
            <div className="flex items-center justify-between mb-5">
              <div>
                <h2 className="font-bold text-sm">Power Output</h2>
                <p className="text-xs text-zinc-500 mt-0.5">Hourly average — last 7 days</p>
              </div>
              <Activity size={16} className="text-zinc-600" />
            </div>
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={productionChartData}>
                <defs>
                  <linearGradient id="powerGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#22d3ee" stopOpacity={0.25} />
                    <stop offset="95%" stopColor="#22d3ee" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="windGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#34d399" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="#34d399" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                <XAxis
                  dataKey="time"
                  tick={{ fontSize: 10, fill: '#52525b' }}
                  tickLine={false}
                  interval={Math.floor(productionChartData.length / 7)}
                />
                <YAxis
                  yAxisId="power"
                  tick={{ fontSize: 10, fill: '#52525b' }}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  yAxisId="wind"
                  orientation="right"
                  tick={{ fontSize: 10, fill: '#52525b' }}
                  tickLine={false}
                  axisLine={false}
                />
                <Tooltip
                  contentStyle={{
                    background: '#18181b',
                    border: '1px solid #3f3f46',
                    borderRadius: '8px',
                    fontSize: '11px',
                  }}
                />
                <Area
                  yAxisId="power"
                  type="monotone"
                  dataKey="power"
                  stroke="#22d3ee"
                  strokeWidth={2}
                  fill="url(#powerGrad)"
                  name="Power (kW)"
                />
                <Area
                  yAxisId="wind"
                  type="monotone"
                  dataKey="wind"
                  stroke="#34d399"
                  strokeWidth={1.5}
                  fill="url(#windGrad)"
                  name="Wind (m/s)"
                  strokeDasharray="4 2"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* Turbine grid */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
            <h2 className="font-bold text-sm mb-4">Turbine Status</h2>
            <div className="grid grid-cols-2 gap-3">
              {fleet?.turbines.map((t) => (
                <TurbineCard key={t.turbine_id} turbine={t} />
              )) ?? (
                [...Array(6)].map((_, i) => (
                  <div key={i} className="h-24 bg-zinc-800 rounded-xl animate-pulse" />
                ))
              )}
            </div>
          </div>
        </div>

        {/* ── Energy bar chart + Anomaly feed ── */}
        <div className="grid lg:grid-cols-3 gap-6">

          {/* Energy production */}
          <div className="lg:col-span-2 bg-zinc-900 border border-zinc-800 rounded-xl p-5">
            <div className="flex items-center justify-between mb-5">
              <div>
                <h2 className="font-bold text-sm">Energy Production</h2>
                <p className="text-xs text-zinc-500 mt-0.5">kWh per hour — last 7 days</p>
              </div>
            </div>
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={productionChartData.slice(-48)}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                <XAxis
                  dataKey="time"
                  tick={{ fontSize: 9, fill: '#52525b' }}
                  tickLine={false}
                  interval={Math.floor(productionChartData.slice(-48).length / 8)}
                />
                <YAxis
                  tick={{ fontSize: 9, fill: '#52525b' }}
                  tickLine={false}
                  axisLine={false}
                />
                <Tooltip
                  contentStyle={{
                    background: '#18181b',
                    border: '1px solid #3f3f46',
                    borderRadius: '8px',
                    fontSize: '11px',
                  }}
                />
                <Bar dataKey="energy" fill="#818cf8" radius={[2, 2, 0, 0]} name="Energy (kWh)" />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Anomaly feed */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-bold text-sm">Anomaly Feed</h2>
              {anomalies && anomalies.length > 0 && (
                <span className="text-xs font-mono bg-amber-500/10 text-amber-400 border border-amber-500/20 px-2 py-0.5 rounded-full">
                  {anomalies.length} active
                </span>
              )}
            </div>
            <div className="space-y-0 max-h-72 overflow-y-auto">
              {anomalies && anomalies.length > 0 ? (
                anomalies.slice(0, 10).map((a) => <AnomalyRow key={a.anomaly_id} event={a} />)
              ) : (
                <div className="flex flex-col items-center justify-center py-10 text-zinc-700">
                  <Activity size={24} className="mb-2" />
                  <span className="text-xs">No active anomalies</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
