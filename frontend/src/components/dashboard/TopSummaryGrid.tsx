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
      <TopList title="Top Networks" items={networks} />
      <TopList title="Top Places" items={places} />
      <BandsChart title="Magnitude Bands" data={magnitudeBands} field="mag_band" />
      <BandsChart title="Depth Bands" data={depthBands} field="depth_band" />
    </Box>
  );
}
