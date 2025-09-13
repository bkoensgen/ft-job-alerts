from __future__ import annotations

import json
import os
import pathlib
import urllib.parse
import urllib.request
from typing import Any
from urllib.error import HTTPError
import time

from .auth import AuthClient
from .config import Config


class OffresEmploiClient:
    def __init__(self, cfg: Config, auth: AuthClient):
        self.cfg = cfg
        self.auth = auth

    def _do_request(self, req: urllib.request.Request, *, retries: int = 3, backoff: float = 0.5) -> str:
        last_err: Exception | None = None
        for attempt in range(retries):
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    return resp.read().decode("utf-8")
            except HTTPError as e:
                code = getattr(e, 'code', 0)
                body = ''
                try:
                    body = e.read().decode("utf-8")
                except Exception:
                    pass
                # retry on 429 and 5xx
                if code in (429,) or 500 <= code < 600:
                    last_err = RuntimeError(f"HTTP {code}: {body}")
                    time.sleep(backoff * (2 ** attempt))
                    continue
                raise RuntimeError(f"HTTP {code}: {body}")
            except Exception as e:
                last_err = e
                time.sleep(backoff * (2 ** attempt))
        if last_err:
            raise last_err
        return ""

    def search(
        self,
        *,
        keywords: list[str],
        departements: list[str] | None = None,
        commune: str | None = None,
        distance_km: int | None = None,
        rome_codes: list[str] | None = None,
        limit: int = 50,
        page: int = 0,
        sort: int | None = None,
        published_since_days: int | None = None,
        min_creation_date: str | None = None,
        max_creation_date: str | None = None,
        origine_offre: int | None = None,
    ) -> list[dict[str, Any]]:
        if self.cfg.api_simulate:
            return self._load_sample()

        params: dict[str, Any] = {}
        if keywords:
            params["motsCles"] = ",".join(keywords)
        if departements:
            params["departement"] = ",".join([d.strip() for d in departements])
        if commune:
            params["commune"] = commune
            if distance_km is not None:
                params["distance"] = int(distance_km)
        if rome_codes:
            params["codeROME"] = ",".join(rome_codes)
        if sort is not None:
            params["sort"] = int(sort)
        if published_since_days is not None:
            params["publieeDepuis"] = int(published_since_days)
        if min_creation_date:
            params["minCreationDate"] = min_creation_date
        if max_creation_date:
            params["maxCreationDate"] = max_creation_date
        if origine_offre is not None:
            params["origineOffre"] = int(origine_offre)

        # Pagination
        lim = min(max(int(limit), 1), 150)
        start = max(int(page), 0) * lim
        end = start + lim - 1
        use_range_header = self.cfg.range_header
        if not use_range_header:
            params["range"] = f"{start}-{end}"

        url = f"{self.cfg.offres_search_url}?{urllib.parse.urlencode(params)}"
        token = self.auth.get_token()
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Accept", "application/json")
        if self.cfg.accept_language:
            req.add_header("Accept-Language", self.cfg.accept_language)
        if use_range_header:
            req.add_header("Range", f"{start}-{end}")
        if self.cfg.debug:
            print("[debug] GET", url)
            if use_range_header:
                print("[debug] Header Range:", f"{start}-{end}")
        try:
            raw = self._do_request(req)
        except Exception as e:
            raise RuntimeError(f"Offres search failed for URL: {url}\n{e}")
        obj = json.loads(raw) if raw else {}
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

    def detail(self, offer_id: str) -> dict[str, Any]:
        if self.cfg.api_simulate:
            path = pathlib.Path("data/samples/offres_detail") / f"{offer_id}.json"
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            return {}
        url = self.cfg.offres_detail_url.replace("{id}", urllib.parse.quote(str(offer_id)))
        token = self.auth.get_token()
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Accept", "application/json")
        if self.cfg.accept_language:
            req.add_header("Accept-Language", self.cfg.accept_language)
        try:
            raw = self._do_request(req)
            return json.loads(raw) if raw else {}
        except Exception as e:
            raise RuntimeError(f"Offres detail failed for {offer_id}: {e}")


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
