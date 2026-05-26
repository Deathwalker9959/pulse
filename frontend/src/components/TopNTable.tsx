import { useState } from "react";
import type { TopNItem } from "../api/client";

interface Props {
  data: TopNItem[];
  onFieldChange: (field: "origin_country" | "callsign") => void;
  field: "origin_country" | "callsign";
}

export function TopNTable({ data, field, onFieldChange }: Props) {
  const maxCount = data[0]?.count ?? 1;

  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        <button
          onClick={() => onFieldChange("origin_country")}
          style={{ fontWeight: field === "origin_country" ? "bold" : "normal" }}
        >
          By Country
        </button>
        <button
          onClick={() => onFieldChange("callsign")}
          style={{ fontWeight: field === "callsign" ? "bold" : "normal" }}
        >
          By Callsign
        </button>
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr>
            <th style={{ textAlign: "left", padding: "4px 8px" }}>#</th>
            <th style={{ textAlign: "left", padding: "4px 8px" }}>
              {field === "origin_country" ? "Country" : "Callsign"}
            </th>
            <th style={{ textAlign: "right", padding: "4px 8px" }}>Flights</th>
            <th style={{ textAlign: "left", padding: "4px 8px" }}></th>
          </tr>
        </thead>
        <tbody>
          {data.map((item, i) => (
            <tr key={item.label} style={{ borderTop: "1px solid #eee" }}>
              <td style={{ padding: "4px 8px", color: "#888" }}>{i + 1}</td>
              <td style={{ padding: "4px 8px" }}>{item.label || "—"}</td>
              <td style={{ padding: "4px 8px", textAlign: "right" }}>{item.count.toLocaleString()}</td>
              <td style={{ padding: "4px 8px" }}>
                <div style={{
                  height: 8, borderRadius: 4, background: "#3b82f6",
                  width: `${(item.count / maxCount) * 100}%`,
                  minWidth: 4,
                }} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
