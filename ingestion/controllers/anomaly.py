from __future__ import annotations

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


async def detect_anomalies(events: list[EarthquakeEvent], redis) -> list[AnomalyEvent]:
    anomalies: list[AnomalyEvent] = []
    anomalies.extend(_significant_events(events))
    anomalies.extend(_tsunami_risk(events))
    anomalies.extend(await _magnitude_spike(events, redis))
    anomalies.extend(await _swarm_detection(events, redis))
    anomalies.extend(await _energy_burst(events, redis))
    anomalies.extend(await _aftershock_cascade(events, redis))
    anomalies.extend(await _rate_anomalies(events, redis))
    anomalies.extend(await _deep_focus_cluster(events, redis))
    anomalies.extend(_b_value_shift(events))
    anomalies.extend(_data_quality(events))
    anomalies.extend(await _foreshock_sequence(events, redis))
    return anomalies


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


async def _magnitude_spike(events: list[EarthquakeEvent], redis) -> list[AnomalyEvent]:
    if not events:
        return []
    current = max(event.magnitude for event in events)
    history_raw = await redis.lrange(MAG_HISTORY_KEY, 0, -1)
    await redis.lpush(MAG_HISTORY_KEY, current)
    await redis.ltrim(MAG_HISTORY_KEY, 0, 11)
    await redis.expire(MAG_HISTORY_KEY, 3600)
    if len(history_raw) < 4:
        return []
    history = [float(value) for value in history_raw]
    stdev = statistics.stdev(history)
    if stdev == 0:
        return []
    mean = statistics.mean(history)
    z_score = (current - mean) / stdev
    if z_score <= 2.5:
        return []
    trigger = max(events, key=lambda event: event.magnitude)
    return [_alert(
        trigger,
        AnomalyType.MAGNITUDE_SPIKE,
        Severity.WARNING,
        f"Magnitude spike: M{current:.1f} is {z_score:.1f} standard deviations above recent batches",
    )]


async def _swarm_detection(events: list[EarthquakeEvent], redis) -> list[AnomalyEvent]:
    positioned = [event for event in events if event.has_position()]
    if not positioned:
        return []

    def cell(event: EarthquakeEvent) -> str:
        try:
            return pygeohash.encode(event.latitude, event.longitude, precision=5)
        except Exception:
            return ""

    counts = Counter(cell(event) for event in positioned)
    counts.pop("", None)
    if not counts:
        return []

    result: list[AnomalyEvent] = []
    for geohash, current in counts.items():
        key = f"{SWARM_PREFIX}{geohash}"
        history_raw = await redis.lrange(key, 0, -1)
        await redis.lpush(key, current)
        await redis.ltrim(key, 0, 5)
        await redis.expire(key, 3600)
        if current < 3 or len(history_raw) < 4:
            continue
        history = [int(value) for value in history_raw]
        stdev = statistics.stdev(history)
        if stdev == 0:
            continue
        mean = statistics.mean(history)
        z_score = (current - mean) / stdev
        if z_score > 3:
            sample = next(event for event in positioned if cell(event) == geohash)
            result.append(_alert(
                sample,
                AnomalyType.SWARM_DETECTION,
                Severity.WARNING,
                f"Regional swarm: {current} events in geohash {geohash}, {z_score:.1f} standard deviations above baseline",
            ))
    return result


async def _energy_burst(events: list[EarthquakeEvent], redis) -> list[AnomalyEvent]:
    if not events:
        return []
    current = sum(10 ** (1.5 * event.magnitude) for event in events)
    history_raw = await redis.lrange(ENERGY_HISTORY_KEY, 0, -1)
    await redis.lpush(ENERGY_HISTORY_KEY, current)
    await redis.ltrim(ENERGY_HISTORY_KEY, 0, 11)
    await redis.expire(ENERGY_HISTORY_KEY, 3600)
    if len(history_raw) < 4:
        return []
    history = [float(v) for v in history_raw]
    stdev = statistics.stdev(history)
    if stdev == 0:
        return []
    mean = statistics.mean(history)
    z_score = (current - mean) / stdev
    if z_score <= 2.5:
        return []
    trigger = max(events, key=lambda e: e.magnitude)
    return [_alert(
        trigger,
        AnomalyType.ENERGY_BURST,
        Severity.WARNING,
        f"Energy burst: cumulative seismic energy {z_score:.1f} standard deviations above recent batches",
    )]


async def _aftershock_cascade(events: list[EarthquakeEvent], redis) -> list[AnomalyEvent]:
    positioned = [e for e in events if e.has_position()]
    if not positioned:
        return []

    result: list[AnomalyEvent] = []

    for event in positioned:
        if event.magnitude >= 5.5:
            try:
                mainshock_geohash = pygeohash.encode(event.latitude, event.longitude, precision=3)
            except Exception:
                continue
            key = f"{MAINSHOCK_PREFIX}{mainshock_geohash}"
            await redis.set(key, f"{event.event_id}:{event.magnitude:.2f}", ex=MAINSHOCK_TTL)

    for event in positioned:
        if event.magnitude >= 5.5:
            continue
        try:
            geohash3 = pygeohash.encode(event.latitude, event.longitude, precision=3)
        except Exception:
            continue
        key = f"{MAINSHOCK_PREFIX}{geohash3}"
        mainshock_raw = await redis.get(key)
        if not mainshock_raw:
            continue
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
    current = len(events)
    history_raw = await redis.lrange(RATE_HISTORY_KEY, 0, -1)
    await redis.lpush(RATE_HISTORY_KEY, current)
    await redis.ltrim(RATE_HISTORY_KEY, 0, 11)
    await redis.expire(RATE_HISTORY_KEY, 3600)
    if len(history_raw) < 4:
        return []
    history = [int(v) for v in history_raw]
    stdev = statistics.stdev(history)
    if stdev == 0:
        return []
    mean = statistics.mean(history)
    z_score = (current - mean) / stdev
    result: list[AnomalyEvent] = []
    if z_score > 2.5 and events:
        trigger = max(events, key=lambda e: e.magnitude)
        result.append(_alert(
            trigger,
            AnomalyType.GLOBAL_RATE_SPIKE,
            Severity.WARNING,
            f"Global rate spike: {current} events in batch, {z_score:.1f} standard deviations above baseline",
        ))
    elif z_score < -2.5 and events:
        # Significant drop in activity — potential precursor or data gap
        trigger = max(events, key=lambda e: e.magnitude)
        result.append(_alert(
            trigger,
            AnomalyType.SEISMIC_QUIESCENCE,
            Severity.WARNING,
            f"Seismic quiescence: only {current} events in batch, {abs(z_score):.1f} standard deviations below baseline",
        ))
    return result


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
    result: list[AnomalyEvent] = []
    for event in deep:
        try:
            gh = pygeohash.encode(event.latitude, event.longitude, precision=3)
        except Exception:
            continue
        key = f"{DEEP_FOCUS_PREFIX}{gh}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, DEEP_FOCUS_TTL)
        if count == DEEP_FOCUS_THRESHOLD:
            result.append(_alert(
                event,
                AnomalyType.DEEP_FOCUS_CLUSTER,
                Severity.WARNING,
                f"Deep focus cluster: {count}+ events >300 km depth in region (geohash {gh}) within 24 hours",
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
    for event in positioned:
        try:
            gh3 = pygeohash.encode(event.latitude, event.longitude, precision=3)
        except Exception:
            continue
        key = f"{FORESHOCK_PREFIX}{gh3}"
        member = f"{event.event_id}:{event.magnitude:.1f}"
        await redis.zadd(key, {member: event.time.timestamp()})
        await redis.expire(key, FORESHOCK_TTL)
        regions_updated.add(gh3)

    anomalies: list[AnomalyEvent] = []
    for gh3 in regions_updated:
        key = f"{FORESHOCK_PREFIX}{gh3}"
        await redis.zremrangebyscore(key, "-inf", h72_ago)

        recent_raw = await redis.zrangebyscore(key, h24_ago, "+inf")
        prior_raw = await redis.zrangebyscore(key, h72_ago, h24_ago)

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
            (e for e in positioned if _gh3(e) == gh3),
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


def _gh3(event: EarthquakeEvent) -> str:
    try:
        return pygeohash.encode(event.latitude, event.longitude, precision=3)
    except Exception:
        return ""

