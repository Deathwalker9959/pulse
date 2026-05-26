const BASE = "";  // proxied through Vite dev server in dev; same-origin in prod

export interface FlightLive {
  icao24: string;
  callsign: string;
  origin_country: string;
  latitude: number;
  longitude: number;
  baro_altitude: number;
  on_ground: boolean;
  velocity: number;
  true_track: number;
  vertical_rate: number;
  squawk: string;
  last_contact: string;
}

export interface FlightPoint {
  time_position: string;
  latitude: number;
  longitude: number;
  baro_altitude: number;
  velocity: number;
  on_ground: boolean;
}

export interface HourlyBucket {
  hour: string;
  flight_count: number;
  avg_altitude: number;
  avg_velocity: number;
  airborne_count: number;
}

export interface TopNItem {
  label: string;
  count: number;
}

export interface DensityCell {
  lat: number;
  lon: number;
  count: number;
}

export interface AnomalyEvent {
  event_id: string;
  detected_at: string;
  anomaly_type: string;
  severity: "INFO" | "WARNING" | "CRITICAL";
  icao24: string;
  callsign: string;
  latitude: number;
  longitude: number;
  detail: string;
  weather_temp_c: number | null;
  weather_wind_kts: number | null;
  weather_condition: string | null;
  weather_visibility: number | null;
  weather_fetched_at: string | null;
}

async function get<T>(path: string, params?: Record<string, string>): Promise<T> {
  const url = new URL(BASE + path, window.location.href);
  if (params) Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  flights: {
    live: () => get<FlightLive[]>("/api/flights/live"),
    history: (icao24: string, from: string, to: string) =>
      get<FlightPoint[]>("/api/flights/history", { icao24, from, to }),
  },
  stats: {
    topN: (field: "origin_country" | "callsign", limit = 10, from?: string, to?: string) =>
      get<TopNItem[]>("/api/stats/top-n", {
        field, limit: String(limit),
        ...(from && { from }),
        ...(to && { to }),
      }),
    hourly: (from?: string, to?: string) =>
      get<HourlyBucket[]>("/api/stats/hourly", {
        ...(from && { from }),
        ...(to && { to }),
      }),
    density: (bbox: string, interval: "1h" | "6h" | "24h" = "1h") =>
      get<DensityCell[]>("/api/stats/density", { bbox, interval }),
  },
  anomalies: {
    history: (limit = 100) => get<AnomalyEvent[]>("/api/anomalies/history", { limit: String(limit) }),
  },
};
