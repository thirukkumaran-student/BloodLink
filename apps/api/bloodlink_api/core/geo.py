"""Geographic helpers (owner: D1, spec §11, §21).

Location is *internal matching data*. Two rules apply everywhere:

1. Exact coordinates are never serialised to ordinary API responses.
2. Only coarse distance bands reach a hospital-facing view (``~4 km away``).

Engines
-------
Coordinates are stored as plain ``Float`` columns, so the same haversine adapter
below serves SQLite *and* PostgreSQL — matching behaves identically on both, and
no PostGIS extension is required to run on PostgreSQL (see ``docs/database.md``).

``BLOODLINK_GEO_BACKEND=postgis`` is reserved: it is validated and logged, but the
engine keeps using this adapter until an index-backed implementation lands. If you
set it, the API logs a warning at startup rather than pretending the swap happened.
"""

from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def bounding_box(latitude: float, longitude: float, radius_km: float) -> dict[str, float]:
    """Cheap SQL-side pre-filter box around a point."""
    lat_delta = radius_km / 111.32
    denominator = 111.32 * max(0.1, math.cos(math.radians(latitude)))
    lon_delta = radius_km / denominator
    return {
        "min_lat": latitude - lat_delta,
        "max_lat": latitude + lat_delta,
        "min_lon": longitude - lon_delta,
        "max_lon": longitude + lon_delta,
    }


def distance_km(
    *,
    from_lat: float | None,
    from_lon: float | None,
    to_lat: float | None,
    to_lon: float | None,
) -> float | None:
    if None in (from_lat, from_lon, to_lat, to_lon):
        return None
    return haversine_km(float(from_lat), float(from_lon), float(to_lat), float(to_lon))


def distance_band(km: float | None) -> str:
    """Coarse, privacy-preserving distance label (spec §21)."""
    if km is None:
        return "Distance unavailable"
    if km < 1:
        return "< 1 km away"
    if km < 5:
        return f"~{max(1, round(km))} km away"
    if km < 10:
        return f"~{round(km / 2) * 2} km away"
    if km < 40:
        return f"~{round(km / 5) * 5} km away"
    if km < 100:
        return f"~{round(km / 10) * 10} km away"
    return "> 100 km away"


def coarse_area(latitude: float | None, longitude: float | None) -> str | None:
    """Neighbourhood-level label: coordinates snapped to a ~0.05° grid.

    Deliberately imprecise (~5 km) so it can be shown in coordination views
    without revealing a home address.
    """
    if latitude is None or longitude is None:
        return None
    return f"{round(float(latitude) / 0.05) * 0.05:.2f}, {round(float(longitude) / 0.05) * 0.05:.2f}"


def rounded_km(km: float | None) -> float | None:
    """Round to whole kilometres — the only precision hospitals ever see."""
    return None if km is None else float(round(km))
