import { Box } from "@mui/material";
import { useEffect, useState } from "react";
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
  const [liveSourceAge, setLiveSourceAge] = useState(dataAgeSeconds);

  useEffect(() => {
    setLiveSourceAge(dataAgeSeconds);
    if (dataAgeSeconds == null) return;

    const timer = window.setInterval(() => {
      setLiveSourceAge(age => age == null ? dataAgeSeconds + 1 : age + 1);
    }, 1000);

    return () => window.clearInterval(timer);
  }, [dataAgeSeconds]);

  return (
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(4, 1fr)" }, gap: 2 }}>
      <MetricCard
        title={isHeatmapMode ? "Density clusters" : "Visible events"}
        value={isHeatmapMode ? heatmapCellCount.toLocaleString() : visibleEventCount.toLocaleString()}
        icon={<PublicIcon color="primary" />}
      />
      <MetricCard title="Events in 30 minutes" value={events30Min.toLocaleString()} icon={<SensorsIcon color="primary" />} />
      <MetricCard title="Signals in 24 hours" value={signals24h.toLocaleString()} icon={<WarningAmberIcon color="warning" />} />
      <MetricCard title="Source age" value={liveSourceAge == null ? "pending" : `${liveSourceAge}s`} icon={<SensorsIcon color="success" />} />
    </Box>
  );
}
