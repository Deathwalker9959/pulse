from __future__ import annotations

import io
import math
from datetime import datetime, timedelta, timezone

from PIL import Image, ImageDraw

from decorators import cached
from db import query

_ATLAS_W = 4096
_ATLAS_H = 2048


def _xy(lat: float, lon: float) -> tuple[float, float]:
    """Equirectangular: north pole at image top (y=0)."""
    return ((lon + 180) / 360 * _ATLAS_W, (90 - lat) / 180 * _ATLAS_H)


def _event_fill(magnitude: float) -> tuple[int, int, int, int]:
    alpha = 200 if magnitude >= 4 else 140 if magnitude >= 2 else 97
    if magnitude >= 5: return (249, 115, 22, alpha)
    if magnitude >= 3: return (250, 204, 21, alpha)
    return (34, 197, 94, alpha)


def _cell_fill(max_magnitude: float, ratio: float) -> tuple[int, int, int, int]:
    alpha = int(46 + ratio * 168)  # 0.18 → 0.84 opacity
    if max_magnitude >= 6: return (220, 38, 38, alpha)
    if max_magnitude >= 5: return (249, 115, 22, alpha)
    if max_magnitude >= 3: return (250, 204, 21, alpha)
    return (34, 197, 94, alpha)


def render_events_atlas(events: list[dict]) -> bytes:
    img = Image.new("RGBA", (_ATLAS_W, _ATLAS_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img, "RGBA")
    for ev in sorted(events, key=lambda e: float(e.get("magnitude") or 0)):
        try:
            lat, lon = float(ev["latitude"]), float(ev["longitude"])
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            mag = float(ev.get("magnitude") or 0)
            r = max(8, min(48, int(6 + mag * 6)))
            x, y = _xy(lat, lon)
            draw.ellipse([x - r, y - r, x + r, y + r], fill=_event_fill(mag))
        except (KeyError, TypeError, ValueError):
            continue
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False)
    return buf.getvalue()


def render_heatmap_atlas(cells: list[dict]) -> bytes:
    import h3 as _h3

    img = Image.new("RGBA", (_ATLAS_W, _ATLAS_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img, "RGBA")
    max_count = max((int(c.get("event_count") or 1) for c in cells), default=1)

    for cell in sorted(cells, key=lambda c: int(c.get("event_count") or 0)):
        try:
            h3_index = cell["h3_index"]
            count = int(cell["event_count"])
            max_mag = float(cell.get("max_magnitude") or 0)
        except (KeyError, TypeError, ValueError):
            continue

        try:
            boundary = _h3.cell_to_boundary(h3_index)  # [(lat, lon), ...]
        except Exception:
            continue

        lons = [v[1] for v in boundary]
        if max(lons) - min(lons) > 180:  # antimeridian-crossing cell
            continue

        xy_pts = [_xy(lat, lon) for lat, lon in boundary]
        fill = _cell_fill(max_mag, count / max_count)
        draw.polygon(xy_pts, fill=fill)
        # visible border
        border = (*fill[:3], min(255, fill[3] + 80))
        draw.line(xy_pts + [xy_pts[0]], fill=border, width=3)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False)
    return buf.getvalue()


@cached(ttl=10, key_prefix="earthquakes:live")
async def get_live(*, redis, from_ts: datetime | None = None, to_ts: datetime | None = None, min_magnitude: float = 0.0) -> list[dict]:
    mag_clause = "AND magnitude >= {min_mag:Float32}" if min_magnitude > 0 else ""
    if from_ts or to_ts:
        t0 = from_ts or (datetime.now(timezone.utc) - timedelta(hours=2))
        t1 = to_ts or datetime.now(timezone.utc)
        return await query(f"""
            SELECT
                event_id, time, updated, latitude, longitude, depth_km, magnitude,
                mag_type, place, event_type, status, alert, tsunami, significance,
                net, mag_band, depth_band
            FROM earthquakes_raw FINAL
            WHERE time >= {{t0:DateTime}} AND time <= {{t1:DateTime}} {mag_clause}
            ORDER BY magnitude DESC, time DESC
            LIMIT 5000
        """, {"t0": t0, "t1": t1, "min_mag": min_magnitude})
    return await query(f"""
        SELECT
            event_id, time, updated, latitude, longitude, depth_km, magnitude,
            mag_type, place, event_type, status, alert, tsunami, significance,
            net, mag_band, depth_band
        FROM earthquakes_raw FINAL
        WHERE time >= now() - INTERVAL 2 HOUR {mag_clause}
        ORDER BY time DESC
        LIMIT 5000
    """, {"min_mag": min_magnitude} if min_magnitude > 0 else {})


@cached(ttl=60, key_prefix="earthquakes:heatmap")
async def get_heatmap(*, redis, from_ts: datetime, to_ts: datetime, resolution: int = 3) -> list[dict]:
    return await query("""
        SELECT
            lower(hex(geoToH3(longitude, latitude, {resolution:UInt8}))) AS h3_index,
            count() AS event_count,
            max(magnitude) AS max_magnitude,
            avg(magnitude) AS avg_magnitude,
            avg(latitude) AS centroid_lat,
            avg(longitude) AS centroid_lon
        FROM earthquakes_raw
        WHERE time >= {t0:DateTime} AND time <= {t1:DateTime}
        GROUP BY h3_index
        ORDER BY event_count DESC
        LIMIT 10000
    """, {"t0": from_ts, "t1": to_ts, "resolution": resolution})
