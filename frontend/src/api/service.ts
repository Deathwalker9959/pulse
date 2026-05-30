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
  live: (
    from?: string,
    to?: string,
    minMagnitude?: string,
    plate?: string,
    net?: string,
  ) =>
    get<EarthquakeEvent[]>("/api/earthquakes/live", {
      from,
      to,
      min_magnitude: minMagnitude,
      plate,
      net,
    }),
  heatmap: (
    from: string,
    to: string,
    resolution = 3,
    plate?: string,
    net?: string,
  ) =>
    get<HeatmapCell[]>("/api/earthquakes/heatmap", {
      from,
      to,
      resolution: String(resolution),
      plate,
      net,
    }),
  timeseries: (
    from?: string,
    to?: string,
    bucket: BucketSize = "1h",
    plate?: string,
    net?: string,
  ) =>
    get<TimeseriesBucket[]>("/api/earthquakes/timeseries", {
      bucket,
      from,
      to,
      plate,
      net,
    }),
  topNetworks: (from?: string, to?: string, plate?: string, net?: string) =>
    get<TopItem[]>("/api/earthquakes/top-networks", {
      from,
      to,
      limit: "10",
      plate,
      net,
    }),
  topPlaces: (from?: string, to?: string, plate?: string, net?: string) =>
    get<TopItem[]>("/api/earthquakes/top-places", {
      from,
      to,
      limit: "10",
      plate,
      net,
    }),
  magnitudeBands: (from?: string, to?: string, plate?: string, net?: string) =>
    get<BandBucket[]>("/api/earthquakes/magnitude-bands", {
      from,
      to,
      plate,
      net,
    }),
  depthBands: (from?: string, to?: string, plate?: string, net?: string) =>
    get<BandBucket[]>("/api/earthquakes/depth-bands", { from, to, plate, net }),
  networkRollups: (
    from?: string,
    to?: string,
    net?: string,
    bucket: BucketSize = "5m",
    plate?: string,
  ) =>
    get<NetworkRollup[]>("/api/earthquakes/rollups/network", {
      bucket,
      from,
      to,
      net,
      limit: "5000",
      plate,
    }),
  anomalyHistory: (from?: string, to?: string, plate?: string, net?: string) =>
    get<AnomalyEvent[]>("/api/anomalies/history", {
      from,
      to,
      limit: "10000",
      plate,
      net,
    }),
  ingestionStatus: () => get<IngestionStatus>("/api/ingestion/status"),
  magnitudeFrequency: (
    from: string,
    to: string,
    plate?: string,
    net?: string,
  ) =>
    get<MagFrequencyBucket[]>("/api/earthquakes/magnitude-frequency", {
      from,
      to,
      plate,
      net,
    }),
  energyTimeseries: (
    from: string,
    to: string,
    bucket: BucketSize = "1d",
    plate?: string,
    net?: string,
  ) =>
    get<EnergyBucket[]>("/api/earthquakes/energy-timeseries", {
      from,
      to,
      bucket,
      plate,
      net,
    }),
  bValueHistory: (
    from: string,
    to: string,
    bucket: BucketSize = "1d",
    plate?: string,
    net?: string,
  ) =>
    get<BValueBucket[]>("/api/earthquakes/b-value-history", {
      from,
      to,
      bucket,
      plate,
      net,
    }),
  interEventTimes: (from: string, to: string, plate?: string, net?: string) =>
    get<IETBucket[]>("/api/earthquakes/inter-event-times", {
      from,
      to,
      plate,
      net,
    }),
  seismicRisk: (resolution = 2, plate?: string, net?: string) =>
    get<SeismicRiskCell[]>("/api/earthquakes/seismic-risk", {
      resolution: String(resolution),
      plate,
      net,
    }),
  plates: () => get<string[]>("/api/earthquakes/plates"),
};
