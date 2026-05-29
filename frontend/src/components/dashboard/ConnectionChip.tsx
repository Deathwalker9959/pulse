import { Chip } from "@mui/material";

export function ConnectionChip({ label, connected }: { label: string; connected: boolean }) {
  return <Chip size="small" color={connected ? "success" : "default"} label={`${label}: ${connected ? "live" : "connecting"}`} />;
}
