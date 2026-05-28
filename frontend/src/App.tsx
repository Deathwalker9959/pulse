import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Container,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Tab,
  Tabs,
  Typography
} from "@mui/material";
import PublicIcon from "@mui/icons-material/Public";
import SensorsIcon from "@mui/icons-material/Sensors";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import { latLngToCell } from "h3-js";
import type { EarthquakeEvent } from "./api/client";
import { useDashboardData, resolveRange } from "./hooks/useDashboardData";
import { MapLibreView } from "./components/MapLibreView";
import { RangePickerButton } from "./components/RangePickerButton";
import type { AnomalyEvent, BandBucket, BucketSize, HeatmapCell, RangePreset, TopItem } from "./api/client";

const PRESET_LABELS: { label: string; value: RangePreset }[] = [
  { label: "1H",  value: "1h"  },
  { label: "6H",  value: "6h"  },
  { label: "24H", value: "24h" },
  { label: "7D",  value: "7d"  },
  { label: "30D", value: "30d" },
  { label: "YTD", value: "ytd" },
];

function ConnectionChip({ label, connected }: { label: string; connected: boolean }) {
  return <Chip size="small" color={connected ? "success" : "default"} label={`${label}: ${connected ? "live" : "connecting"}`} />;
}

function MetricCard({ title, value, icon }: { title: string; value: string; icon: ReactNode }) {
  return (
    <Card variant="outlined">
      <CardContent>
        <Stack direction="row" alignItems="center" spacing={1}>
          {icon}
          <Typography color="text.secondary" variant="body2">{title}</Typography>
        </Stack>
        <Typography variant="h4" sx={{ mt: 1 }}>{value}</Typography>
      </CardContent>
    </Card>
  );
}

const ANOMALY_TYPE_LABEL: Record<string, string> = {
  SIGNIFICANT_EVENT:   "Significant",
  TSUNAMI_ALERT:       "Tsunami Alert",
  TSUNAMI_RISK:        "Tsunami Risk",
  MAGNITUDE_SPIKE:     "Mag Spike",
  SWARM_DETECTION:     "Swarm",
  ENERGY_BURST:        "Energy Burst",
  AFTERSHOCK_CASCADE:  "Aftershock",
  GLOBAL_RATE_SPIKE:   "Rate Spike",
  SEISMIC_QUIESCENCE:  "Quiescence",
  B_VALUE_ANOMALY:     "B-Value",
  DEEP_FOCUS_CLUSTER:  "Deep Focus",
  DATA_QUALITY_ANOMALY:"Data Quality",
  FORESHOCK_SEQUENCE:  "Foreshock Seq",
};

const SEVERITY_CHIP_COLOR = {
  CRITICAL: "error",
  WARNING:  "warning",
  INFO:     "info",
} as const;

const SEVERITY_BORDER = {
  CRITICAL: "error.main",
  WARNING:  "warning.main",
  INFO:     "info.main",
} as const;

const SEV_ORDER: Record<string, number> = { CRITICAL: 0, WARNING: 1, INFO: 2 };

function AlertFeed({
  alerts,
  typeFilter,
  onTypeFilter,
  onAlertClick,
  isHeatmapMode = false,
  heatmapResolution = 3,
}: {
  alerts: AnomalyEvent[];
  typeFilter: string;
  onTypeFilter: (t: string) => void;
  onAlertClick: (alert: AnomalyEvent) => void;
  isHeatmapMode?: boolean;
  heatmapResolution?: number;
}) {
  const typeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const a of alerts) counts[a.anomaly_type] = (counts[a.anomaly_type] ?? 0) + 1;
    return counts;
  }, [alerts]);

  const visible = typeFilter ? alerts.filter(a => a.anomaly_type === typeFilter) : alerts;

  const clusters = useMemo(() => {
    if (!isHeatmapMode) return null;
    const byCell = new Map<string, AnomalyEvent[]>();
    for (const a of visible) {
      try {
        const key = latLngToCell(a.latitude, a.longitude, heatmapResolution).replace(/^0/, "");
        if (!byCell.has(key)) byCell.set(key, []);
        byCell.get(key)!.push(a);
      } catch { /* */ }
    }
    return Array.from(byCell.values())
      .map(group => {
        group.sort((a, b) => (SEV_ORDER[a.severity] ?? 2) - (SEV_ORDER[b.severity] ?? 2));
        return { top: group[0], count: group.length };
      })
      .sort((a, b) => {
        const sd = (SEV_ORDER[a.top.severity] ?? 2) - (SEV_ORDER[b.top.severity] ?? 2);
        return sd !== 0 ? sd : b.count - a.count;
      });
  }, [visible, isHeatmapMode, heatmapResolution]);

  const alertRow = (alert: AnomalyEvent, key: string, countBadge?: number) => (
    <Box
      key={key}
      onClick={() => onAlertClick(alert)}
      sx={{
        borderLeft: 4,
        borderColor: SEVERITY_BORDER[alert.severity] ?? "warning.main",
        pl: 1.5, py: 0.5, cursor: "pointer",
        borderRadius: "0 4px 4px 0",
        "&:hover": { bgcolor: "action.hover" },
      }}
    >
      <Stack direction="row" spacing={0.75} alignItems="center" sx={{ mb: 0.3 }}>
        <Chip size="small" label={alert.severity} color={SEVERITY_CHIP_COLOR[alert.severity] ?? "default"}
          sx={{ height: 18, fontSize: "0.62rem", fontWeight: 700 }} />
        {countBadge !== undefined && countBadge > 1 && (
          <Chip size="small" label={`${countBadge} signals`} variant="outlined"
            sx={{ height: 18, fontSize: "0.62rem" }} />
        )}
        <Typography variant="subtitle2" sx={{ fontSize: "0.8rem" }}>
          {ANOMALY_TYPE_LABEL[alert.anomaly_type] ?? alert.anomaly_type.replaceAll("_", " ")}
        </Typography>
      </Stack>
      <Typography variant="body2" sx={{ fontSize: "0.78rem" }}>{alert.detail}</Typography>
      <Typography variant="caption" color="text.secondary">
        {alert.source_place ? `${alert.source_place} · ` : ""}
        {new Date(
          alert.event_time && new Date(alert.event_time).getFullYear() > 2000
            ? alert.event_time : alert.detected_at
        ).toLocaleString()}
      </Typography>
    </Box>
  );

  return (
    <Stack spacing={1.5}>
      {Object.keys(typeCounts).length > 0 && (
        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
          {Object.entries(typeCounts)
            .sort((a, b) => b[1] - a[1])
            .map(([type, count]) => (
              <Chip key={type} size="small"
                label={`${ANOMALY_TYPE_LABEL[type] ?? type.replaceAll("_", " ")} · ${count}`}
                clickable variant={typeFilter === type ? "filled" : "outlined"}
                color={typeFilter === type ? "primary" : "default"}
                onClick={() => onTypeFilter(typeFilter === type ? "" : type)}
              />
            ))}
        </Stack>
      )}
      <Stack spacing={1} sx={{ maxHeight: 360, overflow: "auto" }}>
        {visible.length === 0 ? (
          <Typography color="text.secondary" variant="body2">No signals detected yet.</Typography>
        ) : clusters
          ? clusters.map(({ top, count }) => alertRow(top, `cluster-${top.anomaly_id}`, count))
          : visible.map(a => alertRow(a, a.anomaly_id))
        }
      </Stack>
    </Stack>
  );
}

function TopList({ title, items }: { title: string; items: TopItem[] }) {
  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="h6" gutterBottom>{title}</Typography>
        <Stack spacing={1}>
          {items.map(item => (
            <Stack key={item.label} direction="row" justifyContent="space-between">
              <Typography variant="body2" noWrap>{item.label || "Unknown"}</Typography>
              <Chip size="small" label={item.count.toLocaleString()} />
            </Stack>
          ))}
        </Stack>
      </CardContent>
    </Card>
  );
}

const MAG_BAND_LABELS: Record<string, string> = {
  micro: "M < 1",
  minor: "M 1–3",
  light: "M 3–5",
  moderate: "M 5–6",
  strong: "M 6–7",
  major: "M 7–8",
  great: "M 8+",
};

const DEPTH_BAND_LABELS: Record<string, string> = {
  negative: "< 0 km",
  shallow: "0–70 km",
  intermediate: "70–300 km",
  deep: "> 300 km",
};

const BAND_LABEL_ORDER: Record<"mag_band" | "depth_band", string[]> = {
  mag_band: ["micro", "minor", "light", "moderate", "strong", "major", "great"],
  depth_band: ["negative", "shallow", "intermediate", "deep"],
};

function BandsChart({ title, data, field }: { title: string; data: BandBucket[]; field: "mag_band" | "depth_band" }) {
  const labelMap = field === "mag_band" ? MAG_BAND_LABELS : DEPTH_BAND_LABELS;
  const order = BAND_LABEL_ORDER[field];
  const byKey = Object.fromEntries(data.map(item => [item[field] ?? "unknown", item.event_count]));
  const chartData = order
    .filter(key => byKey[key] !== undefined)
    .map(key => ({ label: labelMap[key] ?? key, count: byKey[key] }));
  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="h6" gutterBottom>{title}</Typography>
        <Box sx={{ height: 220 }}>
          <ResponsiveContainer>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="label" />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="count" fill="#176b87" />
            </BarChart>
          </ResponsiveContainer>
        </Box>
      </CardContent>
    </Card>
  );
}

function autoBucket(from: string, to: string): BucketSize {
  const spanMs = new Date(to).getTime() - new Date(from).getTime();
  if (spanMs <= 3_600_000)        return "5m";
  if (spanMs <= 6 * 3_600_000)    return "15m";
  if (spanMs <= 24 * 3_600_000)   return "1h";
  if (spanMs <= 7 * 86_400_000)   return "6h";
  if (spanMs <= 30 * 86_400_000)  return "1d";
  if (spanMs <= 365 * 86_400_000) return "1mo";
  return "1y";
}

export default function App() {
  const [activeRange, setActiveRange] = useState<RangePreset | null>("24h");
  const [from, setFrom] = useState(() => resolveRange("24h").from);
  const [to, setTo] = useState(() => resolveRange("24h").to);
  const [net, setNet] = useState("");
  const [mapView, setMapView] = useState<"globe" | "map">("globe");
  const [selectedEvent, setSelectedEvent] = useState<EarthquakeEvent | null>(null);
  const [focusLatLon, setFocusLatLon] = useState<{ lat: number; lon: number } | null>(null);
  const [viewCenter, setViewCenter] = useState<{ lat: number; lon: number }>({ lat: 20, lon: 0 });

  function handleTabChange(_: unknown, value: "globe" | "map") {
    setMapView(value);
  }

  function onPresetClick(preset: RangePreset) {
    const r = resolveRange(preset);
    setFrom(r.from);
    setTo(r.to);
    setActiveRange(preset);
  }

  function onPickerChange(newFrom: string, newTo: string) {
    setFrom(newFrom);
    setTo(newTo);
    setActiveRange(null);
  }

  const bucket = useMemo(() => autoBucket(from, to), [from, to]);
  const rollupBucket: BucketSize = useMemo(() => {
    if (bucket === "1y" || bucket === "1mo" || bucket === "1d") return "1d";
    if (bucket === "6h") return "1h";
    return "5m";
  }, [bucket]);

  const [alertTypeFilter, setAlertTypeFilter] = useState("");

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
    } else {
      const match = events.find(e => e.event_id === alert.source_event_id);
      if (match) {
        setSelectedEvent(match);
        setFocusLatLon(null);
      } else {
        setFocusLatLon({ lat: alert.latitude, lon: alert.longitude });
        setSelectedEvent(null);
      }
    }
  }

  const filteredEvents = net ? events.filter(event => event.net.toLowerCase().includes(net.toLowerCase())) : events;
  const filteredAlerts = useMemo(
    () => alertTypeFilter ? alerts.filter(a => a.anomaly_type === alertTypeFilter) : alerts,
    [alerts, alertTypeFilter]
  );

  function xLabel(isoTime: string): string {
    const d = new Date(isoTime);
    if (bucket === "1y")  return d.toLocaleDateString([], { year: "numeric" });
    if (bucket === "1mo") return d.toLocaleDateString([], { month: "short", year: "numeric" });
    if (bucket === "1d" || bucket === "6h") return d.toLocaleDateString([], { month: "short", day: "numeric" });
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  const rollupData = (data.rollups.data ?? []).map(item => ({
    time: xLabel(item.bucket),
    events: item.event_count,
    magnitude: Number(item.avg_magnitude.toFixed(2))
  }));

  return (
    <Container maxWidth={false} sx={{ py: 3 }}>
      <Stack spacing={3}>
        <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={2}>
          <Box>
            <Typography variant="h4" fontWeight={700}>PULSE</Typography>
            <Typography color="text.secondary">Real-time seismic intelligence from USGS GeoJSON streams</Typography>
          </Box>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
            <ConnectionChip label="Events" connected={data.eventsConnected} />
            <ConnectionChip label="Signals" connected={data.alertsConnected} />
          </Stack>
        </Stack>

        <Card variant="outlined">
          <CardContent>
            <Stack spacing={1.5}>
              <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                <Typography variant="body2" color="text.secondary">Range:</Typography>
                {PRESET_LABELS.map(({ label, value }) => (
                  <Chip
                    key={value}
                    label={label}
                    clickable
                    color={activeRange === value ? "primary" : "default"}
                    onClick={() => onPresetClick(value)}
                  />
                ))}
                <RangePickerButton from={from} to={to} onChange={onPickerChange} />
              </Stack>
              <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems={{ md: "center" }}>
                <FormControl size="small" sx={{ minWidth: 180 }}>
                  <InputLabel>Network</InputLabel>
                  <Select value={net} label="Network" onChange={event => setNet(event.target.value)}>
                    <MenuItem value="">All networks</MenuItem>
                    {(data.networks.data ?? []).map(item => <MenuItem key={item.label} value={item.label}>{item.label || "Unknown"}</MenuItem>)}
                  </Select>
                </FormControl>
                <Button variant="outlined" onClick={() => { setNet(""); onPresetClick("24h"); }}>Clear</Button>
              </Stack>
            </Stack>
          </CardContent>
        </Card>

        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(4, 1fr)" }, gap: 2 }}>
          <MetricCard title={isHeatmapMode ? "Density clusters" : "Visible events"} value={isHeatmapMode ? heatmapCells.length.toLocaleString() : filteredEvents.length.toLocaleString()} icon={<PublicIcon color="primary" />} />
          <MetricCard title="Events in 30 minutes" value={(data.status.data?.events_30min ?? 0).toLocaleString()} icon={<SensorsIcon color="primary" />} />
          <MetricCard title="Signals in 24 hours" value={(data.status.data?.anomaly_24h ?? 0).toLocaleString()} icon={<WarningAmberIcon color="warning" />} />
          <MetricCard title="Source age" value={data.status.data?.data_age_seconds == null ? "pending" : `${data.status.data.data_age_seconds}s`} icon={<SensorsIcon color="success" />} />
        </Box>

        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", lg: "2fr 1fr" }, gap: 2 }}>
          <Card variant="outlined">
            <CardContent>
              <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" alignItems={{ sm: "center" }} spacing={1} sx={{ mb: 1 }}>
                <Typography variant="h6">Live Epicentres</Typography>
                <Tabs value={mapView} onChange={handleTabChange} aria-label="map view">
                  <Tab value="globe" label="Globe" />
                  <Tab value="map" label="Map" />
                </Tabs>
              </Stack>
              <Box sx={{ height: 520 }}>
                <MapLibreView
                  events={filteredEvents}
                  heatmapCells={isHeatmapMode ? heatmapCells : undefined}
                  alerts={filteredAlerts}
                  selectedEvent={selectedEvent}
                  focusLatLon={focusLatLon}
                  onSelect={setSelectedEvent}
                  initialCenter={viewCenter}
                  onViewChange={(lat, lon) => setViewCenter({ lat, lon })}
                  projection={mapView === "globe" ? "globe" : "mercator"}
                />
              </Box>
            </CardContent>
          </Card>
          <Card variant="outlined">
            <CardContent>
              <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1.5 }}>
                <Typography variant="h6">Detected Signals</Typography>
                {alertTypeFilter && (
                  <Chip size="small" label="Clear filter" onClick={() => setAlertTypeFilter("")} onDelete={() => setAlertTypeFilter("")} />
                )}
              </Stack>
              <AlertFeed alerts={alerts} typeFilter={alertTypeFilter} onTypeFilter={setAlertTypeFilter} onAlertClick={handleAlertClick} isHeatmapMode={isHeatmapMode} heatmapResolution={heatmapResolution} />
            </CardContent>
          </Card>
        </Box>

        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", lg: "2fr 1fr" }, gap: 2 }}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="h6" gutterBottom>Event Volume ({bucket === "1mo" ? "monthly" : bucket === "1y" ? "yearly" : `${bucket} buckets`})</Typography>
              <Box sx={{ height: 260 }}>
                <ResponsiveContainer>
                  <AreaChart data={(data.timeseries.data ?? []).map(item => ({ ...item, label: xLabel(item.time) }))}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="label" />
                    <YAxis allowDecimals={false} />
                    <Tooltip />
                    <Area dataKey="event_count" stroke="#176b87" fill="#64a6bd" fillOpacity={0.35} />
                  </AreaChart>
                </ResponsiveContainer>
              </Box>
            </CardContent>
          </Card>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="h6" gutterBottom>Network Rollup</Typography>
              <Box sx={{ height: 260 }}>
                <ResponsiveContainer>
                  <LineChart data={rollupData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="time" />
                    <YAxis allowDecimals={false} />
                    <Tooltip />
                    <Line type="monotone" dataKey="events" stroke="#b45309" dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </Box>
            </CardContent>
          </Card>
        </Box>

        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(4, 1fr)" }, gap: 2 }}>
          <TopList title="Top Networks" items={data.networks.data ?? []} />
          <TopList title="Top Places" items={data.places.data ?? []} />
          <BandsChart title="Magnitude Bands" data={data.magnitudeBands.data ?? []} field="mag_band" />
          <BandsChart title="Depth Bands" data={data.depthBands.data ?? []} field="depth_band" />
        </Box>
      </Stack>
    </Container>
  );
}
