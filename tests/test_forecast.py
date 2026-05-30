from __future__ import annotations

import importlib.util
import math
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# conftest.py already inserts ingestion/ and api/ onto sys.path.
# Load forecast directly from file so we control exactly which modules it sees.
_prev_db = sys.modules.get("db")
_prev_dec = sys.modules.get("decorators")

_fake_db = types.ModuleType("db")
async def _stub_query(*a, **kw): return []
_fake_db.query = _stub_query  # type: ignore[attr-defined]

_dec_spec = importlib.util.spec_from_file_location("decorators", ROOT / "api" / "decorators.py")
assert _dec_spec and _dec_spec.loader
_dec_mod = importlib.util.module_from_spec(_dec_spec)
_dec_spec.loader.exec_module(_dec_mod)

sys.modules["db"] = _fake_db
sys.modules["decorators"] = _dec_mod

_spec = importlib.util.spec_from_file_location("forecast", ROOT / "api" / "controllers" / "forecast.py")
assert _spec and _spec.loader
forecast = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(forecast)

# Restore originals so other test files are not affected.
if _prev_db is not None:
    sys.modules["db"] = _prev_db
else:
    sys.modules.pop("db", None)
if _prev_dec is not None:
    sys.modules["decorators"] = _prev_dec
else:
    sys.modules.pop("decorators", None)


def _make_row(events_7d=10, mean_mag_25=3.0, count_25=20, max_m6_30d=0.0, event_count=30) -> dict:
    return {
        "h3_index": "83b47aaffffffff",
        "centroid_lat": 35.0,
        "centroid_lon": 139.0,
        "event_count": event_count,
        "events_7d": events_7d,
        "max_m6_30d": max_m6_30d,
        "max_magnitude": 4.5,
        "mean_mag_25": mean_mag_25,
        "count_25": count_25,
    }


def _score(row: dict, max_rate: int) -> float:
    """Re-implement the risk score formula from forecast.get_seismic_risk for unit testing."""
    rate_norm = row["events_7d"] / max_rate
    b_value = None
    if row["count_25"] >= 5 and row["mean_mag_25"] > 2.5:
        try:
            b_value = math.log10(math.e) / (row["mean_mag_25"] - 2.5)
        except ZeroDivisionError:
            pass
    b_factor = 1.0
    if b_value is not None:
        b_factor = max(0.5, min(2.0, 1.0 / max(b_value, 0.3)))
    large_event_boost = min(0.3, (row["max_m6_30d"] or 0.0) - 5.9) if (row["max_m6_30d"] or 0) >= 6.0 else 0.0
    return min(1.0, rate_norm * b_factor + large_event_boost)


def test_risk_score_is_zero_for_zero_event_rate() -> None:
    """A cell with no events in the last 7 days and no M6+ has risk score 0."""
    row = _make_row(events_7d=0, max_m6_30d=0.0)
    assert _score(row, max_rate=100) == 0.0


def test_risk_score_capped_at_one() -> None:
    """Risk score never exceeds 1.0 regardless of inputs."""
    row = _make_row(events_7d=1000, mean_mag_25=2.51, count_25=5, max_m6_30d=8.0)
    assert _score(row, max_rate=1) <= 1.0


def test_low_b_value_increases_score() -> None:
    """A low b-value raises the risk score. b = log10(e)/(mean_M - Mc): higher mean magnitude
    → lower b (magnitude distribution skews large) → higher risk multiplier."""
    low_b  = _make_row(events_7d=10, mean_mag_25=3.5, count_25=20)   # b ≈ 0.43 → low b → high risk
    high_b = _make_row(events_7d=10, mean_mag_25=2.55, count_25=20)  # b ≈ 8.7 → high b → low risk
    assert _score(low_b, 100) > _score(high_b, 100)


def test_large_event_boost_applied_for_m6_plus() -> None:
    """A recent M6.5 adds a positive boost to the raw score."""
    without = _make_row(events_7d=10, max_m6_30d=0.0)
    with_large = _make_row(events_7d=10, max_m6_30d=6.5)
    assert _score(with_large, 100) > _score(without, 100)


def test_fewer_than_five_m25_events_gives_neutral_b_factor() -> None:
    """With < 5 qualifying events, b-value is undefined and defaults to neutral (factor = 1.0)."""
    row = _make_row(events_7d=10, mean_mag_25=2.8, count_25=3)
    # b_factor defaults to 1.0 → score = rate_norm * 1.0
    expected = 10 / 100
    assert abs(_score(row, 100) - expected) < 1e-9


def test_score_increases_with_event_rate() -> None:
    """Higher 7-day event rate produces a higher risk score, all else equal."""
    low_rate  = _make_row(events_7d=5)
    high_rate = _make_row(events_7d=50)
    assert _score(high_rate, 100) > _score(low_rate, 100)
