import { Box, Stack, Typography } from "@mui/material";
import { ConnectionChip } from "./ConnectionChip";

export function DashboardHeader({ eventsConnected, alertsConnected }: { eventsConnected: boolean; alertsConnected: boolean }) {
  return (
    <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={2}>
      <Box>
        <Typography variant="h4" fontWeight={700}>PULSE</Typography>
        <Typography color="text.secondary">Real-time seismic intelligence from USGS GeoJSON streams</Typography>
      </Box>
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
        <ConnectionChip label="Events" connected={eventsConnected} />
        <ConnectionChip label="Signals" connected={alertsConnected} />
      </Stack>
    </Stack>
  );
}
