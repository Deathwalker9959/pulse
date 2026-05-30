import { Container, Stack } from "@mui/material";
import { useMemo, useState } from "react";
import type { AnomalyEvent, BucketSize, EarthquakeEvent, HeatmapCell, RangePreset } from "./api/client";
import {
  ActivityCharts,
  DashboardFilters,
  DashboardHeader,
  DashboardMetrics,
  MapSignalsPanel,
  SeismicAnalysis,
  TopSummaryGrid,
} from "./components/dashboard";
import { resolveRange, useDashboardData } from "./hooks/useDashboardData";
import { utcDateLabel, utcMonthYearLabel, utcTimeLabel, utcYearLabel } from "./utils/dates";

function autoBucket(from: string, to: string): BucketSize {
  const spanMs = new Date(to).getTime() - new Date(from).getTime();
  if (spanMs <= 3_600_000) return "5m";
  if (spanMs <= 6 * 3_600_000) return "15m";
  if (spanMs <= 24 * 3_600_000) return "1h";
  if (spanMs <= 7 * 86_400_000) return "6h";
  if (spanMs <= 30 * 86_400_000) return "1d";
  if (spanMs <= 365 * 86_400_000) return "1mo";
  return "1y";
}

export default function App() {
  const [activeRange, setActiveRange] = useState<RangePreset | null>("24h");
  const [from, setFrom] = useState(() => resolveRange("24h").from);
  const [to, setTo] = useState(() => resolveRange("24h").to);
  const [net, setNet] = useState("");
  const [mapView, setMapView] = useState<"globe" | "map">("globe");
  const [activeLayers, setActiveLayers] = useState<string[]>(["event-hexes", "event-nodes"]);
  const [selectedEvent, setSelectedEvent] = useState<EarthquakeEvent | null>(null);
  const [focusLatLon, setFocusLatLon] = useState<{ lat: number; lon: number } | null>(null);
  const [viewCenter, setViewCenter] = useState<{ lat: number; lon: number }>({ lat: 20, lon: 0 });
  const [alertTypeFilter, setAlertTypeFilter] = useState("");

  function handleTabChange(_: unknown, value: "globe" | "map") {
    setMapView(value);
  }

  function handleLayersChange(_: unknown, value: string[]) {
    setActiveLayers(value);
  }

  function clearMapFocus() {
    setSelectedEvent(null);
    setFocusLatLon(null);
  }

  function onPresetClick(preset: RangePreset) {
    const range = resolveRange(preset);
    setFrom(range.from);
    setTo(range.to);
    setActiveRange(preset);
    clearMapFocus();
  }

  function onPickerChange(newFrom: string, newTo: string) {
    setFrom(newFrom);
    setTo(newTo);
    setActiveRange(null);
    clearMapFocus();
  }

  function clearFilters() {
    setNet("");
    onPresetClick("24h");
  }

  const bucket = useMemo(() => autoBucket(from, to), [from, to]);
  const rollupBucket: BucketSize = useMemo(() => {
    if (bucket === "1y" || bucket === "1mo" || bucket === "1d") return "1d";
    if (bucket === "6h") return "1h";
    return "5m";
  }, [bucket]);

  const data = useDashboardData(from, to, net, bucket, rollupBucket);
  const events = data.live.data ?? [];
  const heatmapCells: HeatmapCell[] = data.heatmap.data ?? [];
  const isHeatmapMode = data.isHeatmapMode;
  const heatmapResolution = data.heatmapResolution;
  const alerts = data.alerts.data ?? [];

  function handleAlertClick(alert: AnomalyEvent) {
    if (isHeatmapMode) {
      setFocusLatLon({ lat: alert.latitude, lon: alert.longitude });
      setSelectedEvent(null);
      return;
    }

    const match = events.find(event => event.event_id === alert.source_event_id);
    if (match) {
      setSelectedEvent(match);
      setFocusLatLon(null);
    } else {
      setFocusLatLon({ lat: alert.latitude, lon: alert.longitude });
      setSelectedEvent(null);
    }
  }

  const filteredEvents = net ? events.filter(event => event.net.toLowerCase().includes(net.toLowerCase())) : events;
  const selectedVisibleEvent = selectedEvent && filteredEvents.some(event => event.event_id === selectedEvent.event_id)
    ? selectedEvent
    : null;
  const filteredAlerts = useMemo(
    () => alertTypeFilter ? alerts.filter(alert => alert.anomaly_type === alertTypeFilter) : alerts,
    [alerts, alertTypeFilter]
  );

  function xLabel(isoTime: string): string {
    if (bucket === "1y") return utcYearLabel(isoTime);
    if (bucket === "1mo") return utcMonthYearLabel(isoTime);
    if (bucket === "1d" || bucket === "6h") return utcDateLabel(isoTime);
    return utcTimeLabel(isoTime);
  }

  return (
    <Container maxWidth={false} sx={{ py: 3 }}>
      <Stack spacing={3}>
        <DashboardHeader eventsConnected={data.eventsConnected} alertsConnected={data.alertsConnected} />

        <DashboardFilters
          activeRange={activeRange}
          from={from}
          to={to}
          net={net}
          networks={data.networks.data ?? []}
          onPresetClick={onPresetClick}
          onPickerChange={onPickerChange}
          onNetChange={setNet}
          onClear={clearFilters}
        />

        <DashboardMetrics
          isHeatmapMode={isHeatmapMode}
          heatmapCellCount={heatmapCells.length}
          visibleEventCount={filteredEvents.length}
          events30Min={data.status.data?.events_30min ?? 0}
          signals24h={data.status.data?.anomaly_24h ?? 0}
          dataAgeSeconds={data.status.data?.data_age_seconds}
          pollAgeSeconds={data.status.data?.poll_age_seconds}
        />

        <MapSignalsPanel
          events={filteredEvents}
          heatmapCells={heatmapCells}
          riskCells={data.seismicRisk.data ?? []}
          alerts={alerts}
          filteredAlerts={filteredAlerts}
          isHeatmapMode={isHeatmapMode}
          heatmapResolution={heatmapResolution}
          activeLayers={activeLayers}
          mapView={mapView}
          selectedEvent={selectedVisibleEvent}
          focusLatLon={focusLatLon}
          viewCenter={viewCenter}
          alertTypeFilter={alertTypeFilter}
          onLayersChange={handleLayersChange}
          onMapViewChange={handleTabChange}
          onSelectEvent={setSelectedEvent}
          onViewChange={(lat, lon) => setViewCenter({ lat, lon })}
          onAlertTypeFilter={setAlertTypeFilter}
          onAlertClick={handleAlertClick}
        />

        <ActivityCharts
          bucket={bucket}
          timeseries={data.timeseries.data ?? []}
          rollups={data.rollups.data ?? []}
          xLabel={xLabel}
        />

        <TopSummaryGrid
          networks={data.networks.data ?? []}
          places={data.places.data ?? []}
          magnitudeBands={data.magnitudeBands.data ?? []}
          depthBands={data.depthBands.data ?? []}
        />

        <SeismicAnalysis
          magnitudeFrequency={data.magnitudeFrequency.data ?? []}
          energyTimeseries={data.energyTimeseries.data ?? []}
          bValueHistory={data.bValueHistory.data ?? []}
          interEventTimes={data.interEventTimes.data ?? []}
          xLabel={xLabel}
        />
      </Stack>
    </Container>
  );
}
