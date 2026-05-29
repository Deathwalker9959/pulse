import { useEffect, useMemo, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { cellToBoundary, getResolution, latLngToCell } from "h3-js";
import { Box } from "@mui/material";
import type { AnomalyEvent, EarthquakeEvent, HeatmapCell } from "../api/client";

const STYLE_URL = "https://tiles.openfreemap.org/styles/liberty";
const TECTONIC_URL =
  "https://raw.githubusercontent.com/fraxen/tectonicplates/master/GeoJSON/PB2002_boundaries.json";


function eventColor(mag: number, isAlert: boolean): string {
  if (isAlert) return "#dc2626";
  if (mag >= 5) return "#f97316";
  if (mag >= 3) return "#ca8a04";
  return "#16a34a";
}

function anomalyColor(severity: AnomalyEvent["severity"]): string {
  if (severity === "CRITICAL") return "#dc2626";
  if (severity === "WARNING") return "#f97316";
  return "#2563eb";
}

function severityRank(severity: AnomalyEvent["severity"]): number {
  if (severity === "CRITICAL") return 0;
  if (severity === "WARNING") return 1;
  return 2;
}

function buildEventsGeoJSON(events: EarthquakeEvent[], alertIds: Set<string>) {
  return {
    type: "FeatureCollection" as const,
    features: events.map(ev => ({
      type: "Feature" as const,
      geometry: { type: "Point" as const, coordinates: [ev.longitude, ev.latitude] },
      properties: {
        id: ev.event_id,
        magnitude: ev.magnitude,
        place: ev.place ?? "",
        depth_km: ev.depth_km,
        time: ev.time,
        net: ev.net ?? "",
        is_alert: alertIds.has(ev.event_id) ? 1 : 0,
        color: eventColor(ev.magnitude, alertIds.has(ev.event_id)),
        radius: Math.max(5, Math.min(22, 3 + ev.magnitude * 2.8)),
      },
    })),
  };
}

function buildAnomalyNodesGeoJSON(alerts: AnomalyEvent[]) {
  return {
    type: "FeatureCollection" as const,
    features: alerts.map(alert => ({
      type: "Feature" as const,
      geometry: { type: "Point" as const, coordinates: [alert.longitude, alert.latitude] },
      properties: {
        id: alert.anomaly_id,
        source_event_id: alert.source_event_id,
        anomaly_type: alert.anomaly_type,
        severity: alert.severity,
        place: alert.source_place ?? "",
        detail: alert.detail,
        time: alert.event_time,
        color: anomalyColor(alert.severity),
        radius: alert.severity === "CRITICAL" ? 12 : alert.severity === "WARNING" ? 10 : 8,
      },
    })),
  };
}

function buildHeatmapGeoJSON(cells: HeatmapCell[], maxCount: number) {
  const features: object[] = [];
  for (const cell of cells) {
    try {
      const boundary = cellToBoundary(cell.h3_index) as [number, number][];
      const lons = boundary.map(([, lon]) => lon);
      if (Math.max(...lons) - Math.min(...lons) > 180) continue;
      const ring = [...boundary.map(([lat, lon]) => [lon, lat]), [boundary[0][1], boundary[0][0]]];
      const opacity = Math.min(0.82, 0.18 + (cell.event_count / maxCount) * 0.64);
      const color =
        cell.max_magnitude >= 6 ? "#dc2626" :
        cell.max_magnitude >= 5 ? "#f97316" :
        cell.max_magnitude >= 3 ? "#ca8a04" : "#16a34a";
      features.push({
        type: "Feature",
        geometry: { type: "Polygon", coordinates: [ring] },
        properties: {
          event_count: cell.event_count,
          max_magnitude: cell.max_magnitude,
          avg_magnitude: cell.avg_magnitude,
          centroid_lat: cell.centroid_lat,
          centroid_lon: cell.centroid_lon,
          h3_index: cell.h3_index,
          fill_opacity: opacity,
          color,
        },
      });
    } catch { /* skip bad cell */ }
  }
  return { type: "FeatureCollection" as const, features } as Parameters<maplibregl.GeoJSONSource["setData"]>[0];
}

function buildAnomalyHexGeoJSON(alerts: AnomalyEvent[], resolution: number) {
  const byCell = new Map<string, AnomalyEvent[]>();
  for (const alert of alerts) {
    try {
      const key = latLngToCell(alert.latitude, alert.longitude, resolution);
      if (!byCell.has(key)) byCell.set(key, []);
      byCell.get(key)!.push(alert);
    } catch { /* skip bad alert coordinates */ }
  }

  const maxCount = Math.max(...Array.from(byCell.values(), group => group.length), 1);
  const features: object[] = [];
  for (const [h3Index, group] of byCell.entries()) {
    try {
      const boundary = cellToBoundary(h3Index) as [number, number][];
      const lons = boundary.map(([, lon]) => lon);
      if (Math.max(...lons) - Math.min(...lons) > 180) continue;
      const ring = [...boundary.map(([lat, lon]) => [lon, lat]), [boundary[0][1], boundary[0][0]]];
      const top = [...group].sort((a, b) => severityRank(a.severity) - severityRank(b.severity))[0];
      const typeCount = new Set(group.map(item => item.anomaly_type)).size;
      features.push({
        type: "Feature",
        geometry: { type: "Polygon", coordinates: [ring] },
        properties: {
          signal_count: group.length,
          anomaly_types: typeCount,
          h3_index: h3Index,
          top_severity: top.severity,
          top_type: top.anomaly_type,
          fill_opacity: Math.min(0.82, 0.18 + (group.length / maxCount) * 0.64),
          color: anomalyColor(top.severity),
        },
      });
    } catch { /* skip bad cell */ }
  }
  return { type: "FeatureCollection" as const, features } as Parameters<maplibregl.GeoJSONSource["setData"]>[0];
}

function utcLabel(iso: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "UTC", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false, timeZoneName: "short",
  }).format(new Date(iso));
}

function eventPopupHTML(ev: EarthquakeEvent): string {
  return (
    `<strong>M${ev.magnitude.toFixed(1)} ${ev.place || "Unknown"}</strong><br/>` +
    `Depth ${ev.depth_km.toFixed(1)} km · ${ev.net || "?"}<br/>` +
    `<span style="font-size:0.78em;color:#64748b">${utcLabel(ev.time)}</span>`
  );
}

function cellPopupHTML(count: number, maxMag: number, avgMag: number): string {
  return `<strong>${count.toLocaleString()} events</strong><br/>Max M${maxMag.toFixed(1)} · Avg M${avgMag.toFixed(1)}`;
}

function addCursorPointer(map: maplibregl.Map, layerId: string): void {
  map.on("mouseenter", layerId, () => { map.getCanvas().style.cursor = "pointer"; });
  map.on("mouseleave", layerId, () => { map.getCanvas().style.cursor = ""; });
}

function anomalyPopupHTML(alert: AnomalyEvent): string {
  const displayTime = alert.event_time && new Date(alert.event_time).getFullYear() > 2000
    ? alert.event_time
    : alert.detected_at;
  return (
    `<strong>${alert.anomaly_type.replaceAll("_", " ")}</strong><br/>` +
    `${alert.severity} · ${alert.source_place || "Unknown"}<br/>` +
    `<span>${alert.detail}</span><br/>` +
    `<span style="font-size:0.78em;color:#64748b">${utcLabel(displayTime)}</span>`
  );
}

function anomalyHexPopupHTML(props: Record<string, unknown>): string {
  return (
    `<strong>${Number(props.signal_count).toLocaleString()} signals</strong><br/>` +
    `${String(props.top_type).replaceAll("_", " ")} · ${String(props.top_severity)}<br/>` +
    `<span style="font-size:0.78em;color:#64748b">${Number(props.anomaly_types).toLocaleString()} signal types</span>`
  );
}

interface Props {
  events: EarthquakeEvent[];
  heatmapCells?: HeatmapCell[];
  alerts: AnomalyEvent[];
  selectedEvent?: EarthquakeEvent | null;
  focusLatLon?: { lat: number; lon: number } | null;
  onSelect?: (event: EarthquakeEvent) => void;
  initialCenter?: { lat: number; lon: number };
  onViewChange?: (lat: number, lon: number) => void;
  projection?: "globe" | "mercator";
  initialZoom?: number;
  showEventHexes?: boolean;
  showSignalHexes?: boolean;
  showEventNodes?: boolean;
  showSignalNodes?: boolean;
  anomalyHexResolution?: number;
}

export function MapLibreView({
  events,
  heatmapCells,
  alerts,
  selectedEvent,
  focusLatLon,
  onSelect,
  initialCenter,
  onViewChange,
  projection = "globe",
  initialZoom = 2,
  showEventHexes = true,
  showSignalHexes = false,
  showEventNodes = true,
  showSignalNodes = false,
  anomalyHexResolution = 3,
}: Props) {
  const hostRef        = useRef<HTMLDivElement | null>(null);
  const mapRef         = useRef<maplibregl.Map | null>(null);
  const isLoadedRef    = useRef(false);
  const popupRef       = useRef<maplibregl.Popup | null>(null);

  const eventsRef      = useRef(events);
  const heatmapRef     = useRef(heatmapCells);
  const alertsRef      = useRef(alerts);
  const onSelectRef    = useRef(onSelect);
  const onViewChangeRef = useRef(onViewChange);
  const alertIdsRef    = useRef(new Set<string>());

  useEffect(() => { eventsRef.current = events; });
  useEffect(() => { heatmapRef.current = heatmapCells; });
  useEffect(() => { alertsRef.current = alerts; });
  useEffect(() => { onSelectRef.current = onSelect; });
  useEffect(() => { onViewChangeRef.current = onViewChange; });

  const alertIds = useMemo(() => new Set(alerts.map(a => a.source_event_id)), [alerts]);
  useEffect(() => { alertIdsRef.current = alertIds; }, [alertIds]);

  function pushData(map: maplibregl.Map) {
    const cells = heatmapRef.current ?? [];
    const maxCount = Math.max(...cells.map(c => c.event_count), 1);
    const eventHexesVisible = showEventHexes && cells.length > 0;
    const signalHexesVisible = showSignalHexes && alertsRef.current.length > 0;

    (map.getSource("events") as maplibregl.GeoJSONSource | undefined)
      ?.setData(buildEventsGeoJSON(eventsRef.current, alertIdsRef.current));
    (map.getSource("anomaly-nodes") as maplibregl.GeoJSONSource | undefined)
      ?.setData(buildAnomalyNodesGeoJSON(alertsRef.current));
    (map.getSource("heatmap") as maplibregl.GeoJSONSource | undefined)
      ?.setData(buildHeatmapGeoJSON(cells, maxCount));
    (map.getSource("anomaly-hexes") as maplibregl.GeoJSONSource | undefined)
      ?.setData(buildAnomalyHexGeoJSON(alertsRef.current, anomalyHexResolution));

    if (map.getLayer("heatmap-fill")) {
      map.setLayoutProperty("heatmap-fill", "visibility", eventHexesVisible ? "visible" : "none");
      map.setLayoutProperty("heatmap-outline", "visibility", eventHexesVisible ? "visible" : "none");
      map.setLayoutProperty("anomaly-hex-fill", "visibility", signalHexesVisible ? "visible" : "none");
      map.setLayoutProperty("anomaly-hex-outline", "visibility", signalHexesVisible ? "visible" : "none");
      map.setLayoutProperty("events-circles", "visibility", showEventNodes ? "visible" : "none");
      map.setLayoutProperty("anomaly-circles", "visibility", showSignalNodes ? "visible" : "none");
    }
  }

  // ── Init map (once) ────────────────────────────────────────────────────────
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    const map = new maplibregl.Map({
      container: host,
      style: STYLE_URL,
      center: [initialCenter?.lon ?? 0, initialCenter?.lat ?? 20],
      zoom: initialZoom,
      attributionControl: false,
    });
    mapRef.current = map;

    map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-left");
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    map.on("load", () => {
      isLoadedRef.current = true;

      map.setProjection({ type: projection === "globe" ? "globe" : "mercator" });

      // ── Tectonic plates ──────────────────────────────────────────────────
      map.addSource("tectonic", { type: "geojson", data: TECTONIC_URL });
      map.addLayer({
        id: "tectonic-lines",
        type: "line",
        source: "tectonic",
        paint: { "line-color": "#fb923c", "line-width": 1.5, "line-opacity": 0.65 },
      });

      // ── Heatmap polygons ─────────────────────────────────────────────────
      map.addSource("heatmap", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({
        id: "heatmap-fill",
        type: "fill",
        source: "heatmap",
        layout: { visibility: "none" },
        paint: { "fill-color": ["get", "color"], "fill-opacity": ["get", "fill_opacity"] },
      });
      map.addLayer({
        id: "heatmap-outline",
        type: "line",
        source: "heatmap",
        layout: { visibility: "none" },
        paint: { "line-color": ["get", "color"], "line-width": 1, "line-opacity": 0.45 },
      });

      // ── Anomaly distribution polygons ────────────────────────────────────
      map.addSource("anomaly-hexes", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({
        id: "anomaly-hex-fill",
        type: "fill",
        source: "anomaly-hexes",
        layout: { visibility: "none" },
        paint: { "fill-color": ["get", "color"], "fill-opacity": ["get", "fill_opacity"] },
      });
      map.addLayer({
        id: "anomaly-hex-outline",
        type: "line",
        source: "anomaly-hexes",
        layout: { visibility: "none" },
        paint: { "line-color": ["get", "color"], "line-width": 1.4, "line-opacity": 0.55 },
      });

      // ── Event circles ────────────────────────────────────────────────────
      map.addSource("events", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({
        id: "events-circles",
        type: "circle",
        source: "events",
        paint: {
          "circle-radius": ["get", "radius"],
          "circle-color": ["get", "color"],
          "circle-opacity": 0.75,
          "circle-stroke-width": ["case", ["==", ["get", "is_alert"], 1], 2.5, 1],
          "circle-stroke-color": "#ffffff",
          "circle-stroke-opacity": 0.9,
        },
      });

      // ── Anomaly nodes ────────────────────────────────────────────────────
      map.addSource("anomaly-nodes", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({
        id: "anomaly-circles",
        type: "circle",
        source: "anomaly-nodes",
        layout: { visibility: "none" },
        paint: {
          "circle-radius": ["get", "radius"],
          "circle-color": ["get", "color"],
          "circle-opacity": 0.86,
          "circle-stroke-width": 2,
          "circle-stroke-color": "#ffffff",
          "circle-stroke-opacity": 0.95,
        },
      });

      pushData(map);

      // ── Event click ──────────────────────────────────────────────────────
      map.on("click", "events-circles", e => {
        if (!e.features?.length) return;
        const props = e.features[0].properties as Record<string, unknown>;
        const ev = eventsRef.current.find(x => x.event_id === props.id);
        if (ev) {
          onSelectRef.current?.(ev);
          popupRef.current?.remove();
          const [lng, lat] = (e.features[0].geometry as { coordinates: number[] }).coordinates;
          popupRef.current = new maplibregl.Popup({ closeButton: true, maxWidth: "260px" })
            .setLngLat([lng, lat])
            .setHTML(eventPopupHTML(ev))
            .addTo(map);
        }
      });

      // ── Anomaly node click ───────────────────────────────────────────────
      map.on("click", "anomaly-circles", e => {
        if (!e.features?.length) return;
        const props = e.features[0].properties as Record<string, unknown>;
        const alert = alertsRef.current.find(x => x.anomaly_id === props.id);
        if (alert) {
          popupRef.current?.remove();
          const [lng, lat] = (e.features[0].geometry as { coordinates: number[] }).coordinates;
          popupRef.current = new maplibregl.Popup({ closeButton: true, maxWidth: "280px" })
            .setLngLat([lng, lat])
            .setHTML(anomalyPopupHTML(alert))
            .addTo(map);
        }
      });

      // ── Heatmap cell click ───────────────────────────────────────────────
      map.on("click", "heatmap-fill", e => {
        if (!e.features?.length) return;
        const props = e.features[0].properties as Record<string, unknown>;
        const cell = heatmapRef.current?.find(c => c.h3_index.replace(/^0/, "") === String(props.h3_index).replace(/^0/, ""));
        popupRef.current?.remove();
        popupRef.current = new maplibregl.Popup({ closeButton: true, maxWidth: "240px" })
          .setLngLat(e.lngLat)
          .setHTML(cellPopupHTML(
            cell?.event_count ?? Number(props.event_count),
            cell?.max_magnitude ?? Number(props.max_magnitude),
            cell?.avg_magnitude ?? Number(props.avg_magnitude),
          ))
          .addTo(map);
      });

      // ── Anomaly hex click ────────────────────────────────────────────────
      map.on("click", "anomaly-hex-fill", e => {
        if (!e.features?.length) return;
        const props = e.features[0].properties as Record<string, unknown>;
        popupRef.current?.remove();
        popupRef.current = new maplibregl.Popup({ closeButton: true, maxWidth: "240px" })
          .setLngLat(e.lngLat)
          .setHTML(anomalyHexPopupHTML(props))
          .addTo(map);
      });

      addCursorPointer(map, "events-circles");
      addCursorPointer(map, "anomaly-circles");
      addCursorPointer(map, "heatmap-fill");
      addCursorPointer(map, "anomaly-hex-fill");

      map.on("moveend", () => {
        const c = map.getCenter();
        onViewChangeRef.current?.(c.lat, c.lng);
      });
    });

    return () => {
      isLoadedRef.current = false;
      popupRef.current?.remove();
      map.remove();
      mapRef.current = null;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Projection toggle (no remount) ─────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isLoadedRef.current) return;
    map.setProjection({ type: projection === "globe" ? "globe" : "mercator" });
  }, [projection]);

  // ── Data updates ───────────────────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isLoadedRef.current) return;
    pushData(map);
  }, [events, heatmapCells, alertIds, alerts, showEventHexes, showSignalHexes, showEventNodes, showSignalNodes, anomalyHexResolution]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── FlyTo + popup for selected event ──────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !selectedEvent) return;
    popupRef.current?.remove();
    popupRef.current = new maplibregl.Popup({ closeButton: true, maxWidth: "260px" })
      .setLngLat([selectedEvent.longitude, selectedEvent.latitude])
      .setHTML(eventPopupHTML(selectedEvent))
      .addTo(map);
    map.flyTo({ center: [selectedEvent.longitude, selectedEvent.latitude], zoom: Math.max(map.getZoom(), 5), duration: 1200 });
  }, [selectedEvent]);

  // ── FlyTo + popup for heatmap cell focus ──────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !focusLatLon) return;
    const cells = heatmapRef.current ?? [];
    if (cells.length > 0) {
      try {
        const res = getResolution(cells[0].h3_index);
        const idx = latLngToCell(focusLatLon.lat, focusLatLon.lon, res).replace(/^0/, "");
        const cell = cells.find(c => c.h3_index.replace(/^0/, "") === idx);
        if (cell) {
          popupRef.current?.remove();
          popupRef.current = new maplibregl.Popup({ closeButton: true, maxWidth: "240px" })
            .setLngLat([focusLatLon.lon, focusLatLon.lat])
            .setHTML(cellPopupHTML(cell.event_count, cell.max_magnitude, cell.avg_magnitude))
            .addTo(map);
        }
      } catch { /* */ }
    }
    map.flyTo({ center: [focusLatLon.lon, focusLatLon.lat], zoom: Math.max(map.getZoom(), 5), duration: 1200 });
  }, [focusLatLon]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Box
      ref={hostRef}
      sx={{
        height: "100%", minHeight: 520,
        "& .maplibregl-canvas": { borderRadius: 0 },
        "& .maplibregl-map": { borderRadius: 1 },
      }}
    />
  );
}
