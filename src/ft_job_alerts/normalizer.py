from __future__ import annotations

from typing import Any


def normalize_offer(o: dict[str, Any]) -> dict[str, Any]:
    """Normalize a raw API offer into our storage format.
    Keeps only fields we persist and fills safe defaults.
    """
    oid = str(o.get("id") or o.get("offerId") or o.get("reference") or o.get("idOffre") or "")
    title = o.get("intitule") or o.get("title") or ""
    company = (o.get("entreprise") or {}).get("nom") if isinstance(o.get("entreprise"), dict) else (o.get("company") or "")

    city = ""
    department = ""
    postal_code = ""
    latitude = None
    longitude = None
    location = None
    if isinstance(o.get("lieuTravail"), dict):
        lt = o["lieuTravail"]
        city = lt.get("libelle") or lt.get("ville") or ""
        department = lt.get("departement") or lt.get("codePostal", "")[:2]
        postal_code = lt.get("codePostal") or ""
        latitude = lt.get("latitude")
        longitude = lt.get("longitude")
        location = f"{city} ({department})".strip()
    else:
        location = o.get("location") or ""

    contract = o.get("typeContrat") or o.get("contractType") or ""
    published = o.get("dateCreation") or o.get("publishedAt") or o.get("publication") or ""
    url = None
    if isinstance(o.get("origineOffre"), dict):
        url = o["origineOffre"].get("urlOrigine") or o["origineOffre"].get("url")
        origin_code = o["origineOffre"].get("origine")
    else:
        origin_code = None
    if not url:
        url = o.get("url") or ""
    apply_url = o.get("lienPostuler") or url
    salary = o.get("salaire", {}).get("libelle") if isinstance(o.get("salaire"), dict) else (o.get("salary") or "")
    description = o.get("description") or ""
    shortage = o.get("offresManqueCandidats")

    return {
        "offer_id": oid,
        "title": title,
        "company": company or "",
        "location": location or "",
        "contract_type": contract or "",
        "published_at": published or "",
        # Fallback to candidate site detail page if URL missing
        "url": (url or (f"https://candidat.francetravail.fr/offres/recherche/detail/{oid}" if oid else "")),
        "apply_url": apply_url or "",
        "salary": salary or "",
        "description": description or "",
        "origin_code": origin_code,
        "offres_manque_candidats": int(bool(shortage)) if shortage is not None else None,
        "city": city or "",
        "department": department or "",
        "postal_code": postal_code or "",
        "latitude": latitude,
        "longitude": longitude,
        # filled later
        "rome_codes": [],
        "keywords": [],
        "score": 0.0,
    }

