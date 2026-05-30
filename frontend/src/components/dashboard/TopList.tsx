import { Card, CardContent, Chip, Stack, Tooltip, Typography } from "@mui/material";
import InfoIcon from "@mui/icons-material/Info";
import type { TopItem } from "../../api/client";

interface TopListProps {
  title: string;
  items: TopItem[];
  info?: string;
}

export function TopList({ title, items, info }: TopListProps) {
  return (
    <Card variant="outlined">
      <CardContent>
        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
          <Typography variant="h6">{title}</Typography>
          {info && (
            <Tooltip title={info}>
              <InfoIcon sx={{ fontSize: 20, opacity: 0.6, cursor: "help" }} />
            </Tooltip>
          )}
        </Stack>
        <Stack spacing={1}>
          {items.map(item => (
            <Stack key={item.label} direction="row" justifyContent="space-between">
              <Typography variant="body2" noWrap>{item.label || "Unknown"}</Typography>
              <Chip size="small" label={item.count.toLocaleString()} />
            </Stack>
          ))}
        </Stack>
      </CardContent>
    </Card>
  );
}
