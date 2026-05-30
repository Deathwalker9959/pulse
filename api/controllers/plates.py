"""Tectonic plate lookup by latitude/longitude using real plate boundaries."""

import json
from functools import lru_cache
from pathlib import Path

from shapely.geometry import Point, shape

# Local GeoJSON file (PB2002 tectonic plate model)
PLATES_FILE = Path(__file__).parent.parent / "data" / "tectonic_plates.json"


@lru_cache(maxsize=1)
def _load_plates() -> dict[str, object]:
    """Load and cache tectonic plates GeoJSON."""
    try:
        with open(PLATES_FILE) as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: failed to load plates GeoJSON from {PLATES_FILE}: {e}")
        return {"type": "FeatureCollection", "features": []}


def get_plate(lat: float, lon: float) -> str:
    """Return tectonic plate name for given lat/lon using point-in-polygon.

    Uses real plate boundaries from PB2002 model.
    """
    point = Point(lon, lat)
    geojson = _load_plates()

    for feature in geojson.get("features", []):
        try:
            polygon = shape(feature["geometry"])
            if polygon.contains(point):
                return feature.get("properties", {}).get("PlateName", "Unknown")
        except Exception:
            continue

    return "Unknown"


def list_plates() -> list[str]:
    """Return all available tectonic plates."""
    geojson = _load_plates()
    plates = set()
    for feature in geojson.get("features", []):
        plate_name = feature.get("properties", {}).get("PlateName")
        if plate_name:
            plates.add(plate_name)
    return sorted(list(plates))
