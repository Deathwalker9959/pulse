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
  last_poll_at: string | null;
  poll_age_seconds: number | null;
  events_30min: number;
  events_2min: number;
  anomaly_24h: number;
  active_anomaly_types: string[];
  poll_interval_seconds: number;
}

export interface SeismicRiskCell {
  h3_index: string;
  centroid_lat: number;
  centroid_lon: number;
  event_count: number;
  event_rate_7d: number;
  b_value: number | null;
  max_magnitude: number;
  risk_score: number;
}

export type RangePreset = "1h" | "6h" | "24h" | "7d" | "30d" | "ytd";
export type BucketSize = "1m" | "5m" | "15m" | "1h" | "6h" | "1d" | "1mo" | "1y";
