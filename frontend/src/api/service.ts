import { get } from "./apiClient";
import type {
  AnomalyEvent,
  BValueBucket,
  BandBucket,
  BucketSize,
  EarthquakeEvent,
  EnergyBucket,
  HeatmapCell,
  IETBucket,
  IngestionStatus,
  MagFrequencyBucket,
  NetworkRollup,
  SeismicRiskCell,
  TimeseriesBucket,
  TopItem,
} from "./client";

export const apiService = {
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
    get<IETBucket[]>("/api/earthquakes/inter-event-times", { from, to }),
  seismicRisk: (resolution = 2) =>
    get<SeismicRiskCell[]>("/api/earthquakes/seismic-risk", { resolution: String(resolution) }),
};
