from __future__ import annotations

import math
import re
from typing import Any


KEYWORD_WEIGHTS: list[tuple[str, float]] = [
    (r"\bros ?2\b|\bros2\b", 3.0),
    (r"\bc\+\+\b|\bcpp\b", 2.5),
    (r"\bvision\b|\bperception\b|\bopencv\b", 1.5),
    (r"\brobot(?:ique|ics)?\b|\bmoveit\b|\burgdf\b|\bgazebo\b|\bisaac\b", 2.0),
    (r"\bslam\b|\bnavigation\b|\bpath planning\b", 1.7),
]


def score_offer(offer: dict[str, Any], *, base_lat: float | None = None, base_lon: float | None = None) -> float:
    text = " ".join(
        [
            str(offer.get("intitule", "")),
            str(offer.get("description", "")),
        ]
    )
    s = 0.0
    for pattern, w in KEYWORD_WEIGHTS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            s += w

    # Contract preference: CDI ≥ CDD ≥ Alternance ≥ Stage
    contrat = str(offer.get("typeContrat", "")).upper()
    if "CDI" in contrat:
        s += 1.5
    elif "CDD" in contrat:
        s += 0.8
    elif "ALTERN" in contrat:
        s += 0.4
    elif "STAGE" in contrat:
        s += 0.3

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
                s += 1.5
            elif d <= 50:
                s += 0.8
            elif d <= 100:
                s += 0.3
    return round(s, 3)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))
