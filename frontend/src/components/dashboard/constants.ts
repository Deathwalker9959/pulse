import type { RangePreset } from "../../api/client";

export const PRESET_LABELS: { label: string; value: RangePreset }[] = [
  { label: "1H", value: "1h" },
  { label: "6H", value: "6h" },
  { label: "24H", value: "24h" },
  { label: "7D", value: "7d" },
  { label: "30D", value: "30d" },
  { label: "YTD", value: "ytd" },
];

export const ANOMALY_TYPE_LABEL: Record<string, string> = {
  SIGNIFICANT_EVENT: "Significant",
  TSUNAMI_ALERT: "Tsunami Alert",
  TSUNAMI_RISK: "Tsunami Risk",
  MAGNITUDE_SPIKE: "Mag Spike",
  SWARM_DETECTION: "Swarm",
  ENERGY_BURST: "Energy Burst",
  AFTERSHOCK_CASCADE: "Aftershock",
  GLOBAL_RATE_SPIKE: "Rate Spike",
  SEISMIC_QUIESCENCE: "Quiescence",
  B_VALUE_ANOMALY: "B-Value",
  DEEP_FOCUS_CLUSTER: "Deep Focus",
  DATA_QUALITY_ANOMALY: "Data Quality",
  FORESHOCK_SEQUENCE: "Foreshock Seq",
};

export const SEVERITY_CHIP_COLOR = {
  CRITICAL: "error",
  WARNING: "warning",
  INFO: "info",
} as const;

export const SEVERITY_BORDER = {
  CRITICAL: "error.main",
  WARNING: "warning.main",
  INFO: "info.main",
} as const;

export const SEV_ORDER: Record<string, number> = {
  CRITICAL: 0,
  WARNING: 1,
  INFO: 2,
};

export const MAG_BAND_LABELS: Record<string, string> = {
  micro: "M < 1",
  minor: "M 1–3",
  light: "M 3–5",
  moderate: "M 5–6",
  strong: "M 6–7",
  major: "M 7–8",
  great: "M 8+",
};

export const DEPTH_BAND_LABELS: Record<string, string> = {
  negative: "< 0 km",
  shallow: "0–70 km",
  intermediate: "70–300 km",
  deep: "> 300 km",
};

export const BAND_LABEL_ORDER: Record<"mag_band" | "depth_band", string[]> = {
  mag_band: ["micro", "minor", "light", "moderate", "strong", "major", "great"],
  depth_band: ["negative", "shallow", "intermediate", "deep"],
};

export const MC = 2.5;
