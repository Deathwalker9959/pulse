import { Card, CardContent, Stack, Tooltip, Typography } from "@mui/material";
import type { ReactNode } from "react";

interface MetricCardProps {
  title: string;
  value: string;
  icon: ReactNode;
  tooltip?: string;
}

export function MetricCard({ title, value, icon, tooltip }: MetricCardProps) {
  const content = (
    <Card
      variant="outlined"
      sx={{ cursor: "default", pointerEvents: "none", height: "100%" }}
    >
      <CardContent>
        <Stack direction="row" alignItems="center" spacing={1}>
          {icon}
          <Typography color="text.secondary" variant="body2">
            {title}
          </Typography>
        </Stack>
        <Typography variant="h4" sx={{ mt: 1 }}>
          {value}
        </Typography>
      </CardContent>
    </Card>
  );

  return tooltip ? (
    <Tooltip title={tooltip} placement="top">
      <div style={{ pointerEvents: "auto" }}>{content}</div>
    </Tooltip>
  ) : (
    content
  );
}
