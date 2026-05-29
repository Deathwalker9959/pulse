import { Button, Card, CardContent, Chip, FormControl, InputLabel, MenuItem, Select, Stack, Typography } from "@mui/material";
import type { RangePreset, TopItem } from "../../api/client";
import { RangePickerButton } from "../RangePickerButton";
import { PRESET_LABELS } from "./constants";

interface DashboardFiltersProps {
  activeRange: RangePreset | null;
  from: string;
  to: string;
  net: string;
  networks: TopItem[];
  onPresetClick: (preset: RangePreset) => void;
  onPickerChange: (from: string, to: string) => void;
  onNetChange: (net: string) => void;
  onClear: () => void;
}

export function DashboardFilters({
  activeRange,
  from,
  to,
  net,
  networks,
  onPresetClick,
  onPickerChange,
  onNetChange,
  onClear,
}: DashboardFiltersProps) {
  return (
    <Card variant="outlined">
      <CardContent>
        <Stack spacing={1.5}>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
            <Typography variant="body2" color="text.secondary">Range:</Typography>
            {PRESET_LABELS.map(({ label, value }) => (
              <Chip key={value} label={label} clickable color={activeRange === value ? "primary" : "default"} onClick={() => onPresetClick(value)} />
            ))}
            <RangePickerButton from={from} to={to} onChange={onPickerChange} />
          </Stack>
          <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems={{ md: "center" }}>
            <FormControl size="small" sx={{ minWidth: 180 }}>
              <InputLabel>Network</InputLabel>
              <Select value={net} label="Network" onChange={event => onNetChange(event.target.value)}>
                <MenuItem value="">All networks</MenuItem>
                {networks.map(item => <MenuItem key={item.label} value={item.label}>{item.label || "Unknown"}</MenuItem>)}
              </Select>
            </FormControl>
            <Button variant="outlined" onClick={onClear}>Clear</Button>
          </Stack>
        </Stack>
      </CardContent>
    </Card>
  );
}
