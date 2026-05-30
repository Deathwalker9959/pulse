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

function isoTruncKey(iso: string, bucket: BucketSize): string {
  // Deterministic grouping key — truncate ISO to bucket granularity (UTC).
  // Using locale-formatted strings as Map keys risks Intl variation (NBSP, etc.).
  if (bucket === "1y") return iso.slice(0, 4);
  if (bucket === "1mo") return iso.slice(0, 7);
  if (bucket === "1d") return iso.slice(0, 10);
  return iso.slice(0, 13); // 6h, 1h, 15m, 5m: preserve hour
}

export function ActivityCharts({
  bucket,
  timeseries,
  rollups,
  xLabel,
}: ActivityChartsProps) {
  const rollupData = useMemo(() => {
    const byTime = new Map<
      string,
      { display: string; events: number; magnitude: number; count: number }
    >();
    for (const item of rollups) {
      const key = isoTruncKey(item.bucket, bucket);
      const existing = byTime.get(key);
      if (existing) {
        existing.events += item.event_count;
        existing.magnitude += item.avg_magnitude;
        existing.count += 1;
      } else {
        byTime.set(key, {
          display: xLabel(item.bucket),
          events: item.event_count,
          magnitude: item.avg_magnitude,
          count: 1,
        });
      }
    }
    return Array.from(byTime.values()).map((v) => ({
      time: v.display,
      events: v.events,
      magnitude: Number((v.magnitude / v.count).toFixed(2)),
    }));
  }, [rollups, xLabel, bucket]);

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
