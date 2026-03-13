/**
 * React Query hooks for all SCADA API endpoints.
 * These are the primary data-fetching layer for the dashboard.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import type {
  TurbineMetadata,
  ReadingsResponse,
  FleetSummary,
  PowerCurveResult,
  AnomalyEvent,
  TurbineKPIs,
  ProductionRollup,
} from '@/types/domain'

const api = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

// ── Query Keys ─────────────────────────────────────────────────

export const queryKeys = {
  turbines: ['turbines'] as const,
  turbine: (id: string) => ['turbines', id] as const,
  readings: (turbineId: string, hours?: number) => ['readings', turbineId, hours] as const,
  fleetOverview: ['fleet', 'overview'] as const,
  powerCurve: (turbineId: string, months?: number) => ['power-curve', turbineId, months] as const,
  anomalies: (turbineId: string, hours?: number) => ['anomalies', turbineId, hours] as const,
  fleetAnomalies: ['anomalies', 'fleet'] as const,
  kpis: (turbineId: string, hours?: number) => ['kpis', turbineId, hours] as const,
  production: (turbineId: string, granularity?: string, days?: number) =>
    ['production', turbineId, granularity, days] as const,
}

// ── Turbines ──────────────────────────────────────────────────

export function useTurbines() {
  return useQuery({
    queryKey: queryKeys.turbines,
    queryFn: async (): Promise<TurbineMetadata[]> => {
      const { data } = await api.get('/turbines/')
      return data
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
  })
}

export function useTurbine(turbineId: string) {
  return useQuery({
    queryKey: queryKeys.turbine(turbineId),
    queryFn: async (): Promise<TurbineMetadata> => {
      const { data } = await api.get(`/turbines/${turbineId}`)
      return data
    },
    enabled: !!turbineId,
    staleTime: 5 * 60 * 1000,
  })
}

// ── SCADA Readings ─────────────────────────────────────────────

export function useReadings(turbineId: string, hours: number = 24) {
  const end = new Date().toISOString()
  const start = new Date(Date.now() - hours * 3600 * 1000).toISOString()

  return useQuery({
    queryKey: queryKeys.readings(turbineId, hours),
    queryFn: async (): Promise<ReadingsResponse> => {
      const { data } = await api.get(`/scada/${turbineId}/readings`, {
        params: { start, end, limit: 1000 },
      })
      return data
    },
    enabled: !!turbineId,
    refetchInterval: 10 * 60 * 1000, // every 10 min
  })
}

// ── Fleet ──────────────────────────────────────────────────────

export function useFleetOverview() {
  return useQuery({
    queryKey: queryKeys.fleetOverview,
    queryFn: async (): Promise<FleetSummary> => {
      const { data } = await api.get('/analytics/fleet/overview')
      return data
    },
    refetchInterval: 60 * 1000, // every minute
  })
}

// ── Power Curve ────────────────────────────────────────────────

export function usePowerCurve(turbineId: string, months: number = 12) {
  return useQuery({
    queryKey: queryKeys.powerCurve(turbineId, months),
    queryFn: async (): Promise<PowerCurveResult> => {
      const { data } = await api.get(`/analytics/${turbineId}/power-curve`, {
        params: { months },
      })
      return data
    },
    enabled: !!turbineId,
    staleTime: 60 * 60 * 1000, // 1 hour
  })
}

// ── Anomalies ──────────────────────────────────────────────────

export function useAnomalies(turbineId: string, hours: number = 168) {
  return useQuery({
    queryKey: queryKeys.anomalies(turbineId, hours),
    queryFn: async (): Promise<{ turbine_id: string; total: number; anomalies: AnomalyEvent[] }> => {
      const { data } = await api.get(`/anomalies/${turbineId}`, {
        params: { hours, unresolved_only: true },
      })
      return data
    },
    enabled: !!turbineId,
    refetchInterval: 5 * 60 * 1000,
  })
}

export function useFleetAnomalies() {
  return useQuery({
    queryKey: queryKeys.fleetAnomalies,
    queryFn: async (): Promise<AnomalyEvent[]> => {
      const { data } = await api.get('/anomalies/fleet/active')
      return data
    },
    refetchInterval: 60 * 1000,
  })
}

export function useAcknowledgeAnomaly() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (anomalyId: string) => {
      const { data } = await api.post(`/anomalies/${anomalyId}/ack`)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.fleetAnomalies })
    },
  })
}

// ── KPIs ──────────────────────────────────────────────────────

export function useKPIs(turbineId: string, hours: number = 720) {
  return useQuery({
    queryKey: queryKeys.kpis(turbineId, hours),
    queryFn: async (): Promise<TurbineKPIs> => {
      const { data } = await api.get(`/analytics/${turbineId}/kpis`, { params: { hours } })
      return data
    },
    enabled: !!turbineId,
    staleTime: 30 * 60 * 1000,
  })
}

// ── Production ─────────────────────────────────────────────────

export function useProduction(
  turbineId: string,
  granularity: '10 minutes' | '1 hour' | '1 day' = '1 hour',
  days: number = 30
) {
  return useQuery({
    queryKey: queryKeys.production(turbineId, granularity, days),
    queryFn: async (): Promise<ProductionRollup> => {
      const { data } = await api.get(`/analytics/${turbineId}/production`, {
        params: { granularity, days },
      })
      return data
    },
    enabled: !!turbineId,
    staleTime: 30 * 60 * 1000,
  })
}
