import { Card, CardContent, Chip, Stack, Typography } from "@mui/material";
import type { TopItem } from "../../api/client";

export function TopList({ title, items }: { title: string; items: TopItem[] }) {
  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="h6" gutterBottom>{title}</Typography>
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
