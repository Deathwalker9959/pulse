from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from decorators import cached
from db import query


@cached(ttl=120, key_prefix="forecast:risk")
async def get_seismic_risk(*, redis, resolution: int = 2) -> list[dict]:
    """Probabilistic seismic risk per H3 cell derived from the last 30 days of seismicity.

    Risk score (0–1) is a composite of three Gutenberg-Richter-grounded signals:

      1. Normalised event rate (last 7 days, M≥2.0) — higher rate → higher short-term hazard.
      2. b-value anomaly — the GR b-value measured from the last 30 days of M≥2.5 events.
         A low b-value (< 0.8) indicates the magnitude distribution is skewing towards larger
         earthquakes relative to the global average (~1.0), a recognised precursor signal.
         No b-value (< 5 qualifying events) defaults to neutral (1.0).
      3. Recent large-event boost — any M≥6.0 in the last 30 days raises the score to reflect
         elevated aftershock probability in the Omori-Utsu sense.

    Cell resolution 2 (~500 km edge) is used by default so every cell has enough events for
    a meaningful b-value estimate; resolution 3 (~100 km) is available for denser regions.
    """
    now = datetime.now(timezone.utc)
    t30 = now - timedelta(days=30)
    t7 = now - timedelta(days=7)

    # Use the pre-computed MATERIALIZED column for resolution 2 (no per-row geoToH3 call).
    # Resolution is fixed at 2 (~500 km cells) so every cell has enough events for a
    # meaningful b-value estimate. If a caller passes a different resolution, fall back.
    h3_expr = "h3r2" if resolution == 2 else f"lower(hex(geoToH3(longitude, latitude, {resolution})))"
    rows = await query(f"""
        SELECT
            {h3_expr} AS h3_index,
            avg(latitude)  AS centroid_lat,
            avg(longitude) AS centroid_lon,
            count()        AS event_count,
            countIf(time >= {{t7:DateTime}}) AS events_7d,
            maxIf(toFloat64(magnitude), magnitude >= 6.0) AS max_m6_30d,
            max(toFloat64(magnitude)) AS max_magnitude,
            avgIf(toFloat64(magnitude), magnitude >= 2.5) AS mean_mag_25,
            countIf(magnitude >= 2.5) AS count_25
        FROM earthquakes_raw FINAL
        WHERE time >= {{t30:DateTime}}
          AND magnitude >= 2.0
        GROUP BY h3_index
        HAVING event_count >= 3
        ORDER BY event_count DESC
        LIMIT 2000
    """, {"t30": t30, "t7": t7})

    # Normalise event rate across all cells for relative comparison.
    max_rate = max((r["events_7d"] for r in rows), default=1) or 1

    results: list[dict] = []
    for row in rows:
        rate_norm = row["events_7d"] / max_rate  # 0–1

        # b-value via maximum-likelihood estimator: b = log10(e) / (mean_M - Mc), Mc = 2.5
        b_value: float | None = None
        if row["count_25"] >= 5 and row["mean_mag_25"] > 2.5:
            try:
                b_value = math.log10(math.e) / (row["mean_mag_25"] - 2.5)
            except ZeroDivisionError:
                pass

        # b-value factor: low b → high risk multiplier (capped for stability)
        b_factor = 1.0
        if b_value is not None:
            b_factor = max(0.5, min(2.0, 1.0 / max(b_value, 0.3)))

        # Large-event boost: M≥6.0 in last 30d raises score (Omori aftershock elevation)
        large_event_boost = min(0.3, (row["max_m6_30d"] or 0.0) - 5.9) if (row["max_m6_30d"] or 0) >= 6.0 else 0.0

        raw = rate_norm * b_factor + large_event_boost
        risk_score = round(min(1.0, raw), 3)

        results.append({
            "h3_index": row["h3_index"],
            "centroid_lat": row["centroid_lat"],
            "centroid_lon": row["centroid_lon"],
            "event_count": row["event_count"],
            "event_rate_7d": row["events_7d"],
            "b_value": round(b_value, 3) if b_value is not None else None,
            "max_magnitude": row["max_magnitude"],
            "risk_score": risk_score,
        })

    return results
