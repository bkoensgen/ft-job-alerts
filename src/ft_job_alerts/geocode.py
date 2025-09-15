from __future__ import annotations

"""Minimal commune name → INSEE resolver (offline).

Looks up a local alias map in data/communes_alias.json.
Falls back to a small built-in dictionary (Alsace + grandes villes).
All matches are case-insensitive and accent-insensitive.
"""

import json
import os
import urllib.parse
import urllib.request
import unicodedata
from typing import Dict, Tuple, Optional
from .config import load_config


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = _strip_accents(s)
    s = s.replace("'", " ").replace("-", " ")
    s = " ".join(s.split())
    # common abbreviations
    s = s.replace("saint ", "st ")
    return s


def _builtin_aliases() -> Dict[str, str]:
    # key = normalized name, value = INSEE code
    pairs = {
        # Alsace / Grand Est
        "mulhouse": "68224",
        "colmar": "68066",
        "strasbourg": "67482",
        "selestat": "67462",
        "saint louis": "68297",
        "st louis": "68297",
        "illzach": "68154",
        "kingersheim": "68166",
        "wittenheim": "68376",
        "riedsheim": "68270",
        "riedisheim": "68270",
        "rixheim": "68277",
        "thann": "68334",
        "cernay": "68063",
        "altkirch": "68004",
        "dannemarie": "68068",
        # Grandes villes France
        "paris": "75056",
        "lyon": "69123",
        "marseille": "13055",
        "toulouse": "31555",
        "bordeaux": "33063",
        "nantes": "44109",
        "lille": "59350",
        "montpellier": "34172",
        "rennes": "35238",
        "nice": "06088",
        "grenoble": "38185",
        "metz": "57463",
        "nancy": "54395",
        "reims": "51454",
        "dijon": "21231",
        "clermont ferrand": "63113",
        "tours": "37261",
        "orleans": "45234",
        "le havre": "76351",
        "rouen": "76540",
        "caen": "14118",
        "angers": "49007",
        "le mans": "72181",
        "brest": "29019",
        "perpignan": "66136",
        "pau": "64445",
        "bayonne": "64102",
        "annecy": "74010",
        "chambery": "73065",
        "besancon": "25056",
    }
    # normalize keys once
    return { _norm(k): v for k, v in pairs.items() }


def _load_alias_file() -> Dict[str, str]:
    path = os.path.join("data", "communes_alias.json")
    try:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
            if isinstance(obj, dict):
                return { _norm(k): str(v) for k, v in obj.items() if isinstance(k, str) }
            return {}
    except Exception:
        return {}


def _online_lookup(name: str) -> str | None:
    """Try geo.api.gouv.fr to resolve name → INSEE code.

    Uses `GEO_COMMUNES_URL` (default: https://geo.api.gouv.fr/communes) with
    parameters: `nom`, `fields=code,nom,centre`, `boost=population`, `limit=1`.
    Returns INSEE code or None on failure.
    """
    cfg = load_config()
    if not cfg.geocode_online:
        return None
    base = cfg.geocode_communes_url.rstrip("/")
    params = {
        "nom": name,
        "fields": "code,nom,centre",
        "boost": "population",
        "limit": "1",
    }
    url = f"{base}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url)
    if cfg.accept_language:
        req.add_header("Accept-Language", cfg.accept_language)
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            raw = resp.read().decode("utf-8")
            arr = json.loads(raw)
            if isinstance(arr, list) and arr:
                code = arr[0].get("code")
                if code and isinstance(code, str):
                    return code.strip().upper()
    except Exception:
        return None
    return None


def to_insee(commune: str | None) -> Tuple[str | None, str | None]:
    """Return (insee_code, matched_name) or (None, None).

    Accepts names with accents/cases, or direct INSEE codes (5 digits or 2A/2B+3 digits).
    """
    if not commune:
        return None, None
    s = str(commune).strip()
    # Already a valid INSEE code
    import re
    if re.fullmatch(r"\d{5}", s) or re.fullmatch(r"(2A|2B)\d{3}", s, flags=re.I):
        return s.upper(), None

    key = _norm(s)
    # 1) Local alias file
    alias = _load_alias_file()
    code = alias.get(key)
    if code:
        return code, s
    # 2) Built-in minimal fallback
    code = _builtin_aliases().get(key)
    if code:
        return code, s
    # 3) Online lookup (if enabled)
    code = _online_lookup(s)
    if code:
        return code, s
    return None, None


def get_commune_center(commune: str | None) -> Tuple[Optional[float], Optional[float]]:
    """Return approximate (lat, lon) for a commune code or name.

    - Tries online geo.api.gouv.fr (if enabled)
    - Falls back to a tiny builtin mapping for some codes
    """
    code, matched = to_insee(commune)
    if not code:
        return None, None
    # Try online
    cfg = load_config()
    if cfg.geocode_online:
        base = cfg.geocode_communes_url.rstrip("/")
        # Primary: lookup by INSEE code
        params = {"code": code, "fields": "code,centre", "format": "json"}
        url = f"{base}?{urllib.parse.urlencode(params)}"
        try:
            with urllib.request.urlopen(url, timeout=6) as resp:
                raw = resp.read().decode("utf-8")
                arr = json.loads(raw)
                if isinstance(arr, list) and arr:
                    centre = arr[0].get("centre")
                    if isinstance(centre, dict) and centre.get("type") == "Point":
                        coords = centre.get("coordinates")
                        if isinstance(coords, list) and len(coords) == 2:
                            lon, lat = float(coords[0]), float(coords[1])
                            return lat, lon
        except Exception:
            pass
        # Fallback: lookup by name
        name = matched or str(commune or "")
        if name:
            try:
                params = {"nom": name, "fields": "centre", "limit": "1", "boost": "population", "format": "json"}
                url = f"{base}?{urllib.parse.urlencode(params)}"
                with urllib.request.urlopen(url, timeout=6) as resp:
                    raw = resp.read().decode("utf-8")
                    arr = json.loads(raw)
                    if isinstance(arr, list) and arr:
                        centre = arr[0].get("centre")
                        if isinstance(centre, dict) and centre.get("type") == "Point":
                            coords = centre.get("coordinates")
                            if isinstance(coords, list) and len(coords) == 2:
                                lon, lat = float(coords[0]), float(coords[1])
                                return lat, lon
            except Exception:
                pass
    # Fallback to builtin map
    centers = {
        "68224": (47.7500, 7.3400),  # Mulhouse
        "68066": (48.0790, 7.3585),  # Colmar
        "67482": (48.5734, 7.7521),  # Strasbourg
        "75056": (48.8566, 2.3522),  # Paris
        "69123": (45.7640, 4.8357),  # Lyon
        "13055": (43.2965, 5.3698),  # Marseille
    }
    return centers.get(code, (None, None))
