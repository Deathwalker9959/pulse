import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";
import type { FlightLive, AnomalyEvent } from "../api/client";

// Fix Leaflet default icon path broken by bundlers.
delete (L.Icon.Default.prototype as unknown as Record<string, unknown>)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

function aircraftIcon(severity: string | undefined): L.Icon {
  const color = severity === "CRITICAL" ? "red" : severity === "WARNING" ? "orange" : "blue";
  const svg = encodeURIComponent(`
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20">
      <circle cx="10" cy="10" r="8" fill="${color}" opacity="0.85"/>
    </svg>
  `);
  return new L.Icon({
    iconUrl: `data:image/svg+xml,${svg}`,
    iconSize: [20, 20],
    iconAnchor: [10, 10],
  });
}

interface Props {
  flights: FlightLive[];
  anomalies: AnomalyEvent[];
  onSelect: (icao24: string) => void;
}

export function FlightMap({ flights, anomalies, onSelect }: Props) {
  // Build a quick severity lookup from active anomalies.
  const severityMap = new Map<string, AnomalyEvent["severity"]>();
  for (const a of anomalies) {
    const prev = severityMap.get(a.icao24);
    if (!prev || a.severity === "CRITICAL" || (a.severity === "WARNING" && prev === "INFO")) {
      severityMap.set(a.icao24, a.severity);
    }
  }

  return (
    <MapContainer
      center={[20, 0]}
      zoom={3}
      style={{ height: "100%", width: "100%" }}
      preferCanvas
    >
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://openstreetmap.org">OSM</a>'
      />
      {flights.map(f => (
        <Marker
          key={f.icao24}
          position={[f.latitude, f.longitude]}
          icon={aircraftIcon(severityMap.get(f.icao24))}
          eventHandlers={{ click: () => onSelect(f.icao24) }}
        >
          <Popup>
            <strong>{f.callsign || f.icao24}</strong>
            <br />{f.origin_country}
            <br />Alt: {f.baro_altitude?.toFixed(0)} m | {f.velocity?.toFixed(0)} m/s
            {severityMap.has(f.icao24) && (
              <><br /><span style={{ color: "red" }}>⚠ Active anomaly</span></>
            )}
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  );
}
