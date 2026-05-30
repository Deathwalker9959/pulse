import { Box, Card, CardContent, Stack, Tooltip as MuiTooltip, Typography } from "@mui/material";
import InfoIcon from "@mui/icons-material/Info";
import { useMemo } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { BValueBucket, EnergyBucket, IETBucket, MagFrequencyBucket } from "../../api/client";
import { utcDateLabel } from "../../utils/dates";
import { MC } from "./constants";

interface SeismicAnalysisProps {
  magnitudeFrequency: MagFrequencyBucket[];
  energyTimeseries: EnergyBucket[];
  bValueHistory: BValueBucket[];
  interEventTimes: IETBucket[];
  xLabel: (iso: string) => string;
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
  magnitudeFrequency,
  energyTimeseries,
  bValueHistory,
  interEventTimes,
  xLabel,
}: SeismicAnalysisProps) {
  const grPoints = useMemo(() => {
    const sorted = [...magnitudeFrequency].sort((a, b) => a.mag_bin - b.mag_bin);
    let cumN = sorted.reduce((sum, bucket) => sum + bucket.event_count, 0);
    return sorted
      .filter(bucket => bucket.mag_bin >= MC && cumN > 0)
      .map(bucket => {
        const point = { mag: bucket.mag_bin, logCumN: cumN > 0 ? Math.log10(cumN) : 0 };
        cumN -= bucket.event_count;
        return point;
      });
  }, [magnitudeFrequency]);

  const grBValue = useMemo(() => {
    const above = magnitudeFrequency.filter(bucket => bucket.mag_bin >= MC);
    const total = above.reduce((sum, bucket) => sum + bucket.event_count, 0);
    if (total < 20) return null;
    const meanM = above.reduce((sum, bucket) => sum + bucket.mag_bin * bucket.event_count, 0) / total;
    if (meanM <= MC) return null;
    return Math.LOG10E / (meanM - MC);
  }, [magnitudeFrequency]);

  const energyData = useMemo(() =>
    energyTimeseries
      .filter(bucket => bucket.energy_joules > 0)
      .map(bucket => ({ bucket: bucket.bucket, logEnergy: Math.log10(bucket.energy_joules) })),
    [energyTimeseries]
  );

  return (
    <Box>
      <Typography variant="h6" sx={{ mb: 2 }}>Seismic Analysis</Typography>
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(2, 1fr)" }, gap: 2 }}>
        <Card variant="outlined">
          <CardContent>
            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
              <Typography variant="h6">
                G–R Distribution{grBValue !== null ? ` · b = ${grBValue.toFixed(2)}` : ""}
              </Typography>
              <MuiTooltip title={grBValue === null ? "Gutenberg-Richter relationship: cumulative frequency vs magnitude. b-value calculated from mean magnitude (need ≥20 events M≥2.5)." : `b-value from mean magnitude: ${grBValue.toFixed(2)}. ${grBValue < 0.5 ? "Critical: predominantly large events" : grBValue < 0.7 ? "Warning: higher proportion of large events" : "Normal: balanced magnitude distribution"}. Time range: selected window. Chart shows actual G–R slope.`}>
                <InfoIcon sx={{ fontSize: 20, opacity: 0.6, cursor: "help" }} />
              </MuiTooltip>
            </Stack>
            <Box sx={{ height: 260 }}>
              <ResponsiveContainer>
                <LineChart data={grPoints}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="mag" label={{ value: "Magnitude", position: "insideBottom", offset: -2, fontSize: 11 }} />
                  <YAxis label={{ value: "log₁₀(N≥M)", angle: -90, position: "insideLeft", fontSize: 11 }} />
                  <Tooltip formatter={(value) => [Number(value).toFixed(2), "log₁₀(N≥M)"]} />
                  <Line type="monotone" dataKey="logCumN" stroke="#7c3aed" dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </Box>
          </CardContent>
        </Card>
        <Card variant="outlined">
          <CardContent>
            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
              <Typography variant="h6">B-Value History</Typography>
              <MuiTooltip title="B-value evolution over time. Lower values indicate higher proportion of large events. Red line: critical threshold (0.5), orange: warning (0.7).">
                <InfoIcon sx={{ fontSize: 20, opacity: 0.6, cursor: "help" }} />
              </MuiTooltip>
            </Stack>
            <Box sx={{ height: 260 }}>
              <ResponsiveContainer>
                <LineChart data={bValueHistory}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="day" tickFormatter={day => {
                    const dateStr = String(day);
                    const match = dateStr.match(/(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
                    if (match) {
                      const [, , month, date, hour] = match;
                      return `${month}-${date} ${hour}:00`;
                    }
                    return utcDateLabel(dateStr);
                  }} />
                  <YAxis domain={[0, 2.5]} allowDecimals label={{ value: "b-value", angle: -90, position: "insideLeft", fontSize: 11 }} />
                  <Tooltip
                    labelFormatter={day => {
                      const dateStr = String(day);
                      const match = dateStr.match(/(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
                      if (match) {
                        const [, year, month, date, hour, min] = match;
                        return `${year}-${month}-${date} ${hour}:${min}`;
                      }
                      return utcDateLabel(dateStr);
                    }}
                    formatter={(value) => [Number(value).toFixed(2), "b-value"]}
                  />
                  <ReferenceLine y={0.5} stroke="#dc2626" strokeDasharray="4 2" label={{ value: "Critical (0.5)", position: "insideTopRight", fontSize: 10 }} />
                  <ReferenceLine y={0.7} stroke="#f97316" strokeDasharray="4 2" label={{ value: "Warning (0.7)", position: "insideTopRight", fontSize: 10 }} />
                  <Line type="monotone" dataKey="b_value" stroke="#0284c7" dot={false} name="b-value" />
                </LineChart>
              </ResponsiveContainer>
            </Box>
          </CardContent>
        </Card>
        <Card variant="outlined">
          <CardContent>
            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
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
                  <YAxis label={{ value: "log₁₀(E) J", angle: -90, position: "insideLeft", fontSize: 11 }} />
                  <Tooltip
                    labelFormatter={bucket => xLabel(String(bucket))}
                    formatter={(value) => [formatEnergy(Math.pow(10, Number(value) || 0)), "Energy"]}
                  />
                  <Area dataKey="logEnergy" stroke="#b45309" fill="#fbbf24" fillOpacity={0.35} name="log₁₀(E)" />
                </AreaChart>
              </ResponsiveContainer>
            </Box>
          </CardContent>
        </Card>
        <Card variant="outlined">
          <CardContent>
            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
              <Typography variant="h6">Inter-Event Time Distribution</Typography>
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
