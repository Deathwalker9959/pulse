import { Box, Card, CardContent, Typography } from "@mui/material";
import { Area, AreaChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { BucketSize, NetworkRollup, TimeseriesBucket } from "../../api/client";

interface ActivityChartsProps {
  bucket: BucketSize;
  timeseries: TimeseriesBucket[];
  rollups: NetworkRollup[];
  xLabel: (iso: string) => string;
}

export function ActivityCharts({ bucket, timeseries, rollups, xLabel }: ActivityChartsProps) {
  const rollupData = rollups.map(item => ({
    time: xLabel(item.bucket),
    events: item.event_count,
    magnitude: Number(item.avg_magnitude.toFixed(2)),
  }));

  return (
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", lg: "2fr 1fr" }, gap: 2 }}>
      <Card variant="outlined">
        <CardContent>
          <Typography variant="h6" gutterBottom>Event Volume ({bucket === "1mo" ? "monthly" : bucket === "1y" ? "yearly" : `${bucket} buckets`})</Typography>
          <Box sx={{ height: 260 }}>
            <ResponsiveContainer>
              <AreaChart data={timeseries.map(item => ({ ...item, label: xLabel(item.time) }))}>
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
  );
}
