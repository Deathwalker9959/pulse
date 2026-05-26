import type { AnomalyEvent } from "../api/client";

const SEVERITY_COLORS: Record<AnomalyEvent["severity"], string> = {
  INFO: "#3b82f6",
  WARNING: "#f59e0b",
  CRITICAL: "#ef4444",
};

interface Props {
  alerts: AnomalyEvent[];
  connected: boolean;
  onSelectFlight: (icao24: string) => void;
}

function WeatherBadge({ event }: { event: AnomalyEvent }) {
  if (!event.weather_fetched_at) return <span style={{ color: "#999", fontSize: 11 }}>fetching weather…</span>;
  return (
    <span style={{ fontSize: 11, color: "#555" }}>
      {event.weather_condition}
      {event.weather_wind_kts != null && ` · ${event.weather_wind_kts.toFixed(0)}kt`}
      {event.weather_temp_c != null && ` · ${event.weather_temp_c.toFixed(0)}°C`}
      {event.weather_visibility != null && ` · vis ${(event.weather_visibility / 1000).toFixed(1)}km`}
    </span>
  );
}

export function AlertFeed({ alerts, connected, onSelectFlight }: Props) {
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <strong>Live Alert Feed</strong>
        <span style={{
          fontSize: 11, padding: "2px 8px", borderRadius: 10,
          background: connected ? "#d1fae5" : "#fee2e2",
          color: connected ? "#065f46" : "#991b1b",
        }}>
          {connected ? "● live" : "○ reconnecting"}
        </span>
      </div>
      {alerts.length === 0 && (
        <p style={{ color: "#888", fontSize: 13, textAlign: "center", marginTop: 32 }}>
          No anomalies detected yet.
        </p>
      )}
      <div style={{ overflowY: "auto", flex: 1 }}>
        {alerts.map(a => (
          <div
            key={a.event_id}
            style={{
              borderLeft: `4px solid ${SEVERITY_COLORS[a.severity]}`,
              padding: "8px 10px",
              marginBottom: 6,
              background: "#fafafa",
              borderRadius: "0 4px 4px 0",
              cursor: a.icao24 !== "N/A" ? "pointer" : "default",
            }}
            onClick={() => a.icao24 !== "N/A" && onSelectFlight(a.icao24)}
          >
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
              <span style={{
                fontSize: 11, fontWeight: 600,
                color: SEVERITY_COLORS[a.severity],
                textTransform: "uppercase",
              }}>
                {a.severity} · {a.anomaly_type.replace(/_/g, " ")}
              </span>
              <span style={{ fontSize: 11, color: "#999" }}>
                {new Date(a.detected_at).toLocaleTimeString()}
              </span>
            </div>
            <div style={{ fontSize: 13 }}>{a.detail}</div>
            <div style={{ marginTop: 4 }}>
              <WeatherBadge event={a} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
