import { Box } from "@mui/material";
import PublicIcon from "@mui/icons-material/Public";
import SensorsIcon from "@mui/icons-material/Sensors";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import { MetricCard } from "./MetricCard";

interface DashboardMetricsProps {
  isHeatmapMode: boolean;
  heatmapCellCount: number;
  visibleEventCount: number;
  events30Min: number;
  signals24h: number;
  dataAgeSeconds: number | null | undefined;
}

export function DashboardMetrics({
  isHeatmapMode,
  heatmapCellCount,
  visibleEventCount,
  events30Min,
  signals24h,
  dataAgeSeconds,
}: DashboardMetricsProps) {
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(4, 1fr)" }, gap: 2 }}>
      <MetricCard
        title={isHeatmapMode ? "Density clusters" : "Visible events"}
        value={isHeatmapMode ? heatmapCellCount.toLocaleString() : visibleEventCount.toLocaleString()}
        icon={<PublicIcon color="primary" />}
      />
      <MetricCard title="Events in 30 minutes" value={events30Min.toLocaleString()} icon={<SensorsIcon color="primary" />} />
      <MetricCard title="Signals in 24 hours" value={signals24h.toLocaleString()} icon={<WarningAmberIcon color="warning" />} />
      <MetricCard title="Source age" value={dataAgeSeconds == null ? "pending" : `${dataAgeSeconds}s`} icon={<SensorsIcon color="success" />} />
    </Box>
  );
}
