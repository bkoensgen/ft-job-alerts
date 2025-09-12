from __future__ import annotations

import argparse
import datetime as dt
from typing import Any

from .auth import AuthClient
from .clients import OffresEmploiClient, ROMEClient
from .config import load_config
from .filters import is_relevant
from .notifier import format_offers, notify
from .scoring import score_offer
from .storage import due_followups, init_db, recent_new_offers, upsert_offers, mark_notified, query_offers
from .exporter import export_txt, export_md, export_csv, export_jsonl
from .tags import compute_labels
from .storage import update_offer_details


def normalize_offer(o: dict[str, Any]) -> dict[str, Any]:
    # Normalize a raw API offer into our storage format
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


def cmd_init_db(_args):
    init_db()
    print("DB initialized at data/ft_jobs.db")


def cmd_set_status(args):
    from .storage import set_status

    set_status(args.offer_id, args.status)
    print(f"Offer {args.offer_id} set to {args.status}")


def cmd_fetch(args):
    cfg = load_config()
    auth = AuthClient(cfg)
    client = OffresEmploiClient(cfg, auth)
    rome = ROMEClient(cfg)

    if cfg.api_simulate:
        print("[info] FT_API_SIMULATE=1 → utilisation des données d'exemple locales (pas d'appel réseau)")
        print("       Mettez FT_API_SIMULATE=0 + FT_CLIENT_ID/FT_CLIENT_SECRET pour interroger l'API réelle.")

    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()] if args.keywords else cfg.default_keywords
    rome_codes = []
    if args.rome:
        rome_codes = [r.strip() for r in args.rome.split(",") if r.strip()]
    elif args.auto_rome:
        rome_codes = rome.map_keywords_to_rome(keywords)

    # Location parameters
    departements = None
    if args.dept:
        departements = [d.strip() for d in str(args.dept).split(",") if d.strip()]
    commune = args.commune
    # `distance` only applies if `commune` is set. Keep radius_km for backward compat.
    distance_km = args.distance_km if args.distance_km is not None else args.radius_km
    if distance_km is not None and not commune:
        print("[warn] --distance-km/--radius-km est ignoré si --commune n'est pas fourni (API FT)")

    # Normalize publieeDepuis to allowed values (1,3,7,14,31)
    pdays = args.published_since_days
    if pdays is not None:
        allowed = [1, 3, 7, 14, 31]
        if pdays not in allowed:
            nearest = min(allowed, key=lambda x: abs(x - pdays))
            print(f"[warn] publieeDepuis={pdays} non supporté; utilisation de {nearest} (valeurs permises: 1,3,7,14,31)")
            pdays = nearest

    def do_page(page: int) -> list[dict[str, Any]]:
        return client.search(
            keywords=keywords,
            departements=departements,
            commune=commune,
            distance_km=distance_km,
            rome_codes=rome_codes,
            limit=args.limit,
            page=page,
            sort=args.sort,
            published_since_days=pdays,
            min_creation_date=args.min_creation,
            max_creation_date=args.max_creation,
            origine_offre=args.origine_offre,
        )

    raw_all: list[dict[str, Any]] = []
    if args.fetch_all:
        max_pages = args.max_pages
        for p in range(0, max_pages):
            batch = do_page(p)
            if not batch:
                break
            raw_all.extend(batch)
            if len(batch) < args.limit:
                break
        raw = raw_all
    else:
        raw = do_page(args.page)

    # Filter + score
    base_lat = 47.76
    base_lon = 7.34
    prepared: list[dict[str, Any]] = []
    for r in raw:
        n = normalize_offer(r)
        if not n["offer_id"]:
            continue
        if not is_relevant(n["title"], n.get("description")):
            continue
        n["rome_codes"] = rome_codes
        n["keywords"] = keywords
        n["score"] = score_offer(r, base_lat=base_lat, base_lon=base_lon)
        try:
            import json as _json
            n["raw_json"] = _json.dumps(r, ensure_ascii=False)
        except Exception:
            n["raw_json"] = None
        prepared.append(n)

    inserted = upsert_offers(prepared)
    print(f"Prepared: {len(prepared)} offers; inserted/updated: {inserted}")


def cmd_run_daily(args):
    # Fetch new + notify new + notify follow-ups
    cmd_fetch(args)
    cfg = load_config()
    new_rows = recent_new_offers(limit=30)
    fu_rows = due_followups()
    subject = "FT Job Alerts — New & Follow-ups"
    body_parts = []
    if new_rows:
        body_parts.append("New offers:\n" + format_offers(new_rows))
    if fu_rows:
        body_parts.append("\nDue follow-ups:\n" + format_offers(fu_rows))
    if not body_parts:
        body_parts.append("No new offers or follow-ups today.")
    notify(cfg, subject, "\n\n".join(body_parts))
    # Mark newly notified offers to avoid duplicate alerts next runs
    if new_rows:
        mark_notified([r["offer_id"] for r in new_rows])


def cmd_export(args):
    # Query rows based on filters, export in chosen format
    rows = query_offers(
        days=args.days,
        from_date=args.from_date,
        to_date=args.to_date,
        status=args.status,
        min_score=args.min_score,
        limit=args.limit,
        order_by="score_desc",
    )
    # Enrich with labels for human-friendly txt/md
    if args.format in ("txt", "md"):
        enriched = []
        for r in rows:
            d = {k: r[k] for k in r.keys()}
            d.update(compute_labels(d))
            enriched.append(d)
        rows = enriched  # type: ignore
    if args.format == "txt":
        path = export_txt(rows, args.outfile, desc_chars=args.desc_chars)
    elif args.format == "md":
        path = export_md(rows, args.outfile, desc_chars=args.desc_chars)
    elif args.format == "csv":
        path = export_csv(rows, args.outfile)
    else:
        path = export_jsonl(rows, args.outfile)
    print(f"Exported {len(rows)} rows to {path}")


def cmd_sweep(args):
    cfg = load_config()
    auth = AuthClient(cfg)
    client = OffresEmploiClient(cfg, auth)
    rome = ROMEClient(cfg)

    # Prepare location parameters
    departements = None
    if args.dept:
        departements = [d.strip() for d in str(args.dept).split(",") if d.strip()]
    commune = args.commune
    distance_km = args.distance_km

    # Normalize publieeDepuis
    pdays = args.published_since_days
    allowed = [1, 3, 7, 14, 31]
    if pdays not in allowed:
        pdays = min(allowed, key=lambda x: abs(x - pdays))

    total_prepared = 0
    keywords_groups = [k.strip() for k in str(args.keywords_list).split(";") if k.strip()]
    base_lat, base_lon = 47.76, 7.34
    for kw in keywords_groups:
        # Paging loop
        max_pages = args.max_pages if args.fetch_all else 1
        for page in range(0, max_pages):
            raw = client.search(
                keywords=[kw],
                departements=departements,
                commune=commune,
                distance_km=distance_km,
                rome_codes=None,
                limit=args.limit,
                page=page,
                sort=args.sort,
                published_since_days=pdays,
            )
            if not raw:
                break
            prepared: list[dict[str, Any]] = []
            for r in raw:
                n = normalize_offer(r)
                if not n["offer_id"]:
                    continue
                n["rome_codes"] = []
                n["keywords"] = [kw]
                n["score"] = score_offer(r, base_lat=base_lat, base_lon=base_lon)
                try:
                    import json as _json
                    n["raw_json"] = _json.dumps(r, ensure_ascii=False)
                except Exception:
                    n["raw_json"] = None
                prepared.append(n)
            total_prepared += len(prepared)
            upsert_offers(prepared)
            if len(raw) < args.limit:
                break
    print(f"Sweep complete. Inserted/updated approx: {total_prepared}")


def extract_detail_fields(detail: dict[str, Any]) -> dict[str, Any]:
    # Be tolerant to varying schemas; keep the essentials.
    def _get(d: dict, path: list[str], default=None):
        cur = d
        for k in path:
            if not isinstance(cur, dict):
                return default
            cur = cur.get(k)
        return cur if cur is not None else default

    description = detail.get("description") or _get(detail, ["descriptionOffre"]) or ""
    # Try various keys that may contain an application URL
    apply_url = (
        detail.get("lienPostuler")
        or _get(detail, ["contact", "urlPostulation"])  # per OpenAPI Contact schema
        or _get(detail, ["origineOffre", "urlOrigine"])  # partner/original URL
        or _get(detail, ["origineOffre", "url"])  # fallback if present
        or detail.get("url")
        or ""
    )
    url = (
        _get(detail, ["origineOffre", "urlOrigine"]) 
        or _get(detail, ["origineOffre", "url"]) 
        or detail.get("url") 
        or ""
    )
    salary = _get(detail, ["salaire", "libelle"]) or detail.get("salaire") or ""
    company = _get(detail, ["entreprise", "nom"]) or ""
    import json as _json
    return {
        "description": description,
        "apply_url": apply_url,
        "url": url,
        "salary": salary,
        "company": company,
        "raw_json": _json.dumps(detail, ensure_ascii=False),
    }


def cmd_enrich(args):
    cfg = load_config()
    auth = AuthClient(cfg)
    client = OffresEmploiClient(cfg, auth)

    ids: list[str]
    if args.ids:
        ids = [s.strip() for s in args.ids.split(",") if s.strip()]
    else:
        rows = query_offers(
            days=args.days,
            from_date=args.from_date,
            to_date=args.to_date,
            status=args.status,
            min_score=args.min_score,
            limit=args.limit,
            order_by="date_desc",
        )
        # If only missing description requested, filter here
        if args.only_missing_description:
            rows = [r for r in rows if not (r["description"] and len(str(r["description"]).strip()) >= args.min_desc_len)]
        ids = [r["offer_id"] for r in rows]

    import time
    updated = 0
    for oid in ids:
        try:
            d = client.detail(oid)
            if not d:
                continue
            fields = extract_detail_fields(d)
            # Skip if no new info
            if not any(fields.get(k) for k in ("description", "apply_url", "salary")):
                continue
            update_offer_details(oid, fields)
            updated += 1
            time.sleep(max(0, args.sleep_ms) / 1000.0)
        except Exception as e:
            print(f"enrich: failed {oid}: {e}")
    print(f"Enriched {updated} offers (from {len(ids)})")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ft-job-alerts", description="France Travail job alerts pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    s_init = sub.add_parser("init-db", help="Initialize SQLite DB")
    s_init.set_defaults(func=cmd_init_db)

    s_status = sub.add_parser("set-status", help="Update offer status (e.g., applied)")
    s_status.add_argument("--offer-id", required=True)
    s_status.add_argument("--status", required=True, choices=["new", "applied", "rejected", "to_follow"])
    s_status.set_defaults(func=cmd_set_status)

    s_fetch = sub.add_parser("fetch", help="Fetch (or simulate) and store offers")
    s_fetch.add_argument("--keywords", default=None, help="Comma-separated keywords (default from env)")
    s_fetch.add_argument("--rome", default=None, help="Comma-separated ROME codes (override)")
    s_fetch.add_argument("--auto-rome", action="store_true", help="Derive ROME codes from keywords (stub)")
    s_fetch.add_argument("--dept", default=None, help="Department code(s), comma-separated (e.g., 68 or 68,67)")
    s_fetch.add_argument("--commune", default=None, help="INSEE commune code (required to use --distance-km)")
    s_fetch.add_argument("--distance-km", type=int, default=None, help="Radius in km around --commune (API param distance)")
    s_fetch.add_argument("--radius-km", type=int, default=None, help="Deprecated alias for --distance-km")
    s_fetch.add_argument("--limit", type=int, default=50)
    s_fetch.add_argument("--page", type=int, default=0, help="Page index (multiplies the range window)")
    s_fetch.add_argument("--sort", type=int, choices=[0, 1, 2], default=1,
                         help="0=pertinence/date, 1=date/pertinence, 2=distance/pertinence")
    s_fetch.add_argument("--published-since-days", dest="published_since_days", type=int, default=None,
                         help="Only offers published since N days (allowed: 1,3,7,14,31)")
    s_fetch.add_argument("--min-creation", dest="min_creation", default=None,
                         help="Filter minCreationDate (yyyy-MM-dd'T'hh:mm:ss'Z')")
    s_fetch.add_argument("--max-creation", dest="max_creation", default=None,
                         help="Filter maxCreationDate (yyyy-MM-dd'T'hh:mm:ss'Z')")
    s_fetch.add_argument("--origine-offre", dest="origine_offre", type=int, default=None,
                         help="1 = France Travail, 2 = Partenaire")
    s_fetch.add_argument("--all", dest="fetch_all", action="store_true", help="Fetch all pages until exhausted")
    s_fetch.add_argument("--max-pages", dest="max_pages", type=int, default=10,
                         help="Max pages when using --all")
    s_fetch.set_defaults(func=cmd_fetch)

    s_run = sub.add_parser("run-daily", help="Fetch + notify new and follow-ups")
    s_run.add_argument("--keywords", default=None)
    s_run.add_argument("--rome", default=None)
    s_run.add_argument("--auto-rome", action="store_true")
    s_run.add_argument("--dept", default=None)
    s_run.add_argument("--commune", default=None)
    s_run.add_argument("--distance-km", type=int, default=None)
    s_run.add_argument("--radius-km", type=int, default=None)
    s_run.add_argument("--limit", type=int, default=50)
    s_run.add_argument("--page", type=int, default=0)
    s_run.add_argument("--sort", type=int, choices=[0, 1, 2], default=1)
    s_run.add_argument("--published-since-days", dest="published_since_days", type=int, default=1,
                       help="Allowed values: 1,3,7,14,31 (auto-snap to nearest)")
    s_run.set_defaults(func=cmd_run_daily)

    s_export = sub.add_parser("export", help="Export offers (txt/csv/md/jsonl) for analysis")
    s_export.add_argument("--format", choices=["txt", "csv", "md", "jsonl"], default="txt")
    s_export.add_argument("--days", type=int, default=None, help="Window on inserted_at (last N days)")
    s_export.add_argument("--from", dest="from_date", default=None, help="From date YYYY-MM-DD (inserted_at)")
    s_export.add_argument("--to", dest="to_date", default=None, help="To date YYYY-MM-DD (inserted_at)")
    s_export.add_argument("--status", default=None, help="Filter by status (new,applied,rejected,to_follow)")
    s_export.add_argument("--min-score", dest="min_score", type=float, default=None)
    s_export.add_argument("--top", dest="limit", type=int, default=100)
    s_export.add_argument("--outfile", default=None, help="Output path; defaults to data/out/…")
    s_export.add_argument("--desc-chars", dest="desc_chars", type=int, default=400,
                         help="Include description truncated to N chars (0 to omit)")
    s_export.set_defaults(func=cmd_export)

    s_enrich = sub.add_parser("enrich", help="Fetch offer details to fill full description/apply URL/salary")
    s_enrich.add_argument("--ids", default=None, help="Comma-separated offer IDs to enrich (overrides filters)")
    s_enrich.add_argument("--days", type=int, default=None)
    s_enrich.add_argument("--from", dest="from_date", default=None)
    s_enrich.add_argument("--to", dest="to_date", default=None)
    s_enrich.add_argument("--status", default=None)
    s_enrich.add_argument("--min-score", dest="min_score", type=float, default=None)
    s_enrich.add_argument("--only-missing-description", action="store_true",
                          help="Only enrich offers with empty or very short description")
    s_enrich.add_argument("--min-desc-len", type=int, default=40,
                          help="Threshold for considering a description as present")
    s_enrich.add_argument("--limit", type=int, default=100, help="Max number of offers to enrich")
    s_enrich.add_argument("--sleep-ms", type=int, default=250, help="Delay between calls (rate limit)")
    s_enrich.set_defaults(func=cmd_enrich)

    s_auth = sub.add_parser("auth-check", help="Check OAuth config and attempt to fetch a token (redacted output)")
    s_auth.set_defaults(func=cmd_auth_check)

    s_sweep = sub.add_parser("sweep", help="Run multiple keyword fetches (OR sweep) and consolidate")
    s_sweep.add_argument("--keywords-list", default="robotique;robot;ros2;ros;automatisme;cobot;vision;ivvq;agv;amr",
                         help="Semicolon-separated keyword groups; each entry runs a separate fetch")
    s_sweep.add_argument("--dept", default=None)
    s_sweep.add_argument("--commune", default=None)
    s_sweep.add_argument("--distance-km", type=int, default=None)
    s_sweep.add_argument("--limit", type=int, default=100)
    s_sweep.add_argument("--all", dest="fetch_all", action="store_true")
    s_sweep.add_argument("--max-pages", dest="max_pages", type=int, default=10)
    s_sweep.add_argument("--sort", type=int, choices=[0,1,2], default=1)
    s_sweep.add_argument("--published-since-days", dest="published_since_days", type=int, default=31)
    s_sweep.set_defaults(func=cmd_sweep)

    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    # Dispatch including auth-check defined below
    args.func(args)


def cmd_auth_check(_args):
    cfg = load_config()
    redacted_id = (cfg.client_id[:6] + "…" + cfg.client_id[-4:]) if cfg.client_id else None
    print("Auth endpoint:", cfg.auth_url)
    print("Client ID:", redacted_id)
    print("Use Basic:", cfg.oauth_use_basic)
    print("Scope:", cfg.oauth_scope or "api_offresdemploiv2 o2dsoffre (default)")
    try:
        token = AuthClient(cfg).get_token()
        print("Token OK (length):", len(token))
    except Exception as e:
        print("Auth error:", e)


if __name__ == "__main__":
    main()
