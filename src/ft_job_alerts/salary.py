from __future__ import annotations

import re
from typing import Optional


def _to_float(num: str) -> float:
    # Normalize french/english decimals and thousands
    s = num.replace("\u202f", " ").replace("\xa0", " ")
    s = s.replace(".", "").replace(" ", "")
    s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return float("nan")


def parse_salary_min_monthly(text: str) -> Optional[float]:
    """Parse free-form salary text and return a minimum monthly EUR estimate.
    Heuristics handle: 35k€, €/an, €/mois, €/h, ranges like 2500–3200€.
    Returns None if nothing reliable is found.
    """
    if not text:
        return None
    t = text.lower()
    vals = []  # monthly eur

    # k€ annual: 35k€, 42.5 k€
    for m in re.finditer(r"(\d+(?:[\.,]\d+)?)\s*k\s*€", t):
        v = _to_float(m.group(1)) * 1000.0 / 12.0
        if v == v:  # not NaN
            vals.append(v)

    # explicit annual: 42000 € / an
    for m in re.finditer(r"(\d+(?:[\.,]\d+)?)\s*€[^\n]{0,30}?(?:/\s*an|par an|annuel)", t):
        v = _to_float(m.group(1)) / 12.0
        if v == v:
            vals.append(v)

    # explicit monthly: 2800 € / mois
    for m in re.finditer(r"(\d+(?:[\.,]\d+)?)\s*€[^\n]{0,30}?(?:/\s*mois|par mois)", t):
        v = _to_float(m.group(1))
        if v == v:
            vals.append(v)

    # hourly: 15 €/h → approx monthly (151.67 h)
    for m in re.finditer(r"(\d+(?:[\.,]\d+)?)\s*€[^\n]{0,30}?(?:/\s*h|/\s*heure|par heure)", t):
        v = _to_float(m.group(1)) * 151.67
        if v == v:
            vals.append(v)

    # generic amounts with euro sign, possibly ranges "2500€ - 3200€"
    # We'll take the minimum of any amounts in the text, interpreting as monthly
    # if in a plausible monthly band.
    generic = [
        _to_float(m.group(1))
        for m in re.finditer(r"(\d{3,6}(?:[\.,]\d{3})?|\d{2,3}(?:[\.,]\d{2})?)\s*€", t)
    ]
    for raw in generic:
        if raw != raw:
            continue
        # crude heuristic: if very large, treat as annual
        if raw > 20000:
            vals.append(raw / 12.0)
        elif raw >= 800:  # plausible monthly
            vals.append(raw)
        # else likely hourly/daily with missing unit; ignore

    if not vals:
        return None
    # Return the minimum to be conservative on ranges
    return round(min(vals), 2)

