from __future__ import annotations

from typing import Any, Iterable
import math

from .filters import is_relevant
from .normalizer import normalize_offer
from .scoring import score_offer
from .geocode import to_insee as _to_insee


def sanitize_published_since(pdays: int | None) -> int | None:
    if pdays is None:
        return None
    allowed = [1, 3, 7, 14, 31]
    if pdays in allowed:
        return pdays
    return min(allowed, key=lambda x: abs(x - int(pdays)))


def commune_to_insee(commune: str | None) -> str | None:
    """Accept city names or INSEE codes and return a valid INSEE code.

    - If `commune` looks like an INSEE code, return it uppercased.
    - Otherwise try to resolve by name using a local alias map (accent-insensitive).
    - Returns None if input is empty; raises ValueError if it cannot be resolved.
    """
    if not commune:
        return None
    code, matched = _to_insee(commune)
    if code:
        return code
    raise ValueError(
        "Commune inconnue. Saisissez un code INSEE (ex: 68224) ou un nom de ville connu (ex: Mulhouse)."
    )


def dedup_and_prepare_offers(
    raw: Iterable[dict[str, Any]],
    *,
    rome_codes: list[str] | None,
    keywords: list[str],
    base_lat: float | None,
    base_lon: float | None,
    apply_relevance: bool = True,
    center_lat: float | None = None,
    center_lon: float | None = None,
    max_distance_km: float | None = None,
) -> list[dict[str, Any]]:
    """Normalize raw offers, optionally filter by relevance, score, attach metadata and deduplicate by offer_id."""
    prepared_map: dict[str, dict[str, Any]] = {}

    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c
    for r in raw:
        n = normalize_offer(r)
        oid = n.get("offer_id")
        if not oid:
            continue
        if apply_relevance and not is_relevant(n.get("title", ""), n.get("description")):
            continue
        # Optional strict radius filter (applied client-side)
        if max_distance_km is not None and center_lat is not None and center_lon is not None:
            lat = n.get("latitude")
            lon = n.get("longitude")
            try:
                if lat is None or lon is None:
                    # drop offers without coordinates when radius filter is active
                    continue
                if _haversine(float(center_lat), float(center_lon), float(lat), float(lon)) > float(max_distance_km):
                    continue
            except Exception:
                continue
        n["rome_codes"] = rome_codes or []
        n["keywords"] = keywords
        n["score"] = score_offer(r, base_lat=base_lat, base_lon=base_lon)
        try:
            import json as _json
            n["raw_json"] = _json.dumps(r, ensure_ascii=False)
        except Exception:
            n["raw_json"] = None
        prepared_map[oid] = n
    return list(prepared_map.values())
