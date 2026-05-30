import { Box } from "@mui/material";
import type { BandBucket, TopItem } from "../../api/client";
import { BandsChart } from "./BandsChart";
import { TopList } from "./TopList";

interface TopSummaryGridProps {
  networks: TopItem[];
  places: TopItem[];
  magnitudeBands: BandBucket[];
  depthBands: BandBucket[];
}

export function TopSummaryGrid({ networks, places, magnitudeBands, depthBands }: TopSummaryGridProps) {
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(4, 1fr)" }, gap: 2 }}>
      <TopList title="Top Networks" items={networks} info="Seismic networks contributing the most events" />
      <TopList title="Top Places" items={places} info="Geographic locations with highest event count" />
      <BandsChart title="Magnitude Bands" data={magnitudeBands} field="mag_band" info="Distribution of events by magnitude range" />
      <BandsChart title="Depth Bands" data={depthBands} field="depth_band" info="Distribution of events by depth range" />
    </Box>
  );
}
