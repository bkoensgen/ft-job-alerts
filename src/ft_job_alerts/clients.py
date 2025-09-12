from __future__ import annotations

import json
import os
import pathlib
import urllib.parse
import urllib.request
from typing import Any

from .auth import AuthClient
from .config import Config


class OffresEmploiClient:
    def __init__(self, cfg: Config, auth: AuthClient):
        self.cfg = cfg
        self.auth = auth

    def search(self, *, keywords: list[str], dept: str | None = None, radius_km: int | None = None,
               rome_codes: list[str] | None = None, limit: int = 50, published_since_days: int | None = None) -> list[dict[str, Any]]:
        if self.cfg.api_simulate:
            return self._load_sample()

        params: dict[str, Any] = {}
        if keywords:
            params["motsCles"] = ",".join(keywords)
        if dept:
            # In Offres v2, location can be INSEE code, dept, or lat/lon + distance
            # Here we pass departement code via departement parameter if supported.
            params["departement"] = dept
        if radius_km is not None:
            params["rayon"] = radius_km
        if rome_codes:
            params["codeROME"] = ",".join(rome_codes)
        params["limit"] = min(max(int(limit), 1), 150)
        if published_since_days is not None:
            # Common parameter name in some FT APIs, verify with docs
            params["publieeDepuis"] = int(published_since_days)

        url = f"{self.cfg.offres_search_url}?{urllib.parse.urlencode(params)}"
        token = self.auth.get_token()
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
        obj = json.loads(raw)
        # The exact structure may vary; normalize to a list of offers
        if isinstance(obj, dict) and "resultats" in obj:
            return obj["resultats"]
        if isinstance(obj, list):
            return obj
        return []

    def _load_sample(self) -> list[dict[str, Any]]:
        sample_path = pathlib.Path("data/samples/offres_sample.json")
        if not sample_path.exists():
            return []
        with open(sample_path, "r", encoding="utf-8") as f:
            return json.load(f)


class ROMEClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def map_keywords_to_rome(self, keywords: list[str]) -> list[str]:
        # Stub: provide a very small hand-mapping for robotics-ish keywords.
        # Prefer providing ROME codes manually or use ROMEO v2 later.
        mapping = {
            "ros": ["I1401"],     # placeholder ROME codes; adjust to your need
            "ros2": ["I1401"],
            "robot": ["H1203", "I1401"],
            "vision": ["I1308"],
            "c++": ["M1805"],
        }
        out: set[str] = set()
        for k in keywords:
            k0 = k.lower().strip()
            for key, codes in mapping.items():
                if key in k0:
                    out.update(codes)
        return sorted(out)


class LBBClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def top_companies(self, *, rome_codes: list[str], dept: str, limit: int = 20) -> list[dict[str, Any]]:
        # Stub: return an empty list in simulate mode; integrate later with real API
        return []
