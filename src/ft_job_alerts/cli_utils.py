from __future__ import annotations

from typing import Any, Iterable
import math
import re
import datetime as dt
import os

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
    require_all: list[str] | None = None,
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
        # Optional semantic relevance
        if apply_relevance and not is_relevant(n.get("title", ""), n.get("description")):
            continue
        # Optional AND filter for keywords
        if require_all:
            text = f"{n.get('title','')}\n{n.get('description','')}"
            ok = True
            for t in require_all:
                tt = str(t).strip()
                if not tt:
                    continue
                # smart word-boundary: if token is alnum only, use \b; else fallback to simple case-insensitive contains
                if re.fullmatch(r"[A-Za-z0-9]+", tt):
                    if not re.search(rf"\b{re.escape(tt)}\b", text, flags=re.IGNORECASE):
                        ok = False
                        break
                else:
                    if re.search(re.escape(tt), text, flags=re.IGNORECASE) is None:
                        ok = False
                        break
            if not ok:
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
        # Optional weights for scoring
        score_w = globals().get("__score_weights__", None)
        n["score"] = score_offer(n, base_lat=base_lat, base_lon=base_lon, weights=score_w)
        try:
            import json as _json
            n["raw_json"] = _json.dumps(r, ensure_ascii=False)
        except Exception:
            n["raw_json"] = None
        prepared_map[oid] = n
    return list(prepared_map.values())


def _slug(text: str, max_len: int = 40) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", text.strip().lower()).strip("-")
    if len(s) > max_len:
        s = s[:max_len].rstrip("-")
    return s or "x"


def suggest_export_filename(
    fmt: str,
    *,
    keywords: list[str] | None = None,
    dept: str | None = None,
    commune: str | None = None,
    distance_km: int | None = None,
    days: int | None = None,
    topn: int | None = None,
    label: str | None = None,
) -> str:
    os.makedirs("data/out", exist_ok=True)
    parts: list[str] = ["offres"]
    if label:
        parts.append(_slug(label))
    if keywords:
        kk = [k for k in keywords if k]
        if kk:
            head = "+".join(_slug(k, 12) for k in kk[:3])
            if len(kk) > 3:
                head += f"+k{len(kk)}"
            parts.append(head)
    if dept:
        parts.append(f"dept{dept}")
    elif commune:
        if distance_km is not None:
            parts.append(f"c{commune}-{int(distance_km)}km")
        else:
            parts.append(f"c{commune}")
    else:
        parts.append("fr")
    if days is not None:
        parts.append(f"d{int(days)}")
    if topn is not None:
        parts.append(f"top{int(topn)}")
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    parts.append(ts)
    name = "_".join(parts) + f".{fmt}"
    return os.path.join("data", "out", name)
