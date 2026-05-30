import { useCallback, useEffect, useState } from "react";
import type { RangePreset } from "../api/client";
import { resolveRange } from "./useDashboardData";

export interface Filters {
  activeRange: RangePreset | null;
  from: string;
  to: string;
  net: string;
  plate: string;
  onPresetClick: (preset: RangePreset) => void;
  onPickerChange: (from: string, to: string) => void;
  onNetChange: (net: string) => void;
  onPlateChange: (plate: string) => void;
  clearFilters: () => void;
}

function readParams() {
  return new URLSearchParams(window.location.search);
}

export function useFilters(onRangeChange?: () => void): Filters {
  const [activeRange, setActiveRange] = useState<RangePreset | null>(() => {
    const r = readParams().get("range") as RangePreset | null;
    return r ?? "24h";
  });
  const [from, setFrom] = useState(() => {
    const p = readParams();
    return p.get("from") || resolveRange((p.get("range") as RangePreset) ?? "24h").from;
  });
  const [to, setTo] = useState(() => {
    const p = readParams();
    return p.get("to") || resolveRange((p.get("range") as RangePreset) ?? "24h").to;
  });
  const [net, setNet] = useState(() => readParams().get("net") ?? "");
  const [plate, setPlate] = useState(() => readParams().get("plate") ?? "");

  // Sync filter state → URL (replaceState: no history entry, F5 restores state)
  useEffect(() => {
    const params = new URLSearchParams();
    if (plate) params.set("plate", plate);
    if (net) params.set("net", net);
    if (activeRange) {
      params.set("range", activeRange);
    } else {
      params.set("from", from);
      params.set("to", to);
    }
    const qs = params.toString();
    window.history.replaceState(null, "", qs ? `?${qs}` : window.location.pathname);
  }, [plate, net, activeRange, from, to]);

  const onPresetClick = useCallback((preset: RangePreset) => {
    const range = resolveRange(preset);
    setFrom(range.from);
    setTo(range.to);
    setActiveRange(preset);
    onRangeChange?.();
  }, [onRangeChange]);

  const onPickerChange = useCallback((newFrom: string, newTo: string) => {
    setFrom(newFrom);
    setTo(newTo);
    setActiveRange(null);
    onRangeChange?.();
  }, [onRangeChange]);

  const onNetChange = useCallback((value: string) => setNet(value), []);
  const onPlateChange = useCallback((value: string) => setPlate(value), []);

  const clearFilters = useCallback(() => {
    setNet("");
    setPlate("");
    const range = resolveRange("24h");
    setFrom(range.from);
    setTo(range.to);
    setActiveRange("24h");
    onRangeChange?.();
  }, [onRangeChange]);

  return { activeRange, from, to, net, plate, onPresetClick, onPickerChange, onNetChange, onPlateChange, clearFilters };
}
