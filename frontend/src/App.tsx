import { Container, Stack } from "@mui/material";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type {
  AnomalyEvent,
  BucketSize,
  EarthquakeEvent,
  HeatmapCell,
  RangePreset,
} from "./api/client";
import { apiService } from "./api/service";
import {
  ActivityCharts,
  DashboardFilters,
  DashboardHeader,
  DashboardMetrics,
  MapSignalsPanel,
  SeismicAnalysis,
  TopSummaryGrid,
} from "./components/dashboard";
import { useDashboardData } from "./hooks/useDashboardData";
import { useFilters } from "./hooks/useFilters";
import {
  utcDateLabel,
  utcMonthYearLabel,
  utcTimeLabel,
  utcYearLabel,
} from "./utils/dates";

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
  const [mapView, setMapView] = useState<"globe" | "map">("globe");
  const [activeLayers, setActiveLayers] = useState<string[]>([
    "event-hexes",
    "event-nodes",
    "signal-nodes",
  ]);
  const [selectedEvent, setSelectedEvent] = useState<EarthquakeEvent | null>(
    null,
  );
  const [focusLatLon, setFocusLatLon] = useState<{
    lat: number;
    lon: number;
  } | null>(null);
  const [viewCenter, setViewCenter] = useState<{ lat: number; lon: number }>({
    lat: 20,
    lon: 0,
  });
  const [alertTypeFilter, setAlertTypeFilter] = useState("");

  function clearMapFocus() {
    setSelectedEvent(null);
    setFocusLatLon(null);
  }

  const {
    activeRange,
    from,
    to,
    net,
    plate,
    onPresetClick,
    onPickerChange,
    onNetChange,
    onPlateChange,
    clearFilters,
  } = useFilters(clearMapFocus);

  function handleTabChange(_: unknown, value: "globe" | "map") {
    setMapView(value);
  }

  function handleLayersChange(_: unknown, value: string[]) {
    setActiveLayers(value);
  }

  const bucket = useMemo(() => autoBucket(from, to), [from, to]);
  const rollupBucket: BucketSize = useMemo(() => {
    if (bucket === "1y" || bucket === "1mo" || bucket === "1d") return "1d";
    if (bucket === "6h") return "1h";
    return "5m";
  }, [bucket]);

  const platesQuery = useQuery({
    queryKey: ["earthquakes", "plates"],
    queryFn: () => apiService.plates(),
    staleTime: Infinity,
  });
  const data = useDashboardData(from, to, net, bucket, rollupBucket, plate);
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

    const match = events.find(
      (event) => event.event_id === alert.source_event_id,
    );
    if (match) {
      setSelectedEvent(match);
      setFocusLatLon(null);
    } else {
      setFocusLatLon({ lat: alert.latitude, lon: alert.longitude });
      setSelectedEvent(null);
    }
  }

  const filteredEvents = net
    ? events.filter((event) =>
        event.net.toLowerCase().includes(net.toLowerCase()),
      )
    : events;
  const selectedVisibleEvent =
    selectedEvent &&
    filteredEvents.some((event) => event.event_id === selectedEvent.event_id)
      ? selectedEvent
      : null;
  const filteredAlerts = useMemo(
    () =>
      alertTypeFilter
        ? alerts.filter((alert) => alert.anomaly_type === alertTypeFilter)
        : alerts,
    [alerts, alertTypeFilter],
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
        <DashboardHeader
          eventsConnected={data.eventsConnected}
          alertsConnected={data.alertsConnected}
        />

        <DashboardFilters
          activeRange={activeRange}
          from={from}
          to={to}
          net={net}
          plate={plate}
          networks={data.networks.data ?? []}
          plates={platesQuery.data ?? []}
          onPresetClick={onPresetClick}
          onPickerChange={onPickerChange}
          onNetChange={onNetChange}
          onPlateChange={onPlateChange}
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
