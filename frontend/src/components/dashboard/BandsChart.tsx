import { Box, Card, CardContent, Typography } from "@mui/material";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { BandBucket } from "../../api/client";
import { BAND_LABEL_ORDER, DEPTH_BAND_LABELS, MAG_BAND_LABELS } from "./constants";

export function BandsChart({ title, data, field }: { title: string; data: BandBucket[]; field: "mag_band" | "depth_band" }) {
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
