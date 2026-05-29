export interface EarthquakeEvent {
  event_id: string;
  time: string;
  updated: string;
  latitude: number;
  longitude: number;
  depth_km: number;
  magnitude: number;
  mag_type: string;
  place: string;
  event_type: string;
  status: string;
  alert: string;
  tsunami: boolean;
  significance: number;
  net: string;
  mag_band: string;
  depth_band: string;
}

export interface AnomalyEvent {
  anomaly_id: string;
  detected_at: string;
  event_time: string;
  anomaly_type: string;
  severity: "INFO" | "WARNING" | "CRITICAL";
  source_event_id: string;
  source_place: string;
  latitude: number;
  longitude: number;
  detail: string;
}

export interface TimeseriesBucket {
  time: string;
  event_count: number;
  avg_magnitude: number;
}

export interface TopItem {
  label: string;
  count: number;
}

export interface BandBucket {
  mag_band?: string;
  depth_band?: string;
  event_count: number;
}

export interface NetworkRollup {
  bucket: string;
  net: string;
  event_count: number;
  avg_magnitude: number;
  avg_depth_km: number;
}

export interface HeatmapCell {
  h3_index: string;
  event_count: number;
  max_magnitude: number;
  avg_magnitude: number;
  centroid_lat: number;
  centroid_lon: number;
}

export interface MagFrequencyBucket {
  mag_bin: number;
  event_count: number;
}

export interface EnergyBucket {
  bucket: string;
  energy_joules: number;
}

export interface BValueBucket {
  day: string;
  b_value: number;
  sample_size: number;
}

export interface IETBucket {
  bin_label: string;
  count: number;
}

export interface IngestionStatus {
  has_live_data: boolean;
  last_ingested_at: string | null;
  data_age_seconds: number | null;
  events_30min: number;
  events_2min: number;
  anomaly_24h: number;
  active_anomaly_types: string[];
  poll_interval_seconds: number;
}

async function get<T>(path: string, params?: Record<string, string | undefined>): Promise<T> {
  const url = new URL(path, window.location.href);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value) url.searchParams.set(key, value);
    });
  }
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json() as Promise<T>;
}

export type RangePreset = "1h" | "6h" | "24h" | "7d" | "30d" | "ytd";
export type BucketSize = "1m" | "5m" | "15m" | "1h" | "6h" | "1d" | "1mo" | "1y";

export const api = {
  live: (from?: string, to?: string, minMagnitude?: string) =>
    get<EarthquakeEvent[]>("/api/earthquakes/live", { from, to, min_magnitude: minMagnitude }),
  heatmap: (from: string, to: string, resolution = 3) =>
    get<HeatmapCell[]>("/api/earthquakes/heatmap", { from, to, resolution: String(resolution) }),
  timeseries: (from?: string, to?: string, bucket: BucketSize = "1h") =>
    get<TimeseriesBucket[]>("/api/earthquakes/timeseries", { bucket, from, to }),
  topNetworks: (from?: string, to?: string) => get<TopItem[]>("/api/earthquakes/top-networks", { from, to, limit: "10" }),
  topPlaces: (from?: string, to?: string) => get<TopItem[]>("/api/earthquakes/top-places", { from, to, limit: "10" }),
  magnitudeBands: (from?: string, to?: string) => get<BandBucket[]>("/api/earthquakes/magnitude-bands", { from, to }),
  depthBands: (from?: string, to?: string) => get<BandBucket[]>("/api/earthquakes/depth-bands", { from, to }),
  networkRollups: (from?: string, to?: string, net?: string, bucket: BucketSize = "5m") =>
    get<NetworkRollup[]>("/api/earthquakes/rollups/network", { bucket, from, to, net, limit: "500" }),
  anomalyHistory: (from?: string, to?: string) => get<AnomalyEvent[]>("/api/anomalies/history", { from, to, limit: "10000" }),
  ingestionStatus: () => get<IngestionStatus>("/api/ingestion/status"),
  magnitudeFrequency: (from: string, to: string) =>
    get<MagFrequencyBucket[]>("/api/earthquakes/magnitude-frequency", { from, to }),
  energyTimeseries: (from: string, to: string, bucket: BucketSize = "1d") =>
    get<EnergyBucket[]>("/api/earthquakes/energy-timeseries", { from, to, bucket }),
  bValueHistory: (from: string, to: string) =>
    get<BValueBucket[]>("/api/earthquakes/b-value-history", { from, to }),
  interEventTimes: (from: string, to: string) =>
    get<IETBucket[]>("/api/earthquakes/inter-event-times", { from, to })
};

export function websocketUrl(path: string): string {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${window.location.host}${path}`;
}

