from __future__ import annotations

import json
import logging
from pathlib import Path

import antimeridian
import h3 as h3lib
import pygeohash
from shapely.geometry import Point, shape
from shapely.strtree import STRtree

from decorators import retry
from models import AnomalyEvent, EarthquakeEvent

log = logging.getLogger(__name__)

_PLATES_CACHE: list[tuple[str, object]] | None = None
_BOUNDARY_TREE: STRtree | None = None
_H3_PLATE_MAP: dict[str, tuple[str, float]] | None = None  # cell → (plate_name, boundary_km)

_DATA_DIR = Path(__file__).parent / "data"


def _load_plates() -> list[tuple[str, object]]:
    """
    Load tectonic plate polygons, antimeridian-fixed for valid containment.

    antimeridian.fix_geojson splits Pacific/Antarctic plates that cross ±180°
    into valid MultiPolygons. Shapes are only used for point-in-polygon assignment,
    NOT for boundary distance (the split seam at ±180° is not a real boundary).
    """
    global _PLATES_CACHE
    if _PLATES_CACHE is None:
        with open(_DATA_DIR / "tectonic_plates.json") as f:
            fc = json.load(f)
        fixed = antimeridian.fix_geojson(fc)
        _PLATES_CACHE = [
            (feat["properties"].get("PlateName", "Unknown"), shape(feat["geometry"]))
            for feat in fixed.get("features", [])
        ]
    return _PLATES_CACHE


def _load_boundary_tree() -> STRtree:
    """
    STRtree over PB2002 boundary LineStrings for real boundary distance queries.

    LineStrings have no antimeridian issue. Distance to nearest segment gives
    geologically meaningful boundary proximity.
    """
    global _BOUNDARY_TREE
    if _BOUNDARY_TREE is None:
        with open(_DATA_DIR / "tectonic_boundaries.json") as f:
            fc = json.load(f)
        geoms = [shape(feat["geometry"]) for feat in fc.get("features", [])]
        _BOUNDARY_TREE = STRtree(geoms)
    return _BOUNDARY_TREE


def _build_h3_plate_map() -> dict[str, tuple[str, float]]:
    """
    Pre-compute H3 res-2 cell → (plate_name, boundary_distance_km) at startup (~1s).

    Plate assignment via antimeridian-fixed polygon containment (+ nearest fallback
    for PB2002 ocean gaps). Boundary distance via real PB2002 LineString dataset,
    avoiding the artificial ±180° edge introduced by antimeridian splitting.
    """
    plates = _load_plates()
    plate_names = [name for name, _ in plates]
    plate_polys = [poly for _, poly in plates]
    plate_tree = STRtree(plate_polys)
    boundary_tree = _load_boundary_tree()

    mapping: dict[str, tuple[str, float]] = {}
    for res0_cell in h3lib.get_res0_cells():
        for cell in h3lib.cell_to_children(res0_cell, 2):
            lat, lon = h3lib.cell_to_latlng(cell)
            point = Point(lon, lat)

            # Plate assignment: containment first, nearest fallback for ocean gaps
            candidates = plate_tree.query(point, predicate="contains")
            idx = candidates[0] if len(candidates) > 0 else plate_tree.nearest(point)
            plate_name = plate_names[idx]

            # Boundary distance: nearest real plate boundary LineString (degrees → km)
            nearest_idx = boundary_tree.nearest(point)
            boundary_km = round(boundary_tree.geometries[nearest_idx].distance(point) * 111.32, 1)

            mapping[cell] = (plate_name, boundary_km)

    log.info("H3 plate map built: %d cells assigned to plates", len(mapping))
    return mapping


def assign_plate(latitude: float, longitude: float) -> tuple[str, float]:
    """Assign a tectonic plate via H3 res-2 cell lookup — O(1) after startup."""
    global _H3_PLATE_MAP
    if _H3_PLATE_MAP is None:
        _H3_PLATE_MAP = _build_h3_plate_map()
    cell = h3lib.latlng_to_cell(latitude, longitude, 2)
    return _H3_PLATE_MAP.get(cell, ("Unknown", -1.0))


def magnitude_band(magnitude: float) -> str:
    """Classify a magnitude into a USGS severity band (micro…great) for pre-bucketed aggregation."""
    if magnitude < 1:
        return "micro"
    if magnitude < 3:
        return "minor"
    if magnitude < 5:
        return "light"
    if magnitude < 6:
        return "moderate"
    if magnitude < 7:
        return "strong"
    if magnitude < 8:
        return "major"
    return "great"


def depth_band(depth_km: float) -> str:
    """Classify a hypocenter depth into a band (negative/shallow/intermediate/deep)."""
    if depth_km < 0:
        return "negative"
    if depth_km < 70:
        return "shallow"
    if depth_km < 300:
        return "intermediate"
    return "deep"


def geohash5(latitude: float, longitude: float) -> str:
    """Encode a position as a precision-5 geohash; empty string if the coords can't be encoded."""
    try:
        return pygeohash.encode(latitude, longitude, precision=5)
    except Exception:
        return ""


def earthquake_row(event: EarthquakeEvent) -> dict:
    """Flatten an EarthquakeEvent into a ClickHouse row, adding derived columns (bands, geohash, plate)."""
    plate_name, boundary_km = assign_plate(event.latitude, event.longitude)
    return {
        **event.model_dump(mode="python"),
        "mag_band": magnitude_band(event.magnitude),
        "depth_band": depth_band(event.depth_km),
        "geohash": geohash5(event.latitude, event.longitude),
        "plate_name": plate_name,
        "boundary_distance_km": boundary_km,
    }


async def _insert(client, table: str, rows: list[dict]) -> None:
    """Column-wise insert of dict rows into `table`; no-op on empty input."""
    if not rows:
        return
    columns = list(rows[0].keys())
    await client.insert(table, [[row[c] for c in columns] for row in rows], column_names=columns)


@retry(max_attempts=10, backoff_base=2.0, max_delay=30.0)
async def write_earthquakes(client, events: list[EarthquakeEvent]) -> None:
    """Persist earthquakes to ClickHouse (only those with valid coords), retrying on transient failures."""
    await _insert(client, "earthquakes_raw", [earthquake_row(e) for e in events if e.has_position()])


def anomaly_row(event: AnomalyEvent) -> dict:
    """Flatten an AnomalyEvent into a ClickHouse row, adding plate_name from source event coords."""
    plate_name, _ = assign_plate(event.latitude, event.longitude)
    return {**event.model_dump(mode="python"), "plate_name": plate_name}


@retry(max_attempts=10, backoff_base=2.0, max_delay=30.0)
async def write_anomalies(client, events: list[AnomalyEvent]) -> None:
    """Persist detected anomalies to ClickHouse, retrying on transient failures."""
    await _insert(client, "anomaly_events", [anomaly_row(e) for e in events])
