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
    url = o.get("origineOffre", {}).get("url") if isinstance(o.get("origineOffre"), dict) else (o.get("url") or "")
    apply_url = o.get("lienPostuler") or url
    salary = o.get("salaire", {}).get("libelle") if isinstance(o.get("salaire"), dict) else (o.get("salary") or "")
    description = o.get("description") or ""

    return {
        "offer_id": oid,
        "title": title,
        "company": company or "",
        "location": location or "",
        "contract_type": contract or "",
        "published_at": published or "",
        "url": url or "",
        "apply_url": apply_url or "",
        "salary": salary or "",
        "description": description or "",
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

    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()] if args.keywords else cfg.default_keywords
    rome_codes = []
    if args.rome:
        rome_codes = [r.strip() for r in args.rome.split(",") if r.strip()]
    elif args.auto_rome:
        rome_codes = rome.map_keywords_to_rome(keywords)

    raw = client.search(
        keywords=keywords,
        dept=args.dept or cfg.default_dept,
        radius_km=args.radius_km or cfg.default_radius_km,
        rome_codes=rome_codes,
        limit=args.limit,
        published_since_days=args.published_since_days,
    )

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
    if args.format == "txt":
        path = export_txt(rows, args.outfile, desc_chars=args.desc_chars)
    elif args.format == "md":
        path = export_md(rows, args.outfile, desc_chars=args.desc_chars)
    elif args.format == "csv":
        path = export_csv(rows, args.outfile)
    else:
        path = export_jsonl(rows, args.outfile)
    print(f"Exported {len(rows)} rows to {path}")


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
    s_fetch.add_argument("--dept", default=None, help="Departement code (e.g., 68)")
    s_fetch.add_argument("--radius-km", type=int, default=None, help="Search radius in km")
    s_fetch.add_argument("--limit", type=int, default=50)
    s_fetch.add_argument("--published-since-days", dest="published_since_days", type=int, default=None,
                         help="Only offers published since N days (if supported by API)")
    s_fetch.set_defaults(func=cmd_fetch)

    s_run = sub.add_parser("run-daily", help="Fetch + notify new and follow-ups")
    s_run.add_argument("--keywords", default=None)
    s_run.add_argument("--rome", default=None)
    s_run.add_argument("--auto-rome", action="store_true")
    s_run.add_argument("--dept", default=None)
    s_run.add_argument("--radius-km", type=int, default=None)
    s_run.add_argument("--limit", type=int, default=50)
    s_run.add_argument("--published-since-days", dest="published_since_days", type=int, default=1)
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

    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
