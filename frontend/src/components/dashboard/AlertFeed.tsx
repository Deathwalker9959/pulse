import { Box, Chip, Stack, Typography } from "@mui/material";
import { useMemo } from "react";
import { latLngToCell } from "h3-js";
import type { AnomalyEvent } from "../../api/client";
import { parseApiDate, utcDateTimeLabel } from "../../utils/dates";
import { ANOMALY_TYPE_LABEL, SEVERITY_BORDER, SEVERITY_CHIP_COLOR, SEV_ORDER } from "./constants";

interface AlertFeedProps {
  alerts: AnomalyEvent[];
  typeFilter: string;
  onTypeFilter: (type: string) => void;
  onAlertClick: (alert: AnomalyEvent) => void;
  isHeatmapMode?: boolean;
  heatmapResolution?: number;
}

export function AlertFeed({
  alerts,
  typeFilter,
  onTypeFilter,
  onAlertClick,
  isHeatmapMode = false,
  heatmapResolution = 3,
}: AlertFeedProps) {
  const typeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const alert of alerts) counts[alert.anomaly_type] = (counts[alert.anomaly_type] ?? 0) + 1;
    return counts;
  }, [alerts]);

  const visible = typeFilter ? alerts.filter(alert => alert.anomaly_type === typeFilter) : alerts;

  const clusters = useMemo(() => {
    if (!isHeatmapMode) return null;
    const byCell = new Map<string, AnomalyEvent[]>();
    for (const alert of visible) {
      try {
        const key = latLngToCell(alert.latitude, alert.longitude, heatmapResolution).replace(/^0/, "");
        if (!byCell.has(key)) byCell.set(key, []);
        byCell.get(key)!.push(alert);
      } catch { /* ignore invalid coordinates */ }
    }
    return Array.from(byCell.values())
      .map(group => {
        group.sort((a, b) => (SEV_ORDER[a.severity] ?? 2) - (SEV_ORDER[b.severity] ?? 2));
        return { top: group[0], count: group.length };
      })
      .sort((a, b) => {
        const severityDelta = (SEV_ORDER[a.top.severity] ?? 2) - (SEV_ORDER[b.top.severity] ?? 2);
        return severityDelta !== 0 ? severityDelta : b.count - a.count;
      });
  }, [visible, isHeatmapMode, heatmapResolution]);

  const alertRow = (alert: AnomalyEvent, key: string, countBadge?: number) => (
    <Box
      key={key}
      onClick={() => onAlertClick(alert)}
      sx={{
        borderLeft: 4,
        borderColor: SEVERITY_BORDER[alert.severity] ?? "warning.main",
        pl: 1.5,
        py: 0.5,
        cursor: "pointer",
        borderRadius: "0 4px 4px 0",
        "&:hover": { bgcolor: "action.hover" },
      }}
    >
      <Stack direction="row" spacing={0.75} alignItems="center" sx={{ mb: 0.3 }}>
        <Chip
          size="small"
          label={alert.severity}
          color={SEVERITY_CHIP_COLOR[alert.severity] ?? "default"}
          sx={{ height: 18, fontSize: "0.62rem", fontWeight: 700 }}
        />
        {countBadge !== undefined && countBadge > 1 && (
          <Chip size="small" label={`${countBadge} signals`} variant="outlined" sx={{ height: 18, fontSize: "0.62rem" }} />
        )}
        <Typography variant="subtitle2" sx={{ fontSize: "0.8rem" }}>
          {ANOMALY_TYPE_LABEL[alert.anomaly_type] ?? alert.anomaly_type.replaceAll("_", " ")}
        </Typography>
      </Stack>
      <Typography variant="body2" sx={{ fontSize: "0.78rem" }}>{alert.detail}</Typography>
      <Typography variant="caption" color="text.secondary">
        {alert.source_place ? `${alert.source_place} · ` : ""}
        {utcDateTimeLabel(
          alert.event_time && parseApiDate(alert.event_time).getUTCFullYear() > 2000
            ? alert.event_time : alert.detected_at
        )}
      </Typography>
    </Box>
  );

  return (
    <Stack spacing={1.5}>
      {Object.keys(typeCounts).length > 0 && (
        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
          {Object.entries(typeCounts)
            .sort((a, b) => b[1] - a[1])
            .map(([type, count]) => (
              <Chip
                key={type}
                size="small"
                label={`${ANOMALY_TYPE_LABEL[type] ?? type.replaceAll("_", " ")} · ${count}`}
                clickable
                variant={typeFilter === type ? "filled" : "outlined"}
                color={typeFilter === type ? "primary" : "default"}
                onClick={() => onTypeFilter(typeFilter === type ? "" : type)}
              />
            ))}
        </Stack>
      )}
      <Stack spacing={1}>
        {visible.length === 0 ? (
          <Typography color="text.secondary" variant="body2">No signals detected yet.</Typography>
        ) : clusters
          ? clusters.map(({ top, count }) => alertRow(top, `cluster-${top.anomaly_id}`, count))
          : visible.map(alert => alertRow(alert, alert.anomaly_id))
        }
      </Stack>
    </Stack>
  );
}
