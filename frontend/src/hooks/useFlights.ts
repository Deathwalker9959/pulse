import { useQuery } from "@tanstack/react-query";
import { api, type FlightLive } from "../api/client";

export function useLiveFlights() {
  return useQuery<FlightLive[]>({
    queryKey: ["flights", "live"],
    queryFn: api.flights.live,
    refetchInterval: 10_000,
    staleTime: 9_000,
  });
}

export function useFlightHistory(icao24: string, from: string, to: string) {
  return useQuery({
    queryKey: ["flights", "history", icao24, from, to],
    queryFn: () => api.flights.history(icao24, from, to),
    enabled: Boolean(icao24 && from && to),
  });
}

export function useTopN(field: "origin_country" | "callsign" = "origin_country", from?: string, to?: string) {
  return useQuery({
    queryKey: ["stats", "topn", field, from, to],
    queryFn: () => api.stats.topN(field, 10, from, to),
    refetchInterval: 30_000,
  });
}

export function useHourly(from?: string, to?: string) {
  return useQuery({
    queryKey: ["stats", "hourly", from, to],
    queryFn: () => api.stats.hourly(from, to),
    refetchInterval: 60_000,
  });
}
