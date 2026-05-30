import {
  Alert,
  Box,
  Card,
  CardContent,
  Stack,
  Tooltip as MuiTooltip,
  Typography,
} from "@mui/material";
import InfoIcon from "@mui/icons-material/Info";
import { useMemo } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type {
  BucketSize,
  BValueBucket,
  EnergyBucket,
  IETBucket,
  MagFrequencyBucket,
} from "../../api/client";
import { MC } from "./constants";

interface SeismicAnalysisProps {
  bucket: BucketSize;
  magnitudeFrequency: MagFrequencyBucket[];
  energyTimeseries: EnergyBucket[];
  bValueHistory: BValueBucket[];
  interEventTimes: IETBucket[];
  xLabel: (iso: string) => string;
}

function bvTruncKey(iso: string, bucket: BucketSize): string {
  if (bucket === "1y") return iso.slice(0, 4);
  if (bucket === "1mo") return iso.slice(0, 7);
  if (bucket === "1d") return iso.slice(0, 10);
  return iso.slice(0, 13); // 1h and finer: preserve hour
}

function formatEnergy(joules: number): string {
  const units = ["J", "kJ", "MJ", "GJ", "TJ"];
  let value = joules;
  let unitIndex = 0;
  while (value >= 1000 && unitIndex < units.length - 1) {
    value /= 1000;
    unitIndex++;
  }
  return `${value.toFixed(1)} ${units[unitIndex]}`;
}

export function SeismicAnalysis({
  bucket,
  magnitudeFrequency,
  energyTimeseries,
  bValueHistory,
  interEventTimes,
  xLabel,
}: SeismicAnalysisProps) {
  const grPoints = useMemo(() => {
    const sorted = [...magnitudeFrequency].sort(
      (a, b) => a.mag_bin - b.mag_bin,
    );
    let cumN = sorted.reduce((sum, bucket) => sum + bucket.event_count, 0);
    return sorted
      .filter((bucket) => bucket.mag_bin >= MC && cumN > 0)
      .map((bucket) => {
        const point = {
          mag: bucket.mag_bin,
          logCumN: cumN > 0 ? Math.log10(cumN) : 0,
        };
        cumN -= bucket.event_count;
        return point;
      });
  }, [magnitudeFrequency]);

  const grBValue = useMemo(() => {
    const above = magnitudeFrequency.filter((bucket) => bucket.mag_bin >= MC);
    const total = above.reduce((sum, bucket) => sum + bucket.event_count, 0);
    if (total < 20) return null;
    const meanM =
      above.reduce(
        (sum, bucket) => sum + bucket.mag_bin * bucket.event_count,
        0,
      ) / total;
    if (meanM <= MC) return null;
    return Math.LOG10E / (meanM - MC);
  }, [magnitudeFrequency]);

  const energyData = useMemo(
    () =>
      energyTimeseries
        .filter((b) => b.energy_joules > 0)
        .map((b) => ({ bucket: b.bucket, logEnergy: Math.log10(b.energy_joules) })),
    [energyTimeseries],
  );

  // Aggregate daily b-value buckets to the display granularity (e.g. monthly for YTD).
  // Weighted average by sample_size avoids duplicate x-axis labels from Recharts tick selection.
  const bValueData = useMemo(() => {
    const byKey = new Map<
      string,
      { display: string; wSum: number; wTotal: number }
    >();
    for (const row of bValueHistory) {
      const key = bvTruncKey(row.day, bucket);
      const existing = byKey.get(key);
      if (existing) {
        existing.wSum += row.b_value * row.sample_size;
        existing.wTotal += row.sample_size;
      } else {
        byKey.set(key, {
          display: xLabel(row.day),
          wSum: row.b_value * row.sample_size,
          wTotal: row.sample_size,
        });
      }
    }
    return Array.from(byKey.values()).map((v) => ({
      day: v.display,
      b_value: v.wTotal > 0 ? v.wSum / v.wTotal : 0,
      sample_size: v.wTotal,
    }));
  }, [bValueHistory, bucket, xLabel]);

  return (
    <Box>
      <Typography variant="h6" sx={{ mb: 2 }}>
        Seismic Analysis
      </Typography>
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "1fr", md: "repeat(2, 1fr)" },
          gap: 2,
        }}
      >
        <Card variant="outlined">
          <CardContent>
            <Stack
              direction="row"
              justifyContent="space-between"
              alignItems="center"
              sx={{ mb: 2 }}
            >
              <Typography variant="h6">
                G–R Distribution
                {grBValue !== null ? ` · b = ${grBValue.toFixed(2)}` : ""}
              </Typography>
              <MuiTooltip
                title={
                  grBValue === null
                    ? "Gutenberg-Richter relationship: cumulative frequency vs magnitude. b-value calculated from mean magnitude (need ≥20 events M≥2.5)."
                    : `b-value from mean magnitude: ${grBValue.toFixed(2)}. ${grBValue < 0.5 ? "Critical: predominantly large events" : grBValue < 0.7 ? "Warning: higher proportion of large events" : "Normal: balanced magnitude distribution"}. Time range: selected window. Chart shows actual G–R slope.`
                }
              >
                <InfoIcon sx={{ fontSize: 20, opacity: 0.6, cursor: "help" }} />
              </MuiTooltip>
            </Stack>
            {grPoints.length === 0 ? (
              <Box sx={{ height: 260, display: "flex", alignItems: "center", justifyContent: "center" }}>
                <Typography variant="body2" color="text.secondary">
                  Not enough events — select a wider time range
                </Typography>
              </Box>
            ) : (
            <Box sx={{ height: 260 }}>
              <ResponsiveContainer>
                <LineChart data={grPoints}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis
                    dataKey="mag"
                    type="number"
                    domain={["dataMin", "dataMax"]}
                    tickFormatter={(v) => Number(v).toFixed(1)}
                    label={{
                      value: "Magnitude",
                      position: "insideBottom",
                      offset: -2,
                      fontSize: 11,
                    }}
                  />
                  <YAxis
                    domain={[0, "auto"]}
                    allowDecimals
                    tickFormatter={(v) => Number(v).toFixed(1)}
                    label={{
                      value: "log₁₀(N≥M)",
                      angle: -90,
                      position: "insideLeft",
                      fontSize: 11,
                    }}
                  />
                  <Tooltip
                    formatter={(value) => [
                      Number(value).toFixed(2),
                      "log₁₀(N≥M)",
                    ]}
                  />
                  <Line
                    type="monotone"
                    dataKey="logCumN"
                    stroke="#7c3aed"
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </Box>
            )}
          </CardContent>
        </Card>
        <Card variant="outlined">
          <CardContent>
            <Stack
              direction="row"
              justifyContent="space-between"
              alignItems="center"
              sx={{ mb: 2 }}
            >
              <Typography variant="h6">B-Value History</Typography>
              <MuiTooltip title="B-value evolution over time. Lower values indicate higher proportion of large events. Red line: critical threshold (0.5), orange: warning (0.7).">
                <InfoIcon sx={{ fontSize: 20, opacity: 0.6, cursor: "help" }} />
              </MuiTooltip>
            </Stack>
            {bValueHistory.length > 0 && bValueHistory.length < 10 && (
              <Alert severity="warning" sx={{ mb: 1, py: 0, fontSize: 12 }}>
                Sparse data — only {bValueHistory.length} qualifying bucket
                {bValueHistory.length !== 1 ? "s" : ""}. B-values unreliable (Mc
                may not match filter subset).
              </Alert>
            )}
            {bValueData.length === 0 ? (
              <Box sx={{ height: 260, display: "flex", alignItems: "center", justifyContent: "center" }}>
                <Typography variant="body2" color="text.secondary">
                  Not enough events — select a wider time range
                </Typography>
              </Box>
            ) : (
            <Box sx={{ height: 260 }}>
              <ResponsiveContainer>
                <LineChart data={bValueData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="day" />
                  <YAxis
                    domain={[0, 2.5]}
                    allowDecimals
                    label={{
                      value: "b-value",
                      angle: -90,
                      position: "insideLeft",
                      fontSize: 11,
                    }}
                  />
                  <Tooltip
                    formatter={(value) => [Number(value).toFixed(2), "b-value"]}
                  />
                  <ReferenceLine
                    y={0.5}
                    stroke="#dc2626"
                    strokeDasharray="4 2"
                    label={{
                      value: "Critical (0.5)",
                      position: "insideTopRight",
                      fontSize: 10,
                    }}
                  />
                  <ReferenceLine
                    y={0.7}
                    stroke="#f97316"
                    strokeDasharray="4 2"
                    label={{
                      value: "Warning (0.7)",
                      position: "insideTopRight",
                      fontSize: 10,
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="b_value"
                    stroke="#0284c7"
                    dot={false}
                    name="b-value"
                  />
                </LineChart>
              </ResponsiveContainer>
            </Box>
            )}
          </CardContent>
        </Card>
        <Card variant="outlined">
          <CardContent>
            <Stack
              direction="row"
              justifyContent="space-between"
              alignItems="center"
              sx={{ mb: 2 }}
            >
              <Typography variant="h6">Seismic Energy Release</Typography>
              <MuiTooltip title="Total energy released per time period in joules (log scale). Indicates magnitude and frequency of seismic activity.">
                <InfoIcon sx={{ fontSize: 20, opacity: 0.6, cursor: "help" }} />
              </MuiTooltip>
            </Stack>
            <Box sx={{ height: 260 }}>
              <ResponsiveContainer>
                <AreaChart data={energyData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="bucket" tickFormatter={xLabel} />
                  <YAxis
                    label={{
                      value: "log₁₀(E) J",
                      angle: -90,
                      position: "insideLeft",
                      fontSize: 11,
                    }}
                  />
                  <Tooltip
                    labelFormatter={(bucket) => xLabel(String(bucket))}
                    formatter={(value) => [
                      formatEnergy(Math.pow(10, Number(value) || 0)),
                      "Energy",
                    ]}
                  />
                  <Area
                    dataKey="logEnergy"
                    stroke="#b45309"
                    fill="#fbbf24"
                    fillOpacity={0.35}
                    name="log₁₀(E)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </Box>
          </CardContent>
        </Card>
        <Card variant="outlined">
          <CardContent>
            <Stack
              direction="row"
              justifyContent="space-between"
              alignItems="center"
              sx={{ mb: 2 }}
            >
              <Typography variant="h6">
                Inter-Event Time Distribution
              </Typography>
              <MuiTooltip title="Distribution of time intervals between consecutive seismic events. Shows clustering patterns and temporal organization.">
                <InfoIcon sx={{ fontSize: 20, opacity: 0.6, cursor: "help" }} />
              </MuiTooltip>
            </Stack>
            <Box sx={{ height: 260 }}>
              <ResponsiveContainer>
                <BarChart data={interEventTimes}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="bin_label" tick={{ fontSize: 11 }} />
                  <YAxis allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#176b87" name="Events" />
                </BarChart>
              </ResponsiveContainer>
            </Box>
          </CardContent>
        </Card>
      </Box>
    </Box>
  );
}
