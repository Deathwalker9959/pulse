import { Card, CardContent, Stack, Typography } from "@mui/material";
import type { ReactNode } from "react";

export function MetricCard({ title, value, icon }: { title: string; value: string; icon: ReactNode }) {
  return (
    <Card variant="outlined">
      <CardContent>
        <Stack direction="row" alignItems="center" spacing={1}>
          {icon}
          <Typography color="text.secondary" variant="body2">{title}</Typography>
        </Stack>
        <Typography variant="h4" sx={{ mt: 1 }}>{value}</Typography>
      </CardContent>
    </Card>
  );
}
