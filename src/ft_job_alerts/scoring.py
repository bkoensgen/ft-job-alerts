from __future__ import annotations

import math
import re
from typing import Any
try:
    from .salary import parse_salary_min_monthly as _parse_salary
except Exception:
    _parse_salary = None  # type: ignore


KEYWORD_WEIGHTS: list[tuple[str, float]] = [
    (r"\bros ?2\b|\bros2\b", 3.0),
    (r"\bc\+\+\b|\bcpp\b", 2.5),
    (r"\bvision\b|\bperception\b|\bopencv\b", 1.5),
    (r"\brobot(?:ique|ics)?\b|\bmoveit\b|\burgdf\b|\bgazebo\b|\bisaac\b", 2.0),
    (r"\bslam\b|\bnavigation\b|\bpath planning\b", 1.7),
]


def score_offer(
    offer: dict[str, Any],
    *,
    base_lat: float | None = None,
    base_lon: float | None = None,
    weights: dict[str, float] | None = None,
) -> float:
    """Compute a simple score with optional weights.

    weights keys (defaults):
      - w_keywords (1.0)
      - w_contract (1.0)
      - w_distance (1.0)
      - w_salary (1.0)
    """
    w = {
        "w_keywords": 1.0,
        "w_contract": 1.0,
        "w_distance": 1.0,
        "w_salary": 1.0,
    }
    if isinstance(weights, dict):
        w.update({k: float(v) for k, v in weights.items() if k in w})
    text = " ".join(
        [
            str(offer.get("intitule", "")),
            str(offer.get("description", "")),
        ]
    )
    s = 0.0
    for pattern, w in KEYWORD_WEIGHTS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            s += w * w_weights  # type: ignore[name-defined]
    # local alias for readability (post-assign)
    w_keywords = w["w_keywords"]
    # Replace previous use now that we created local
    s = 0.0
    for pattern, weight in KEYWORD_WEIGHTS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            s += weight * w_keywords

    # Contract preference: CDI ≥ CDD ≥ Alternance ≥ Stage
    contrat = str(offer.get("typeContrat", "")).upper()
    if "CDI" in contrat:
        s += 1.5 * w["w_contract"]
    elif "CDD" in contrat:
        s += 0.8 * w["w_contract"]
    elif "ALTERN" in contrat:
        s += 0.4 * w["w_contract"]
    elif "STAGE" in contrat:
        s += 0.3 * w["w_contract"]

    # Distance bonus if coordinates present and base provided
    if base_lat is not None and base_lon is not None:
        lat = None
        lon = None
        if isinstance(offer.get("lieuTravail"), dict):
            lat = offer.get("lieuTravail", {}).get("latitude")
            lon = offer.get("lieuTravail", {}).get("longitude")
        # If already normalized
        lat = offer.get("latitude", lat)
        lon = offer.get("longitude", lon)
        if lat is not None and lon is not None:
            d = haversine_km(float(base_lat), float(base_lon), float(lat), float(lon))
            if d <= 20:
                s += 1.5 * w["w_distance"]
            elif d <= 50:
                s += 0.8 * w["w_distance"]
            elif d <= 100:
                s += 0.3 * w["w_distance"]

    # Salary bonus (rough, uses min monthly salary if parsable)
    if w["w_salary"] > 0:
        txt = str(offer.get("salary") or "") + "\n" + str(offer.get("description") or "")
        try:
            v = _parse_salary(txt) if _parse_salary else None
        except Exception:
            v = None
        if v is not None:
            if v >= 3500:
                s += 1.0 * w["w_salary"]
            elif v >= 3000:
                s += 0.6 * w["w_salary"]
            elif v >= 2500:
                s += 0.3 * w["w_salary"]
    return round(s, 3)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))
