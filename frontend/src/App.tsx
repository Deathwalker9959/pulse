import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AlertFeed } from "./components/AlertFeed";
import { Filters, FilterProvider, useFilters } from "./components/Filters";
import { FlightChart } from "./components/FlightChart";
import { FlightMap } from "./components/Map";
import { TopNTable } from "./components/TopNTable";
import { useAlerts } from "./hooks/useAlerts";
import { useHourly, useLiveFlights, useTopN } from "./hooks/useFlights";

const queryClient = new QueryClient();

function Dashboard() {
  const [selectedFlight, setSelectedFlight] = useState<string | null>(null);
  const [topNField, setTopNField] = useState<"origin_country" | "callsign">("origin_country");
  const { filters } = useFilters();

  const { data: flights = [] } = useLiveFlights();
  const { data: hourly = [] } = useHourly(filters.from, filters.to);
  const { data: topN = [] } = useTopN(topNField, filters.from, filters.to);
  const { alerts, connected } = useAlerts();

  // Recent alerts (last 60s) for map overlay.
  const recentAlerts = alerts.filter(
    a => Date.now() - new Date(a.detected_at).getTime() < 60_000,
  );

  // Apply country filter to live flights.
  const visibleFlights = filters.country
    ? flights.filter(f => f.origin_country.toLowerCase().includes(filters.country.toLowerCase()))
    : flights;

  return (
    <div style={{ fontFamily: "system-ui, sans-serif", height: "100vh", display: "flex", flexDirection: "column" }}>
      {/* Header */}
      <header style={{ background: "#1e3a5f", color: "#fff", padding: "10px 20px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <strong style={{ fontSize: 18 }}>PULSE</strong>
          <span style={{ marginLeft: 12, opacity: 0.7, fontSize: 13 }}>Real-Time Flight Intelligence</span>
        </div>
        <span style={{ fontSize: 13, opacity: 0.8 }}>{visibleFlights.length.toLocaleString()} aircraft visible</span>
      </header>

      {/* Filters bar */}
      <div style={{ background: "#f8fafc", borderBottom: "1px solid #e2e8f0", padding: "4px 20px" }}>
        <Filters />
      </div>

      {/* Main content */}
      <div style={{ flex: 1, display: "grid", gridTemplateColumns: "1fr 320px", gridTemplateRows: "1fr 260px", overflow: "hidden" }}>
        {/* Map — top left */}
        <div style={{ gridRow: "1 / 2", gridColumn: "1 / 2", position: "relative" }}>
          <FlightMap
            flights={visibleFlights}
            anomalies={recentAlerts}
            onSelect={setSelectedFlight}
          />
        </div>

        {/* Alert feed — top right */}
        <div style={{ gridRow: "1 / 2", gridColumn: "2 / 3", borderLeft: "1px solid #e2e8f0", padding: 12, overflow: "hidden" }}>
          <AlertFeed
            alerts={alerts}
            connected={connected}
            onSelectFlight={setSelectedFlight}
          />
        </div>

        {/* Chart — bottom left */}
        <div style={{ gridRow: "2 / 3", gridColumn: "1 / 2", borderTop: "1px solid #e2e8f0", padding: "12px 20px" }}>
          <strong style={{ fontSize: 13 }}>Hourly Flight Count</strong>
          <FlightChart data={hourly} />
        </div>

        {/* Top-N table — bottom right */}
        <div style={{ gridRow: "2 / 3", gridColumn: "2 / 3", borderTop: "1px solid #e2e8f0", borderLeft: "1px solid #e2e8f0", padding: 12, overflow: "auto" }}>
          <TopNTable data={topN} field={topNField} onFieldChange={setTopNField} />
        </div>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <FilterProvider>
        <Dashboard />
      </FilterProvider>
    </QueryClientProvider>
  );
}
