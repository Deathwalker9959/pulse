import {
  Box,
  Card,
  CardContent,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";
import PublicIcon from "@mui/icons-material/Public";
import SensorsIcon from "@mui/icons-material/Sensors";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import FiberManualRecordIcon from "@mui/icons-material/FiberManualRecord";
import { MetricCard } from "./MetricCard";

interface DashboardMetricsProps {
  isHeatmapMode: boolean;
  heatmapCellCount: number;
  visibleEventCount: number;
  events30Min: number;
  signals24h: number;
  dataAgeSeconds: number | null | undefined;
  pollAgeSeconds: number | null | undefined;
}

export function DashboardMetrics({
  isHeatmapMode,
  heatmapCellCount,
  visibleEventCount,
  events30Min,
  signals24h,
  dataAgeSeconds,
  pollAgeSeconds,
}: DashboardMetricsProps) {
  const [liveSourceAge, setLiveSourceAge] = useState(dataAgeSeconds);

  useEffect(() => {
    setLiveSourceAge(dataAgeSeconds);
    if (dataAgeSeconds == null) return;
    const timer = window.setInterval(() => {
      setLiveSourceAge((age) => (age == null ? dataAgeSeconds + 1 : age + 1));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [dataAgeSeconds]);

  const pipelineLive = pollAgeSeconds != null && pollAgeSeconds < 120;
  const pipelineLabel =
    pollAgeSeconds == null
      ? "No poll data"
      : pipelineLive
        ? "Pipeline live"
        : "Poll overdue";
  const pipelineColor =
    pollAgeSeconds == null ? "#94a3b8" : pipelineLive ? "#16a34a" : "#f59e0b";

  return (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: { xs: "1fr", md: "repeat(4, 1fr)" },
        gap: 2,
        alignItems: "stretch",
      }}
    >
      <MetricCard
        title={isHeatmapMode ? "Density clusters" : "Visible events"}
        value={
          isHeatmapMode
            ? heatmapCellCount.toLocaleString()
            : visibleEventCount.toLocaleString()
        }
        icon={<PublicIcon color="primary" />}
        tooltip={
          isHeatmapMode
            ? "Number of H3 cell clusters in the current view"
            : "Number of seismic events currently visible on the map"
        }
      />
      <MetricCard
        title="Events in 30 minutes"
        value={events30Min.toLocaleString()}
        icon={<SensorsIcon color="primary" />}
        tooltip="Seismic events detected in the last 30 minutes"
      />
      <MetricCard
        title="Signals in 24 hours"
        value={signals24h.toLocaleString()}
        icon={<WarningAmberIcon color="warning" />}
        tooltip="Total number of seismic signals detected in the last 24 hours"
      />
      <Tooltip
        title="Time since last data update from the seismic source. Pipeline indicator shows when poll data was last collected."
        placement="top"
      >
        <div style={{ pointerEvents: "auto", height: "100%" }}>
          <Card
            variant="outlined"
            sx={{ cursor: "default", pointerEvents: "none", height: "100%" }}
          >
            <CardContent>
              <Stack direction="row" alignItems="center" spacing={1}>
                <SensorsIcon color="success" />
                <Typography color="text.secondary" variant="body2">
                  Source age
                </Typography>
              </Stack>
              <Typography variant="h4" sx={{ mt: 1 }}>
                {liveSourceAge == null ? "pending" : `${liveSourceAge}s`}
              </Typography>
              <Stack
                direction="row"
                alignItems="center"
                spacing={0.5}
                sx={{ mt: 0.5 }}
              >
                <FiberManualRecordIcon
                  sx={{ fontSize: 10, color: pipelineColor }}
                />
                <Typography variant="caption" sx={{ color: pipelineColor }}>
                  {pipelineLabel}
                </Typography>
              </Stack>
            </CardContent>
          </Card>
        </div>
      </Tooltip>
    </Box>
  );
}
