import { Box, Card, CardContent, Chip, Stack, Tab, Tabs, ToggleButton, ToggleButtonGroup, Typography } from "@mui/material";
import type { AnomalyEvent, EarthquakeEvent, HeatmapCell } from "../../api/client";
import { MapLibreView } from "../MapLibreView";
import { AlertFeed } from "./AlertFeed";

interface MapSignalsPanelProps {
  events: EarthquakeEvent[];
  heatmapCells: HeatmapCell[];
  alerts: AnomalyEvent[];
  filteredAlerts: AnomalyEvent[];
  isHeatmapMode: boolean;
  heatmapResolution: number;
  activeLayers: string[];
  mapView: "globe" | "map";
  selectedEvent: EarthquakeEvent | null;
  focusLatLon: { lat: number; lon: number } | null;
  viewCenter: { lat: number; lon: number };
  alertTypeFilter: string;
  onLayersChange: (_: unknown, value: string[]) => void;
  onMapViewChange: (_: unknown, value: "globe" | "map") => void;
  onSelectEvent: (event: EarthquakeEvent | null) => void;
  onViewChange: (lat: number, lon: number) => void;
  onAlertTypeFilter: (type: string) => void;
  onAlertClick: (alert: AnomalyEvent) => void;
}

export function MapSignalsPanel({
  events,
  heatmapCells,
  alerts,
  filteredAlerts,
  isHeatmapMode,
  heatmapResolution,
  activeLayers,
  mapView,
  selectedEvent,
  focusLatLon,
  viewCenter,
  alertTypeFilter,
  onLayersChange,
  onMapViewChange,
  onSelectEvent,
  onViewChange,
  onAlertTypeFilter,
  onAlertClick,
}: MapSignalsPanelProps) {
  return (
    <Box sx={{ display: "flex", gap: 2, flexDirection: { xs: "column", lg: "row" }, height: { lg: 618 } }}>
      <Box sx={{ flex: "2 1 0", minWidth: 0 }}>
        <Card variant="outlined">
          <CardContent>
            <Stack direction={{ xs: "column", lg: "row" }} justifyContent="space-between" alignItems={{ lg: "center" }} spacing={1.25} sx={{ mb: 1 }}>
              <Typography variant="h6">Live Epicentres</Typography>
              <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                <ToggleButtonGroup size="small" value={activeLayers} onChange={onLayersChange} aria-label="map layers">
                  <ToggleButton value="event-hexes" aria-label="event hexagons">Event hexes</ToggleButton>
                  <ToggleButton value="signal-hexes" aria-label="signal hexagons">Signal hexes</ToggleButton>
                  <ToggleButton value="event-nodes" aria-label="event nodes">Event nodes</ToggleButton>
                  <ToggleButton value="signal-nodes" aria-label="signal nodes">Signal nodes</ToggleButton>
                </ToggleButtonGroup>
                <Tabs value={mapView} onChange={onMapViewChange} aria-label="map view">
                  <Tab value="globe" label="Globe" />
                  <Tab value="map" label="Map" />
                </Tabs>
              </Stack>
            </Stack>
            <Box sx={{ height: 520 }}>
              <MapLibreView
                events={events}
                heatmapCells={isHeatmapMode ? heatmapCells : undefined}
                alerts={filteredAlerts}
                showEventHexes={activeLayers.includes("event-hexes")}
                showSignalHexes={activeLayers.includes("signal-hexes")}
                showEventNodes={activeLayers.includes("event-nodes")}
                showSignalNodes={activeLayers.includes("signal-nodes")}
                anomalyHexResolution={heatmapResolution}
                selectedEvent={selectedEvent}
                focusLatLon={focusLatLon}
                onSelect={onSelectEvent}
                initialCenter={viewCenter}
                onViewChange={onViewChange}
                projection={mapView === "globe" ? "globe" : "mercator"}
              />
            </Box>
          </CardContent>
        </Card>
      </Box>
      <Box sx={{ flex: "1 1 0", minWidth: 0, display: "flex", flexDirection: "column" }}>
        <Card variant="outlined" sx={{ flex: 1, display: "flex", flexDirection: "column" }}>
          <CardContent sx={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", "&:last-child": { pb: 2 } }}>
            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1.5, flexShrink: 0 }}>
              <Typography variant="h6">Detected Signals</Typography>
              {alertTypeFilter && (
                <Chip size="small" label="Clear filter" onClick={() => onAlertTypeFilter("")} onDelete={() => onAlertTypeFilter("")} />
              )}
            </Stack>
            <Box sx={{ flex: 1, minHeight: 0, overflowY: "auto" }}>
              <AlertFeed
                alerts={alerts}
                typeFilter={alertTypeFilter}
                onTypeFilter={onAlertTypeFilter}
                onAlertClick={onAlertClick}
                isHeatmapMode={isHeatmapMode}
                heatmapResolution={heatmapResolution}
              />
            </Box>
          </CardContent>
        </Card>
      </Box>
    </Box>
  );
}
