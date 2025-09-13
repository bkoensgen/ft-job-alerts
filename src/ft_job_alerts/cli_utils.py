from __future__ import annotations

from typing import Any, Iterable

from .filters import is_relevant
from .normalizer import normalize_offer
from .scoring import score_offer


def sanitize_published_since(pdays: int | None) -> int | None:
    if pdays is None:
        return None
    allowed = [1, 3, 7, 14, 31]
    if pdays in allowed:
        return pdays
    return min(allowed, key=lambda x: abs(x - int(pdays)))


def dedup_and_prepare_offers(
    raw: Iterable[dict[str, Any]],
    *,
    rome_codes: list[str] | None,
    keywords: list[str],
    base_lat: float | None,
    base_lon: float | None,
    apply_relevance: bool = True,
) -> list[dict[str, Any]]:
    """Normalize raw offers, optionally filter by relevance, score, attach metadata and deduplicate by offer_id."""
    prepared_map: dict[str, dict[str, Any]] = {}
    for r in raw:
        n = normalize_offer(r)
        oid = n.get("offer_id")
        if not oid:
            continue
        if apply_relevance and not is_relevant(n.get("title", ""), n.get("description")):
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

