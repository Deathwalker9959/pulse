import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { HourlyBucket } from "../api/client";

interface Props {
  data: HourlyBucket[];
}

function formatHour(iso: string): string {
  const d = new Date(iso);
  return `${d.getUTCHours().toString().padStart(2, "0")}:00`;
}

export function FlightChart({ data }: Props) {
  const chartData = data.map(b => ({
    hour: formatHour(b.hour),
    flights: b.flight_count,
    airborne: b.airborne_count,
    avg_alt: Math.round(b.avg_altitude),
  }));

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="hour" tick={{ fontSize: 11 }} />
        <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
        <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} />
        <Tooltip />
        <Legend />
        <Line yAxisId="left" type="monotone" dataKey="flights" stroke="#3b82f6" dot={false} name="Total flights" />
        <Line yAxisId="left" type="monotone" dataKey="airborne" stroke="#10b981" dot={false} name="Airborne" />
        <Line yAxisId="right" type="monotone" dataKey="avg_alt" stroke="#f59e0b" dot={false} name="Avg altitude (m)" strokeDasharray="4 2" />
      </LineChart>
    </ResponsiveContainer>
  );
}
