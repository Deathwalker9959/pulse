import { useMemo, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { websocketUrl } from "../api/apiClient";
import { apiService } from "../api/service";
import type {
  AnomalyEvent,
  BucketSize,
  EarthquakeEvent,
  RangePreset,
  SeismicRiskCell,
} from "../api/client";
import type {
  BValueBucket,
  EnergyBucket,
  IETBucket,
  MagFrequencyBucket,
} from "../api/client";
import { useWebSocket } from "./useWebSocket";

const MAX_EVENTS = 500;

interface RangeConfig {
  offsetMs: number | null;
  bucket: BucketSize;
  rollupBucket: BucketSize;
}

const RANGE_CONFIGS: Record<RangePreset, RangeConfig> = {
  "1h": { offsetMs: 1 * 3600 * 1000, bucket: "5m", rollupBucket: "5m" },
  "6h": { offsetMs: 6 * 3600 * 1000, bucket: "15m", rollupBucket: "5m" },
  "24h": { offsetMs: 24 * 3600 * 1000, bucket: "1h", rollupBucket: "5m" },
  "7d": { offsetMs: 7 * 86400 * 1000, bucket: "6h", rollupBucket: "1h" },
  "30d": { offsetMs: 30 * 86400 * 1000, bucket: "1d", rollupBucket: "1d" },
  ytd: { offsetMs: null, bucket: "1d", rollupBucket: "1d" },
};

export interface ResolvedRange {
  from: string;
  to: string;
  bucket: BucketSize;
  rollupBucket: BucketSize;
}

export function resolveRange(preset: RangePreset): ResolvedRange {
  const now = new Date();
  const config = RANGE_CONFIGS[preset];
  const to = now.toISOString();
  const from =
    config.offsetMs === null
      ? new Date(Date.UTC(now.getFullYear(), 0, 1)).toISOString()
      : new Date(now.getTime() - config.offsetMs).toISOString();
  return { from, to, bucket: config.bucket, rollupBucket: config.rollupBucket };
}

export function useDashboardData(
  from?: string,
  to?: string,
  net?: string,
  bucket: BucketSize = "1h",
  rollupBucket: BucketSize = "5m",
  plate?: string,
) {
  const queryClient = useQueryClient();
  const invalidateTimer = useRef<number | undefined>(undefined);

  const spanDays = useMemo(() => {
    if (!from || !to) return 1;
    return (new Date(to).getTime() - new Date(from).getTime()) / 86_400_000;
  }, [from, to]);

  const isHeatmapMode = spanDays > 6;
  const heatmapResolution = spanDays > 180 ? 2 : 3;
  const minMagnitude = !isHeatmapMode && spanDays > 3 ? "2.5" : undefined;
  const bValueBucket: "1h" | "1d" = spanDays <= 1 ? "1h" : "1d";

  const heatmap = useQuery({
    queryKey: [
      "earthquakes",
      "heatmap",
      from,
      to,
      heatmapResolution,
      plate,
      net,
    ],
    queryFn: () =>
      apiService.heatmap(from!, to!, heatmapResolution, plate, net),
    enabled: isHeatmapMode && !!from && !!to,
    staleTime: 60_000,
  });

  const live = useQuery({
    queryKey: ["earthquakes", "live", from, to, minMagnitude, plate, net],
    queryFn: () => apiService.live(from, to, minMagnitude, plate, net),
    enabled: !isHeatmapMode,
    staleTime: from || to ? 30_000 : Infinity,
  });
  const alerts = useQuery({
    queryKey: ["anomalies", "history", from, to, plate, net],
    queryFn: () => apiService.anomalyHistory(from, to, plate, net),
    staleTime: 0,
  });
  const status = useQuery({
    queryKey: ["ingestion", "status"],
    queryFn: apiService.ingestionStatus,
    refetchInterval: 30_000,
  });
  const timeseries = useQuery({
    queryKey: ["earthquakes", "timeseries", from, to, bucket, plate, net],
    queryFn: () => apiService.timeseries(from, to, bucket, plate, net),
  });
  // networks list feeds the dropdown — always unfiltered so all options remain selectable
  const networks = useQuery({
    queryKey: ["earthquakes", "top-networks", from, to, plate],
    queryFn: () => apiService.topNetworks(from, to, plate),
  });
  const places = useQuery({
    queryKey: ["earthquakes", "top-places", from, to, plate, net],
    queryFn: () => apiService.topPlaces(from, to, plate, net),
  });
  const magnitudeBands = useQuery({
    queryKey: ["earthquakes", "magnitude-bands", from, to, plate, net],
    queryFn: () => apiService.magnitudeBands(from, to, plate, net),
  });
  const depthBands = useQuery({
    queryKey: ["earthquakes", "depth-bands", from, to, plate, net],
    queryFn: () => apiService.depthBands(from, to, plate, net),
  });
  const rollups = useQuery({
    queryKey: ["earthquakes", "rollups", from, to, net, rollupBucket, plate],
    queryFn: () =>
      apiService.networkRollups(from, to, net, rollupBucket, plate),
  });

  const magnitudeFrequency = useQuery<MagFrequencyBucket[]>({
    queryKey: ["earthquakes", "magnitude-frequency", from, to, plate, net],
    queryFn: () => apiService.magnitudeFrequency(from!, to!, plate, net),
    enabled: !!from && !!to,
    staleTime: 120_000,
  });
  const energyTimeseries = useQuery<EnergyBucket[]>({
    queryKey: [
      "earthquakes",
      "energy-timeseries",
      from,
      to,
      bucket,
      plate,
      net,
    ],
    queryFn: () => apiService.energyTimeseries(from!, to!, bucket, plate, net),
    enabled: !!from && !!to,
    staleTime: 60_000,
  });
  const bValueHistory = useQuery<BValueBucket[]>({
    queryKey: [
      "earthquakes",
      "b-value-history",
      from,
      to,
      bValueBucket,
      plate,
      net,
    ],
    queryFn: () =>
      apiService.bValueHistory(from!, to!, bValueBucket, plate, net),
    enabled: !!from && !!to,
    staleTime: 120_000,
  });
  const interEventTimes = useQuery<IETBucket[]>({
    queryKey: ["earthquakes", "inter-event-times", from, to, plate, net],
    queryFn: () => apiService.interEventTimes(from!, to!, plate, net),
    enabled: !!from && !!to,
    staleTime: 120_000,
  });

  const seismicRisk = useQuery<SeismicRiskCell[]>({
    queryKey: ["earthquakes", "seismic-risk", plate, net],
    queryFn: () => apiService.seismicRisk(2, plate, net),
    staleTime: 120_000,
    refetchInterval: 300_000,
  });

  const eventsConnected = useWebSocket(websocketUrl("/ws/events"), (data) => {
    const next = JSON.parse(data) as EarthquakeEvent;
    queryClient.setQueryData<EarthquakeEvent[]>(
      ["earthquakes", "live"],
      (previous) => {
        const withoutDuplicate = (previous ?? []).filter(
          (item) => item.event_id !== next.event_id,
        );
        return [next, ...withoutDuplicate].slice(0, MAX_EVENTS);
      },
    );
    if (!invalidateTimer.current) {
      invalidateTimer.current = window.setTimeout(() => {
        void queryClient.invalidateQueries({
          queryKey: ["earthquakes"],
          exact: false,
        });
        void queryClient.invalidateQueries({
          queryKey: ["ingestion"],
          exact: false,
        });
        invalidateTimer.current = undefined;
      }, 2000);
    }
  });

  const alertsConnected = useWebSocket(websocketUrl("/ws/alerts"), (data) => {
    const next = JSON.parse(data) as AnomalyEvent;
    // Inject directly into cache — skip round-trip, instant re-render.
    // Only prepend if the alert matches current plate/net filters (or no filter set).
    const plateMatch = !plate || next.plate_name === plate;
    const netMatch = !net || next.source_net === net;
    if (plateMatch && netMatch) {
      queryClient.setQueryData<AnomalyEvent[]>(
        ["anomalies", "history", from, to, plate, net],
        (previous) => {
          const without = (previous ?? []).filter(
            (a) => a.anomaly_id !== next.anomaly_id,
          );
          return [next, ...without];
        },
      );
    }
    void queryClient.invalidateQueries({
      queryKey: ["ingestion"],
      exact: false,
    });
  });

  return {
    live,
    heatmap,
    isHeatmapMode,
    heatmapResolution,
    alerts,
    status,
    timeseries,
    networks,
    places,
    magnitudeBands,
    depthBands,
    rollups,
    magnitudeFrequency,
    energyTimeseries,
    bValueHistory,
    interEventTimes,
    eventsConnected,
    alertsConnected,
    seismicRisk,
  };
}
