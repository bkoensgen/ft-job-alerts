from __future__ import annotations

import base64
import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .config import Config


@dataclass
class Token:
    access_token: str
    expires_at: float

    def valid(self) -> bool:
        # small safety margin
        return time.time() < self.expires_at - 30


class AuthClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._cached: Token | None = None

    def get_token(self) -> str:
        if self.cfg.api_simulate:
            # In simulate mode we just return a dummy token
            return "SIMULATED_TOKEN"
        if self._cached and self._cached.valid():
            return self._cached.access_token
        if not self.cfg.client_id or not self.cfg.client_secret:
            raise RuntimeError("Missing FT_CLIENT_ID / FT_CLIENT_SECRET for real API calls")
        token = self._fetch_token()
        self._cached = token
        return token.access_token

    def _fetch_token(self) -> Token:
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.cfg.client_id,
            "client_secret": self.cfg.client_secret,
            # audience/scope sometimes needed depending on habilitation; keep minimal here
        }
        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(self.cfg.auth_url, data=data)
        # Some auth endpoints require Basic auth; left here for completeness
        basic = base64.b64encode(f"{self.cfg.client_id}:{self.cfg.client_secret}".encode()).decode()
        req.add_header("Authorization", f"Basic {basic}")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")

        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
        obj = json.loads(raw)
        access = obj.get("access_token")
        ttl = obj.get("expires_in", 3600)
        if not access:
            raise RuntimeError("No access_token in OAuth response")
        return Token(access_token=access, expires_at=time.time() + float(ttl))

