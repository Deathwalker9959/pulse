from __future__ import annotations

import asyncio
import math
import statistics
from collections import Counter
from datetime import datetime, timezone

import pygeohash

from models import AnomalyEvent, AnomalyType, EarthquakeEvent, Severity
from models.anomaly import _anomaly_id

MAG_HISTORY_KEY = "pulse:signal:mag-history"
ENERGY_HISTORY_KEY = "pulse:signal:energy-history"
RATE_HISTORY_KEY = "pulse:signal:rate-history"
SWARM_PREFIX = "pulse:signal:swarm:"
MAINSHOCK_PREFIX = "pulse:signal:mainshock:"
MAINSHOCK_TTL = 48 * 3600
DEEP_FOCUS_PREFIX = "pulse:signal:deepfocus:"
DEEP_FOCUS_TTL = 24 * 3600
DEEP_FOCUS_THRESHOLD = 3
B_VALUE_MC = 2.5
B_VALUE_MIN_SAMPLE = 20
FORESHOCK_PREFIX = "pulse:signal:foreshock:"
FORESHOCK_TTL = 72 * 3600
FORESHOCK_MIN_RECENT = 3
FORESHOCK_FREQ_RATIO = 2.0
FORESHOCK_MAG_DELTA = 0.5


async def _rolling_zscore(redis, key: str, current: float, window: int = 12, ttl: int = 3600) -> float | None:
    """Push `current` onto a Redis list, keep last `window` values, return z-score vs history.

    Returns None when there are fewer than 4 prior values or zero standard deviation.
    """
    history_raw = await redis.lrange(key, 0, -1)
    await redis.lpush(key, current)
    await redis.ltrim(key, 0, window - 1)
    await redis.expire(key, ttl)
    if len(history_raw) < 4:
        return None
    history = [float(v) for v in history_raw]
    stdev = statistics.stdev(history)
    if stdev == 0:
        return None
    return (current - statistics.mean(history)) / stdev


def _geohash(event: EarthquakeEvent, precision: int) -> str:
    try:
        return pygeohash.encode(event.latitude, event.longitude, precision=precision)
    except Exception:
        return ""


async def detect_anomalies(events: list[EarthquakeEvent], redis) -> list[AnomalyEvent]:
    sync = (
        _significant_events(events)
        + _tsunami_risk(events)
        + _b_value_shift(events)
        + _data_quality(events)
    )
    batches = await asyncio.gather(
        _magnitude_spike(events, redis),
        _swarm_detection(events, redis),
        _energy_burst(events, redis),
        _aftershock_cascade(events, redis),
        _rate_anomalies(events, redis),
        _deep_focus_cluster(events, redis),
        _foreshock_sequence(events, redis),
    )
    return sync + [item for batch in batches for item in batch]


def _alert(
    event: EarthquakeEvent,
    anomaly_type: AnomalyType,
    severity: Severity,
    detail: str,
) -> AnomalyEvent:
    return AnomalyEvent(
        anomaly_id=_anomaly_id(event.event_id, anomaly_type),
        event_time=event.time,
        anomaly_type=anomaly_type,
        severity=severity,
        source_event_id=event.event_id,
        source_place=event.place,
        latitude=event.latitude,
        longitude=event.longitude,
        detail=detail,
    )


def _significant_events(events: list[EarthquakeEvent]) -> list[AnomalyEvent]:
    result: list[AnomalyEvent] = []
    for event in events:
        if not event.has_position():
            continue
        mag = event.magnitude or 0
        sig = event.significance or 0
        alert = event.alert

        if event.tsunami and mag >= 6.5:
            result.append(_alert(
                event, AnomalyType.TSUNAMI_ALERT, Severity.CRITICAL,
                f"Tsunami alert: M{mag:.1f} near {event.place}",
            ))
        elif alert in {"orange", "red"}:
            result.append(_alert(
                event, AnomalyType.SIGNIFICANT_EVENT, Severity.CRITICAL,
                f"Major impact event: M{mag:.1f}, PAGER {alert}, significance {sig}, {event.place}",
            ))
        elif mag >= 7.0:
            result.append(_alert(
                event, AnomalyType.SIGNIFICANT_EVENT, Severity.CRITICAL,
                f"Major earthquake: M{mag:.1f}, significance {sig}, {event.place}",
            ))
        elif alert == "yellow" or mag >= 6.0 or sig >= 600:
            result.append(_alert(
                event, AnomalyType.SIGNIFICANT_EVENT, Severity.WARNING,
                f"Notable earthquake: M{mag:.1f}, significance {sig}, {event.place}",
            ))
        elif mag >= 5.0 or sig >= 400:
            result.append(_alert(
                event, AnomalyType.SIGNIFICANT_EVENT, Severity.INFO,
                f"Felt/significant earthquake: M{mag:.1f}, significance {sig}, {event.place}",
            ))
    return result


def historical_pattern_anomalies(events: list[EarthquakeEvent]) -> list[AnomalyEvent]:
    """Stateless anomaly pass for historical/catalog backfills.

    Live polling uses Redis-backed rolling state. Historical sync needs event-time windows instead,
    otherwise YTD views only contain simple per-event signals from the backfill path.
    """
    positioned = sorted((event for event in events if event.has_position()), key=lambda event: event.time)
    anomalies: dict[tuple[str, AnomalyType], AnomalyEvent] = {}

    for event in _historical_deep_focus_clusters(positioned):
        anomalies[(event.event_id, AnomalyType.DEEP_FOCUS_CLUSTER)] = _alert(
            event, AnomalyType.DEEP_FOCUS_CLUSTER, Severity.WARNING,
            f"Deep focus cluster: 3+ events >300 km depth in {_geohash(event, 3)} within 24 hours",
        )

    for event, mainshock in _historical_aftershock_cascades(positioned):
        anomalies[(event.event_id, AnomalyType.AFTERSHOCK_CASCADE)] = _alert(
            event, AnomalyType.AFTERSHOCK_CASCADE, Severity.WARNING,
            f"Aftershock cascade: M{event.magnitude:.1f} event near M{mainshock.magnitude:.1f} mainshock ({mainshock.event_id})",
        )

    for event, count, z_score, cell in _historical_swarm_events(positioned):
        anomalies[(event.event_id, AnomalyType.SWARM_DETECTION)] = _alert(
            event, AnomalyType.SWARM_DETECTION, Severity.WARNING,
            f"Regional swarm: {count} events/hour in geohash {cell}, {z_score:.1f} standard deviations above baseline",
        )

    for event, count, ratio, recent_max in _historical_foreshock_sequences(positioned):
        anomalies[(event.event_id, AnomalyType.FORESHOCK_SEQUENCE)] = _alert(
            event, AnomalyType.FORESHOCK_SEQUENCE,
            Severity.WARNING if recent_max >= 5.0 else Severity.INFO,
            f"Foreshock sequence in {_geohash(event, 3)}: {count} events/24h ({ratio:.1f}x accel), max M{recent_max:.1f}.",
        )

    for event, b_value, sample_size in _historical_b_value_anomalies(positioned):
        anomalies[(event.event_id, AnomalyType.B_VALUE_ANOMALY)] = _alert(
            event, AnomalyType.B_VALUE_ANOMALY,
            Severity.CRITICAL if b_value < 0.5 else Severity.WARNING,
            f"B-value anomaly: b={b_value:.2f} (normal ≈ 1.0) from {sample_size} events — elevated crustal stress indicated",
        )

    return list(anomalies.values())


def _historical_deep_focus_clusters(events: list[EarthquakeEvent]) -> list[EarthquakeEvent]:
    result: list[EarthquakeEvent] = []
    by_region: dict[str, list[EarthquakeEvent]] = {}
    for event in events:
        if event.depth_km <= 300:
            continue
        region = _geohash(event, 3)
        if not region:
            continue
        region_events = by_region.setdefault(region, [])
        region_events.append(event)
        cutoff = event.time.timestamp() - 24 * 3600
        region_events[:] = [item for item in region_events if item.time.timestamp() >= cutoff]
        if len(region_events) == DEEP_FOCUS_THRESHOLD:
            result.append(event)
    return result


def _historical_aftershock_cascades(events: list[EarthquakeEvent]) -> list[tuple[EarthquakeEvent, EarthquakeEvent]]:
    result: list[tuple[EarthquakeEvent, EarthquakeEvent]] = []
    mainshocks: dict[str, list[EarthquakeEvent]] = {}
    for event in events:
        region = _geohash(event, 3)
        if not region:
            continue
        cutoff = event.time.timestamp() - MAINSHOCK_TTL
        active = [mainshock for mainshock in mainshocks.get(region, []) if mainshock.time.timestamp() >= cutoff]
        mainshocks[region] = active
        if event.magnitude >= 5.5:
            active.append(event)
            continue
        if active:
            mainshock = max(active, key=lambda item: item.magnitude)
            result.append((event, mainshock))
    return result


def _historical_swarm_events(events: list[EarthquakeEvent]) -> list[tuple[EarthquakeEvent, int, float, str]]:
    by_cell_hour: dict[tuple[str, datetime], list[EarthquakeEvent]] = {}
    for event in events:
        cell = _geohash(event, 5)
        if not cell:
            continue
        hour = event.time.replace(minute=0, second=0, microsecond=0)
        by_cell_hour.setdefault((cell, hour), []).append(event)

    counts_by_cell: dict[str, list[tuple[datetime, int, list[EarthquakeEvent]]]] = {}
    for (cell, hour), items in by_cell_hour.items():
        counts_by_cell.setdefault(cell, []).append((hour, len(items), items))

    result: list[tuple[EarthquakeEvent, int, float, str]] = []
    for cell, buckets in counts_by_cell.items():
        buckets.sort(key=lambda item: item[0])
        history: list[int] = []
        for _hour, count, items in buckets:
            if count >= 3 and len(history) >= 4:
                stdev = statistics.stdev(history)
                if stdev > 0:
                    z_score = (count - statistics.mean(history)) / stdev
                    if z_score > 3:
                        result.append((max(items, key=lambda item: item.magnitude), count, z_score, cell))
            history.append(count)
            history = history[-6:]
    return result


def _historical_foreshock_sequences(events: list[EarthquakeEvent]) -> list[tuple[EarthquakeEvent, int, float, float]]:
    result: list[tuple[EarthquakeEvent, int, float, float]] = []
    by_region: dict[str, list[EarthquakeEvent]] = {}
    for event in events:
        region = _geohash(event, 3)
        if not region:
            continue
        region_events = by_region.setdefault(region, [])
        region_events.append(event)
        cutoff_72 = event.time.timestamp() - FORESHOCK_TTL
        region_events[:] = [item for item in region_events if item.time.timestamp() >= cutoff_72]
        cutoff_24 = event.time.timestamp() - 24 * 3600
        recent = [item for item in region_events if item.time.timestamp() >= cutoff_24]
        prior = [item for item in region_events if item.time.timestamp() < cutoff_24]
        if len(recent) < FORESHOCK_MIN_RECENT or not prior:
            continue
        prior_rate_24h = len(prior) / 2.0
        ratio = len(recent) / prior_rate_24h if prior_rate_24h else 0.0
        recent_max = max(item.magnitude for item in recent)
        prior_mean = statistics.mean(item.magnitude for item in prior)
        if ratio >= FORESHOCK_FREQ_RATIO and recent_max >= prior_mean + FORESHOCK_MAG_DELTA:
            result.append((max(recent, key=lambda item: item.magnitude), len(recent), ratio, recent_max))
    return result


def _historical_b_value_anomalies(events: list[EarthquakeEvent]) -> list[tuple[EarthquakeEvent, float, int]]:
    result: list[tuple[EarthquakeEvent, float, int]] = []
    by_region: dict[str, list[EarthquakeEvent]] = {}
    for event in events:
        if event.magnitude < B_VALUE_MC:
            continue
        region = _geohash(event, 3)
        if not region:
            continue
        region_events = by_region.setdefault(region, [])
        region_events.append(event)
        cutoff = event.time.timestamp() - 30 * 24 * 3600
        region_events[:] = [item for item in region_events if item.time.timestamp() >= cutoff]
        if len(region_events) < B_VALUE_MIN_SAMPLE:
            continue
        mean_m = statistics.mean(item.magnitude for item in region_events)
        if mean_m <= B_VALUE_MC:
            continue
        b_value = math.log10(math.e) / (mean_m - B_VALUE_MC)
        if b_value < 0.7:
            result.append((max(region_events, key=lambda item: item.magnitude), b_value, len(region_events)))
    return result

async def _magnitude_spike(events: list[EarthquakeEvent], redis) -> list[AnomalyEvent]:
    if not events:
        return []
    current = max(e.magnitude for e in events)
    z = await _rolling_zscore(redis, MAG_HISTORY_KEY, current)
    if z is None or z <= 2.5:
        return []
    trigger = max(events, key=lambda e: e.magnitude)
    return [_alert(trigger, AnomalyType.MAGNITUDE_SPIKE, Severity.WARNING,
                   f"Magnitude spike: M{current:.1f} is {z:.1f} standard deviations above recent batches")]


async def _swarm_detection(events: list[EarthquakeEvent], redis) -> list[AnomalyEvent]:
    positioned = [event for event in events if event.has_position()]
    if not positioned:
        return []

    counts = Counter(_geohash(event, 5) for event in positioned)
    counts.pop("", None)
    if not counts:
        return []

    geohashes = list(counts)
    z_scores = await asyncio.gather(*(
        _rolling_zscore(redis, f"{SWARM_PREFIX}{geohash}", float(counts[geohash]), window=6)
        for geohash in geohashes
    ))

    result: list[AnomalyEvent] = []
    for geohash, z in zip(geohashes, z_scores):
        current = counts[geohash]
        if current < 3 or z is None or z <= 3:
            continue
        sample = next(e for e in positioned if _geohash(e, 5) == geohash)
        result.append(_alert(sample, AnomalyType.SWARM_DETECTION, Severity.WARNING,
                             f"Regional swarm: {current} events in geohash {geohash}, {z:.1f} standard deviations above baseline"))
    return result


async def _energy_burst(events: list[EarthquakeEvent], redis) -> list[AnomalyEvent]:
    if not events:
        return []
    current = sum(10 ** (1.5 * e.magnitude) for e in events)
    z = await _rolling_zscore(redis, ENERGY_HISTORY_KEY, current)
    if z is None or z <= 2.5:
        return []
    trigger = max(events, key=lambda e: e.magnitude)
    return [_alert(trigger, AnomalyType.ENERGY_BURST, Severity.WARNING,
                   f"Energy burst: cumulative seismic energy {z:.1f} standard deviations above recent batches")]


async def _aftershock_cascade(events: list[EarthquakeEvent], redis) -> list[AnomalyEvent]:
    positioned = [e for e in events if e.has_position()]
    if not positioned:
        return []

    mainshocks = [(event, _geohash(event, 3)) for event in positioned if event.magnitude >= 5.5]
    mainshocks = [(event, geohash) for event, geohash in mainshocks if geohash]
    if mainshocks:
        async with redis.pipeline(transaction=False) as pipe:
            for event, geohash in mainshocks:
                pipe.set(f"{MAINSHOCK_PREFIX}{geohash}", f"{event.event_id}:{event.magnitude:.2f}", ex=MAINSHOCK_TTL)
            await pipe.execute()

    aftershocks = [(event, _geohash(event, 3)) for event in positioned if event.magnitude < 5.5]
    aftershocks = [(event, geohash) for event, geohash in aftershocks if geohash]
    if not aftershocks:
        return []

    async with redis.pipeline(transaction=False) as pipe:
        for _, geohash in aftershocks:
            pipe.get(f"{MAINSHOCK_PREFIX}{geohash}")
        mainshock_raws = await pipe.execute()

    result: list[AnomalyEvent] = []
    for (event, _), mainshock_raw in zip(aftershocks, mainshock_raws):
        if not mainshock_raw:
            continue
        if isinstance(mainshock_raw, bytes):
            mainshock_raw = mainshock_raw.decode()
        try:
            mainshock_id, mainshock_mag = mainshock_raw.rsplit(":", 1)
            mainshock_mag = float(mainshock_mag)
        except (ValueError, AttributeError):
            continue
        if mainshock_id == event.event_id:
            continue
        result.append(_alert(
            event,
            AnomalyType.AFTERSHOCK_CASCADE,
            Severity.WARNING,
            f"Aftershock cascade: M{event.magnitude:.1f} event near M{mainshock_mag:.1f} mainshock ({mainshock_id})",
        ))

    return result


async def _rate_anomalies(events: list[EarthquakeEvent], redis) -> list[AnomalyEvent]:
    z = await _rolling_zscore(redis, RATE_HISTORY_KEY, float(len(events)))
    if z is None or not events:
        return []
    trigger = max(events, key=lambda e: e.magnitude)
    if z > 2.5:
        return [_alert(trigger, AnomalyType.GLOBAL_RATE_SPIKE, Severity.WARNING,
                       f"Global rate spike: {len(events)} events in batch, {z:.1f} standard deviations above baseline")]
    if z < -2.5:
        return [_alert(trigger, AnomalyType.SEISMIC_QUIESCENCE, Severity.WARNING,
                       f"Seismic quiescence: only {len(events)} events in batch, {abs(z):.1f} standard deviations below baseline")]
    return []


def _tsunami_risk(events: list[EarthquakeEvent]) -> list[AnomalyEvent]:
    result: list[AnomalyEvent] = []
    for event in events:
        if not event.has_position() or event.tsunami:
            continue  # tsunami flag already handled by _significant_events
        if event.magnitude >= 7.0 and event.depth_km < 35:
            result.append(_alert(
                event,
                AnomalyType.TSUNAMI_RISK,
                Severity.CRITICAL,
                f"Potential tsunami risk: M{event.magnitude:.1f} at {event.depth_km:.1f} km depth near {event.place}",
            ))
    return result


def _b_value_shift(events: list[EarthquakeEvent]) -> list[AnomalyEvent]:
    # Gutenberg-Richter: b = log10(e) / (mean(M) - Mc); normal b ≈ 1.0, drop < 0.7 → elevated stress
    sample = [e for e in events if e.magnitude >= B_VALUE_MC]
    if len(sample) < B_VALUE_MIN_SAMPLE:
        return []
    mean_m = statistics.mean(e.magnitude for e in sample)
    if mean_m <= B_VALUE_MC:
        return []
    b = math.log10(math.e) / (mean_m - B_VALUE_MC)
    if b >= 0.7:
        return []
    severity = Severity.CRITICAL if b < 0.5 else Severity.WARNING
    trigger = min(sample, key=lambda e: e.magnitude)
    return [_alert(
        trigger,
        AnomalyType.B_VALUE_ANOMALY,
        severity,
        f"B-value anomaly: b={b:.2f} (normal ≈ 1.0) from {len(sample)} events — elevated crustal stress indicated",
    )]


async def _deep_focus_cluster(events: list[EarthquakeEvent], redis) -> list[AnomalyEvent]:
    deep = [e for e in events if e.has_position() and e.depth_km > 300]
    if not deep:
        return []

    items = [(event, _geohash(event, 3)) for event in deep]
    items = [(event, geohash) for event, geohash in items if geohash]
    if not items:
        return []

    async with redis.pipeline(transaction=False) as pipe:
        for _, geohash in items:
            pipe.incr(f"{DEEP_FOCUS_PREFIX}{geohash}")
        counts = await pipe.execute()

    async with redis.pipeline(transaction=False) as pipe:
        for (_, geohash), count in zip(items, counts):
            if count == 1:
                pipe.expire(f"{DEEP_FOCUS_PREFIX}{geohash}", DEEP_FOCUS_TTL)
        await pipe.execute()

    result: list[AnomalyEvent] = []
    for (event, geohash), count in zip(items, counts):
        if count == DEEP_FOCUS_THRESHOLD:
            result.append(_alert(
                event,
                AnomalyType.DEEP_FOCUS_CLUSTER,
                Severity.WARNING,
                f"Deep focus cluster: {count}+ events >300 km depth in region (geohash {geohash}) within 24 hours",
            ))
    return result


def _data_quality(events: list[EarthquakeEvent]) -> list[AnomalyEvent]:
    result: list[AnomalyEvent] = []
    for event in events:
        reason = ""
        if event.depth_km < -10 or event.depth_km > 1000:
            reason = f"implausible depth {event.depth_km:.1f}km"
        elif event.magnitude < -3 or event.magnitude > 10:
            reason = f"implausible magnitude M{event.magnitude:.1f}"
        if reason:
            result.append(_alert(
                event,
                AnomalyType.DATA_QUALITY_ANOMALY,
                Severity.INFO,
                f"Data quality anomaly: {reason} for {event.event_id}",
            ))
        if len(result) >= 5:
            break
    return result


async def _foreshock_sequence(events: list[EarthquakeEvent], redis) -> list[AnomalyEvent]:
    """Detect accelerating seismic sequences that may precede a large mainshock.

    Fires when a geohash-3 region shows both frequency acceleration (2x rate in last 24h vs prior 48h)
    and magnitude escalation (recent max > prior mean + 0.5) within a 72h rolling window.
    """
    positioned = [e for e in events if e.has_position()]
    if not positioned:
        return []

    now_ts = datetime.now(timezone.utc).timestamp()
    h24_ago = now_ts - 86400
    h72_ago = now_ts - 72 * 3600

    regions_updated: set[str] = set()
    async with redis.pipeline(transaction=False) as pipe:
        for event in positioned:
            gh3 = _geohash(event, 3)
            if not gh3:
                continue
            key = f"{FORESHOCK_PREFIX}{gh3}"
            pipe.zadd(key, {f"{event.event_id}:{event.magnitude:.1f}": event.time.timestamp()})
            pipe.expire(key, FORESHOCK_TTL)
            regions_updated.add(gh3)
        await pipe.execute()

    anomalies: list[AnomalyEvent] = []
    for gh3 in regions_updated:
        key = f"{FORESHOCK_PREFIX}{gh3}"
        async with redis.pipeline(transaction=False) as pipe:
            pipe.zremrangebyscore(key, "-inf", h72_ago)
            pipe.zrangebyscore(key, h24_ago, "+inf")
            pipe.zrangebyscore(key, h72_ago, h24_ago)
            _, recent_raw, prior_raw = await pipe.execute()

        if len(recent_raw) < FORESHOCK_MIN_RECENT or not prior_raw:
            continue

        # Normalize prior (48h window) to 24h equivalent for fair rate comparison
        prior_rate_24h = len(prior_raw) / 2.0
        if len(recent_raw) / prior_rate_24h < FORESHOCK_FREQ_RATIO:
            continue

        def _parse_mag(member: bytes | str) -> float:
            s = member.decode() if isinstance(member, bytes) else str(member)
            parts = s.rsplit(":", 1)
            return float(parts[-1]) if len(parts) == 2 else 0.0

        recent_mags = [_parse_mag(m) for m in recent_raw]
        prior_mags = [_parse_mag(m) for m in prior_raw]
        recent_max = max(recent_mags)
        prior_mean = sum(prior_mags) / len(prior_mags)

        if recent_max < prior_mean + FORESHOCK_MAG_DELTA:
            continue

        rep = max(
            (e for e in positioned if _geohash(e, 3) == gh3),
            key=lambda e: e.magnitude,
            default=None,
        )
        if rep is None:
            continue

        freq_ratio = len(recent_raw) / prior_rate_24h
        severity = Severity.WARNING if recent_max >= 5.0 else Severity.INFO
        anomalies.append(_alert(
            rep,
            AnomalyType.FORESHOCK_SEQUENCE,
            severity,
            f"Foreshock sequence in {gh3}: {len(recent_raw)} events/24h ({freq_ratio:.1f}x accel), "
            f"max M{recent_max:.1f}. Monitor for M5+ mainshock within 72h.",
        ))

    return anomalies
