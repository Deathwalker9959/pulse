import { createContext, useContext, useState, type ReactNode } from "react";

interface FilterState {
  from: string;
  to: string;
  country: string;
}

interface FilterContextValue {
  filters: FilterState;
  setFilters: (f: Partial<FilterState>) => void;
}

const FilterContext = createContext<FilterContextValue | null>(null);

export function FilterProvider({ children }: { children: ReactNode }) {
  const now = new Date();
  const yesterday = new Date(now.getTime() - 86_400_000);

  const [filters, setFiltersState] = useState<FilterState>({
    from: yesterday.toISOString().slice(0, 16),
    to: now.toISOString().slice(0, 16),
    country: "",
  });

  const setFilters = (patch: Partial<FilterState>) =>
    setFiltersState(prev => ({ ...prev, ...patch }));

  return (
    <FilterContext.Provider value={{ filters, setFilters }}>
      {children}
    </FilterContext.Provider>
  );
}

export function useFilters(): FilterContextValue {
  const ctx = useContext(FilterContext);
  if (!ctx) throw new Error("useFilters must be used inside FilterProvider");
  return ctx;
}

export function Filters() {
  const { filters, setFilters } = useFilters();

  return (
    <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", padding: "8px 0" }}>
      <label>
        From&nbsp;
        <input
          type="datetime-local"
          value={filters.from}
          onChange={e => setFilters({ from: e.target.value })}
        />
      </label>
      <label>
        To&nbsp;
        <input
          type="datetime-local"
          value={filters.to}
          onChange={e => setFilters({ to: e.target.value })}
        />
      </label>
      <label>
        Country&nbsp;
        <input
          type="text"
          placeholder="e.g. Germany"
          value={filters.country}
          onChange={e => setFilters({ country: e.target.value })}
          style={{ width: 120 }}
        />
      </label>
    </div>
  );
}
