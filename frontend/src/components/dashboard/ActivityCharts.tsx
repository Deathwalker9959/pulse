import {
  Box,
  Card,
  CardContent,
  Stack,
  Tooltip as MuiTooltip,
  Typography,
} from "@mui/material";
import { useMemo } from "react";
import InfoIcon from "@mui/icons-material/Info";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type {
  BucketSize,
  NetworkRollup,
  TimeseriesBucket,
} from "../../api/client";

interface ActivityChartsProps {
  bucket: BucketSize;
  timeseries: TimeseriesBucket[];
  rollups: NetworkRollup[];
  xLabel: (iso: string) => string;
}

export function ActivityCharts({
  bucket,
  timeseries,
  rollups,
  xLabel,
}: ActivityChartsProps) {
  // Group by time bucket, summing event_count across all networks (or the single filtered net)
  const rollupData = useMemo(() => {
    const byTime = new Map<
      string,
      { events: number; magnitude: number; count: number }
    >();
    for (const item of rollups) {
      const t = xLabel(item.bucket);
      const existing = byTime.get(t);
      if (existing) {
        existing.events += item.event_count;
        existing.magnitude += item.avg_magnitude;
        existing.count += 1;
      } else {
        byTime.set(t, {
          events: item.event_count,
          magnitude: item.avg_magnitude,
          count: 1,
        });
      }
    }
    return Array.from(byTime.entries()).map(([time, v]) => ({
      time,
      events: v.events,
      magnitude: Number((v.magnitude / v.count).toFixed(2)),
    }));
  }, [rollups, xLabel]);

  return (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: { xs: "1fr", lg: "2fr 1fr" },
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
              Event Volume (
              {bucket === "1mo"
                ? "monthly"
                : bucket === "1y"
                  ? "yearly"
                  : `${bucket} buckets`}
              )
            </Typography>
            <MuiTooltip title="Number of seismic events detected per time bucket">
              <InfoIcon sx={{ fontSize: 20, opacity: 0.6, cursor: "help" }} />
            </MuiTooltip>
          </Stack>
          <Box sx={{ height: 260 }}>
            <ResponsiveContainer>
              <AreaChart
                data={timeseries.map((item) => ({
                  ...item,
                  label: xLabel(item.time),
                }))}
              >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="label" />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Area
                  dataKey="event_count"
                  stroke="#176b87"
                  fill="#64a6bd"
                  fillOpacity={0.35}
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
            <Typography variant="h6">Network Rollup</Typography>
            <MuiTooltip title="Event count aggregated by seismic network source">
              <InfoIcon sx={{ fontSize: 20, opacity: 0.6, cursor: "help" }} />
            </MuiTooltip>
          </Stack>
          <Box sx={{ height: 260 }}>
            <ResponsiveContainer>
              <LineChart data={rollupData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="time" />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Line
                  type="monotone"
                  dataKey="events"
                  stroke="#b45309"
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </Box>
        </CardContent>
      </Card>
    </Box>
  );
}
