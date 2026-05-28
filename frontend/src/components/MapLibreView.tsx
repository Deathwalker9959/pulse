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

function cellPopupHTML(cell: HeatmapCell): string {
  return (
    `<strong>${cell.event_count.toLocaleString()} events</strong><br/>` +
    `Max M${cell.max_magnitude.toFixed(1)} · Avg M${cell.avg_magnitude.toFixed(1)}`
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
}: Props) {
  const hostRef        = useRef<HTMLDivElement | null>(null);
  const mapRef         = useRef<maplibregl.Map | null>(null);
  const isLoadedRef    = useRef(false);
  const popupRef       = useRef<maplibregl.Popup | null>(null);

  const eventsRef      = useRef(events);
  const heatmapRef     = useRef(heatmapCells);
  const onSelectRef    = useRef(onSelect);
  const onViewChangeRef = useRef(onViewChange);
  const alertIdsRef    = useRef(new Set<string>());

  useEffect(() => { eventsRef.current = events; });
  useEffect(() => { heatmapRef.current = heatmapCells; });
  useEffect(() => { onSelectRef.current = onSelect; });
  useEffect(() => { onViewChangeRef.current = onViewChange; });

  const alertIds = useMemo(() => new Set(alerts.map(a => a.source_event_id)), [alerts]);
  useEffect(() => { alertIdsRef.current = alertIds; }, [alertIds]);

  function pushData(map: maplibregl.Map) {
    const cells = heatmapRef.current ?? [];
    const maxCount = Math.max(...cells.map(c => c.event_count), 1);
    const isHeatmap = cells.length > 0;

    (map.getSource("events") as maplibregl.GeoJSONSource | undefined)
      ?.setData(buildEventsGeoJSON(eventsRef.current, alertIdsRef.current));
    (map.getSource("heatmap") as maplibregl.GeoJSONSource | undefined)
      ?.setData(buildHeatmapGeoJSON(cells, maxCount));

    if (map.getLayer("heatmap-fill")) {
      map.setLayoutProperty("heatmap-fill",    "visibility", isHeatmap ? "visible" : "none");
      map.setLayoutProperty("heatmap-outline", "visibility", isHeatmap ? "visible" : "none");
      map.setLayoutProperty("events-circles",  "visibility", isHeatmap ? "none" : "visible");
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

      // ── Heatmap cell click ───────────────────────────────────────────────
      map.on("click", "heatmap-fill", e => {
        if (!e.features?.length) return;
        const props = e.features[0].properties as Record<string, unknown>;
        const cell = heatmapRef.current?.find(c => c.h3_index.replace(/^0/, "") === String(props.h3_index).replace(/^0/, ""));
        popupRef.current?.remove();
        popupRef.current = new maplibregl.Popup({ closeButton: true, maxWidth: "240px" })
          .setLngLat(e.lngLat)
          .setHTML(cell ? cellPopupHTML(cell) :
            `<strong>${Number(props.event_count).toLocaleString()} events</strong><br/>` +
            `Max M${Number(props.max_magnitude).toFixed(1)} · Avg M${Number(props.avg_magnitude).toFixed(1)}`
          )
          .addTo(map);
      });

      map.on("mouseenter", "events-circles", () => { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", "events-circles", () => { map.getCanvas().style.cursor = "";          });
      map.on("mouseenter", "heatmap-fill",   () => { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", "heatmap-fill",   () => { map.getCanvas().style.cursor = "";          });

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
  }, [events, heatmapCells, alertIds]); // eslint-disable-line react-hooks/exhaustive-deps

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
            .setHTML(cellPopupHTML(cell))
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
