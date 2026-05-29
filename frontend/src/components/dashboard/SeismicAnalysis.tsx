import { Box, Card, CardContent, Typography } from "@mui/material";
import { useMemo } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { BValueBucket, EnergyBucket, IETBucket, MagFrequencyBucket } from "../../api/client";
import { MC } from "./constants";

interface SeismicAnalysisProps {
  magnitudeFrequency: MagFrequencyBucket[];
  energyTimeseries: EnergyBucket[];
  bValueHistory: BValueBucket[];
  interEventTimes: IETBucket[];
  xLabel: (iso: string) => string;
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
      .filter(() => cumN > 0)
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
            <Typography variant="h6" gutterBottom>
              G–R Distribution{grBValue !== null ? ` · b = ${grBValue.toFixed(2)}` : ""}
            </Typography>
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
            <Typography variant="h6" gutterBottom>B-Value History</Typography>
            <Box sx={{ height: 260 }}>
              <ResponsiveContainer>
                <LineChart data={bValueHistory}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="day" tickFormatter={day => new Date(day).toLocaleDateString([], { month: "short", day: "numeric" })} />
                  <YAxis domain={[0, 2.5]} allowDecimals />
                  <Tooltip
                    labelFormatter={day => new Date(String(day)).toLocaleDateString()}
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
            <Typography variant="h6" gutterBottom>Seismic Energy Release</Typography>
            <Box sx={{ height: 260 }}>
              <ResponsiveContainer>
                <AreaChart data={energyData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="bucket" tickFormatter={xLabel} />
                  <YAxis label={{ value: "log₁₀(E) J", angle: -90, position: "insideLeft", fontSize: 11 }} />
                  <Tooltip
                    labelFormatter={bucket => xLabel(String(bucket))}
                    formatter={(value) => [`10^${Number(value).toFixed(1)} J`, "Energy"]}
                  />
                  <Area dataKey="logEnergy" stroke="#b45309" fill="#fbbf24" fillOpacity={0.35} name="log₁₀(E)" />
                </AreaChart>
              </ResponsiveContainer>
            </Box>
          </CardContent>
        </Card>
        <Card variant="outlined">
          <CardContent>
            <Typography variant="h6" gutterBottom>Inter-Event Time Distribution</Typography>
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
