import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type AnomalyEvent, type BucketSize, type EarthquakeEvent, type RangePreset, websocketUrl } from "../api/client";

const MAX_EVENTS = 500;

interface RangeConfig {
  offsetMs: number | null;
  bucket: BucketSize;
  rollupBucket: BucketSize;
}

const RANGE_CONFIGS: Record<RangePreset, RangeConfig> = {
  "1h":  { offsetMs: 1 * 3600 * 1000,   bucket: "5m",  rollupBucket: "5m"  },
  "6h":  { offsetMs: 6 * 3600 * 1000,   bucket: "15m", rollupBucket: "5m"  },
  "24h": { offsetMs: 24 * 3600 * 1000,  bucket: "1h",  rollupBucket: "5m"  },
  "7d":  { offsetMs: 7 * 86400 * 1000,  bucket: "6h",  rollupBucket: "1h"  },
  "30d": { offsetMs: 30 * 86400 * 1000, bucket: "1d",  rollupBucket: "1d"  },
  "ytd": { offsetMs: null,              bucket: "1d",  rollupBucket: "1d"  },
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
  const from = config.offsetMs === null
    ? new Date(Date.UTC(now.getFullYear(), 0, 1)).toISOString()
    : new Date(now.getTime() - config.offsetMs).toISOString();
  return { from, to, bucket: config.bucket, rollupBucket: config.rollupBucket };
}

export function useDashboardData(from?: string, to?: string, net?: string, bucket: BucketSize = "1h", rollupBucket: BucketSize = "5m") {
  const queryClient = useQueryClient();
  const [eventsConnected, setEventsConnected] = useState(false);
  const [alertsConnected, setAlertsConnected] = useState(false);
  const invalidateTimer = useRef<number | undefined>(undefined);

  const spanDays = useMemo(() => {
    if (!from || !to) return 1;
    return (new Date(to).getTime() - new Date(from).getTime()) / 86_400_000;
  }, [from, to]);

  const isHeatmapMode = spanDays > 6;
  const heatmapResolution = spanDays > 180 ? 2 : 3;
  const minMagnitude = !isHeatmapMode && spanDays > 3 ? "2.5" : undefined;

  const heatmap = useQuery({
    queryKey: ["earthquakes", "heatmap", from, to, heatmapResolution],
    queryFn: () => api.heatmap(from!, to!, heatmapResolution),
    enabled: isHeatmapMode && !!from && !!to,
    staleTime: 60_000,
  });

  const live = useQuery({
    queryKey: ["earthquakes", "live", from, to, minMagnitude],
    queryFn: () => api.live(from, to, minMagnitude),
    enabled: !isHeatmapMode,
    staleTime: from || to ? 30_000 : Infinity,
  });
  const alerts = useQuery({ queryKey: ["anomalies", "history", from, to], queryFn: () => api.anomalyHistory(from, to), staleTime: 0 });
  const status = useQuery({ queryKey: ["ingestion", "status"], queryFn: api.ingestionStatus });
  const timeseries = useQuery({ queryKey: ["earthquakes", "timeseries", from, to, bucket], queryFn: () => api.timeseries(from, to, bucket) });
  const networks = useQuery({ queryKey: ["earthquakes", "top-networks", from, to], queryFn: () => api.topNetworks(from, to) });
  const places = useQuery({ queryKey: ["earthquakes", "top-places", from, to], queryFn: () => api.topPlaces(from, to) });
  const magnitudeBands = useQuery({ queryKey: ["earthquakes", "magnitude-bands", from, to], queryFn: () => api.magnitudeBands(from, to) });
  const depthBands = useQuery({ queryKey: ["earthquakes", "depth-bands", from, to], queryFn: () => api.depthBands(from, to) });
  const rollups = useQuery({ queryKey: ["earthquakes", "rollups", from, to, net, rollupBucket], queryFn: () => api.networkRollups(from, to, net, rollupBucket) });

  useEffect(() => {
    const socket = new WebSocket(websocketUrl("/ws/events"));
    socket.onopen = () => setEventsConnected(true);
    socket.onclose = () => setEventsConnected(false);
    socket.onerror = () => socket.close();
    socket.onmessage = event => {
      const next = JSON.parse(event.data) as EarthquakeEvent;
      queryClient.setQueryData<EarthquakeEvent[]>(["earthquakes", "live"], previous => {
        const withoutDuplicate = (previous ?? []).filter(item => item.event_id !== next.event_id);
        return [next, ...withoutDuplicate].slice(0, MAX_EVENTS);
      });
      if (!invalidateTimer.current) {
        invalidateTimer.current = window.setTimeout(() => {
          void queryClient.invalidateQueries({ queryKey: ["earthquakes"], exact: false });
          void queryClient.invalidateQueries({ queryKey: ["ingestion"], exact: false });
          invalidateTimer.current = undefined;
        }, 2000);
      }
    };
    return () => {
      socket.close();
      if (invalidateTimer.current) window.clearTimeout(invalidateTimer.current);
    };
  }, [queryClient]);

  useEffect(() => {
    const socket = new WebSocket(websocketUrl("/ws/alerts"));
    socket.onopen = () => setAlertsConnected(true);
    socket.onclose = () => setAlertsConnected(false);
    socket.onerror = () => socket.close();
    socket.onmessage = () => {
      void queryClient.invalidateQueries({ queryKey: ["anomalies"], exact: false });
      void queryClient.invalidateQueries({ queryKey: ["ingestion"], exact: false });
    };
    return () => socket.close();
  }, [queryClient]);

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
    eventsConnected,
    alertsConnected
  };
}
