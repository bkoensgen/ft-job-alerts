from __future__ import annotations

import argparse
import datetime as dt
from typing import Any
from argparse import Namespace

from .auth import AuthClient
from .clients import OffresEmploiClient, ROMEClient
from .config import load_config
from .filters import is_relevant
from .notifier import format_offers, notify
from .scoring import score_offer
from .storage import due_followups, init_db, recent_new_offers, upsert_offers, mark_notified, query_offers
from .exporter import export_txt, export_md, export_csv, export_jsonl
from .tags import compute_labels
from .nlp import tokenize, bigrams, log_odds_with_prior
from .storage import update_offer_details
from .charts import build_charts


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
    prepared_map: dict[str, dict[str, Any]] = {}
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
        # Deduplicate by offer_id within this batch (keep last occurrence)
        prepared_map[n["offer_id"]] = n
    prepared: list[dict[str, Any]] = list(prepared_map.values())

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
            prepared_map: dict[str, dict[str, Any]] = {}
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
                prepared_map[n["offer_id"]] = n
            prepared = list(prepared_map.values())
            total_prepared += len(prepared)
            upsert_offers(prepared)
            if len(raw) < args.limit:
                break
    print(f"Sweep complete. Inserted/updated approx: {total_prepared}")


def cmd_stats(args):
    import re, csv, sys
    # Load rows
    rows = query_offers(
        days=args.days,
        from_date=args.from_date,
        to_date=args.to_date,
        status=args.status,
        min_score=args.min_score,
        limit=args.limit,
        order_by="date_desc",
    )

    tokens = [t.strip() for t in str(args.keywords_list).split(";") if t.strip()]
    patterns = []
    for t in tokens:
        if args.mode == "regex":
            pat = re.compile(t, flags=re.IGNORECASE)
        else:
            # smart word boundary: if alnum only, wrap with \b; otherwise use escaped token
            if re.fullmatch(r"[A-Za-z0-9]+", t):
                pat = re.compile(rf"\b{re.escape(t)}\b", flags=re.IGNORECASE)
            else:
                pat = re.compile(re.escape(t), flags=re.IGNORECASE)
        patterns.append((t, pat))

    def count_in_text(pat: re.Pattern, text: str) -> int:
        return len(pat.findall(text))

    # Aggregate
    global_counts = {t: {"offers": 0, "occurrences": 0} for t in tokens}
    by_dept: dict[str, dict[str, dict[str, int]]] = {}
    for r in rows:
        d = {k: r[k] for k in r.keys()}
        text = (d.get("title") or "") + "\n" + (d.get("description") or "")
        dept = d.get("department") or ""
        for t, pat in patterns:
            occ = count_in_text(pat, text)
            if occ > 0:
                global_counts[t]["offers"] += 1
                global_counts[t]["occurrences"] += occ
                if args.group_by == "dept":
                    grp = by_dept.setdefault(dept, {})
                    ctr = grp.setdefault(t, {"offers": 0, "occurrences": 0})
                    ctr["offers"] += 1
                    ctr["occurrences"] += occ

    # Output
    if args.outfile:
        with open(args.outfile, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            if args.group_by == "dept":
                w.writerow(["department", "token", "offers", "occurrences"]) 
                for dept, data in sorted(by_dept.items()):
                    items = list(data.items())
                    items.sort(key=lambda kv: kv[1][args.sort_by], reverse=True)
                    for t, ctr in items:
                        w.writerow([dept, t, ctr["offers"], ctr["occurrences"]])
            else:
                w.writerow(["token", "offers", "occurrences"]) 
                items = list(global_counts.items())
                items.sort(key=lambda kv: kv[1][args.sort_by], reverse=True)
                for t, ctr in items:
                    w.writerow([t, ctr["offers"], ctr["occurrences"]])
        print(f"Stats written to {args.outfile}")
    else:
        def print_table(rows_list):
            # simple columns aligned
            col_widths = [max(len(str(x)) for x in col) for col in zip(*rows_list)]
            for row in rows_list:
                print("  ".join(str(x).ljust(w) for x, w in zip(row, col_widths)))

        if args.group_by == "dept":
            for dept in sorted(by_dept.keys()):
                print(f"\nDepartment: {dept or '-'}")
                items = list(by_dept[dept].items())
                items.sort(key=lambda kv: kv[1][args.sort_by], reverse=True)
                table = [("token", "offers", "occurrences")] + [(t, ctr["offers"], ctr["occurrences"]) for t, ctr in items]
                print_table(table)
        else:
            items = list(global_counts.items())
            items.sort(key=lambda kv: kv[1][args.sort_by], reverse=True)
            table = [("token", "offers", "occurrences")] + [(t, ctr["offers"], ctr["occurrences"]) for t, ctr in items]
            print_table(table)


def cmd_nlp_stats(args):
    # Build two corpora: CORE_ROBOTICS vs other offers, then compute log-odds tokens and bigrams
    rows = query_offers(
        days=args.days,
        from_date=args.from_date,
        to_date=args.to_date,
        status=args.status,
        min_score=args.min_score,
        limit=args.limit,
        order_by="date_desc",
    )
    docs_core: list[list[str]] = []
    docs_other: list[list[str]] = []
    extra_stops = []
    if getattr(args, "stop_add", None):
        extra_stops = [s.strip() for s in str(args.stop_add).split(";") if s.strip()]
    for r in rows:
        d = {k: r[k] for k in r.keys()}
        text = (d.get("title") or "") + "\n" + (d.get("description") or "")
        toks = tokenize(text, keep=["c++","ros2","ros","moveit"], extra_stops=extra_stops)
        from .tags import compute_labels as _cl
        labels = _cl(d)
        if labels.get("CORE_ROBOTICS"):
            docs_core.append(toks)
        else:
            docs_other.append(toks)

    # Count tokens and bigrams
    from collections import Counter
    ca, cb = Counter(), Counter()
    ba, bb = Counter(), Counter()
    # Document frequencies for pruning
    df_tok: Dict[str, int] = {}
    df_big: Dict[str, int] = {}
    total_docs = len(docs_core) + len(docs_other)
    min_df = float(getattr(args, "min_df", 0.005))
    max_df = float(getattr(args, "max_df", 0.4))
    from .nlp import build_stopwords
    stops = build_stopwords(extra_stops)

    def add_doc(tokens: list[str], is_core: bool):
        seen_t = set(tokens)
        for t in seen_t:
            df_tok[t] = df_tok.get(t, 0) + 1
        ca.update(tokens) if is_core else cb.update(tokens)
        bgs = [" ".join(bg) for bg in bigrams(tokens)]
        seen_b = set(bgs)
        for b in seen_b:
            df_big[b] = df_big.get(b, 0) + 1
        ba.update(bgs) if is_core else bb.update(bgs)

    for toks in docs_core:
        add_doc(toks, True)
    for toks in docs_other:
        add_doc(toks, False)

    # Prune tokens by DF and bigrams with only stopwords
    def acceptable_df(df_count: int) -> bool:
        if total_docs == 0:
            return False
        ratio = df_count / total_docs
        return (min_df <= ratio <= max_df)

    def prune_counts(counter: Counter, df_map: Dict[str, int]) -> Counter:
        new = Counter()
        for t, c in counter.items():
            if df_map.get(t) is None:
                continue
            if acceptable_df(df_map.get(t, 0)):
                new[t] = c
        return new

    def is_bigram_stop(b: str) -> bool:
        parts = b.split(" ", 1)
        if len(parts) != 2:
            return True
        a, b2 = parts[0], parts[1]
        return (a in stops) and (b2 in stops)

    ca = prune_counts(ca, df_tok)
    cb = prune_counts(cb, df_tok)
    ba = Counter({k: v for k, v in ba.items() if acceptable_df(df_big.get(k, 0)) and not is_bigram_stop(k)})
    bb = Counter({k: v for k, v in bb.items() if acceptable_df(df_big.get(k, 0)) and not is_bigram_stop(k)})

    # Compute log-odds
    token_scores = log_odds_with_prior(ca, cb, alpha=0.1)
    bigram_scores = log_odds_with_prior(ba, bb, alpha=0.1)

    # Top N
    top = int(args.top)
    toks_top = [(t, int(ca.get(t,0)), round(z,3)) for t, z, _ in token_scores[:top] if ca.get(t,0) > 0]
    bigr_top = [(t, int(ba.get(t,0)), round(z,3)) for t, z, _ in bigram_scores[:top] if ba.get(t,0) > 0]

    if args.outfile_tokens:
        import csv
        with open(args.outfile_tokens, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["token","count_in_core","z_score"])
            for t, c, z in toks_top:
                w.writerow([t, c, z])
        print(f"Tokens written to {args.outfile_tokens}")
    else:
        print("Top tokens (core vs other):")
        rows_tbl = [("token","count","z")] + toks_top
        colw = [max(len(str(x)) for x in col) for col in zip(*rows_tbl)]
        for row in rows_tbl:
            print("  ".join(str(x).ljust(w) for x, w in zip(row, colw)))


def cmd_watchlist(args):
    import csv
    rows = query_offers(
        days=args.days,
        from_date=args.from_date,
        to_date=args.to_date,
        status=None,
        min_score=args.min_score,
        limit=args.limit,
        order_by="date_desc",
    )
    counts: dict[str, int] = {}
    depts: dict[str, set] = {}
    for r in rows:
        company = (r["company"] or "").strip()
        if not company:
            continue
        counts[company] = counts.get(company, 0) + 1
        d = (r["department"] or "").strip()
        depts.setdefault(company, set()).add(d)
    items = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    with open(args.outfile, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["company", "offers", "departments"])
        for comp, c in items:
            w.writerow([comp, c, ",".join(sorted(x for x in depts.get(comp, set()) if x))])
    print(f"Watchlist written to {args.outfile} ({len(items)} companies)")


def cmd_charts(args):
    # Load rows and generate charts to outdir
    rows = query_offers(
        days=args.days,
        from_date=args.from_date,
        to_date=args.to_date,
        status=args.status,
        min_score=args.min_score,
        limit=args.limit,
        order_by="date_desc",
    )
    print(f"[charts] Building charts from {len(rows)} offers → {args.outdir}")
    build_charts(rows, args.outdir, require_mpl=bool(args.require_mpl))
    print("[charts] Done.")


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


def cmd_pipeline_daily(args):
    # 1) Fetch (optionally multi-page)
    fargs = Namespace(
        keywords=args.keywords,
        rome=None,
        auto_rome=False,
        dept=args.dept,
        commune=args.commune,
        distance_km=args.distance_km,
        radius_km=None,
        limit=args.limit,
        page=0,
        sort=1,
        published_since_days=args.published_since_days,
        min_creation=None,
        max_creation=None,
        origine_offre=None,
        fetch_all=bool(args.fetch_all),
        max_pages=args.max_pages,
    )
    print("[pipeline] Fetching offers…")
    cmd_fetch(fargs)

    # 2) Enrich
    if args.enrich:
        eargs = Namespace(
            ids=None,
            days=args.published_since_days,
            from_date=None,
            to_date=None,
            status=None,
            min_score=None,
            only_missing_description=True,
            min_desc_len=40,
            limit=args.enrich_limit,
            sleep_ms=args.enrich_sleep_ms,
        )
        print("[pipeline] Enriching offer details…")
        cmd_enrich(eargs)

    # 3) Export
    xargs = Namespace(
        format=args.export_format,
        days=args.published_since_days,
        from_date=None,
        to_date=None,
        status=None,
        min_score=args.min_score,
        limit=args.export_top,
        outfile=None,
        desc_chars=args.desc_chars,
    )
    print("[pipeline] Exporting results…")
    cmd_export(xargs)


def cmd_pipeline_weekly(args):
    # 1) Sweep multiple keywords (OR)
    swargs = Namespace(
        keywords_list=args.keywords_list,
        dept=args.dept,
        commune=args.commune,
        distance_km=args.distance_km,
        limit=args.limit,
        fetch_all=True,
        max_pages=args.max_pages,
        sort=1,
        published_since_days=args.published_since_days,
    )
    print("[pipeline] Sweep multiple keywords…")
    cmd_sweep(swargs)

    # 2) Enrich
    eargs = Namespace(
        ids=None,
        days=args.published_since_days,
        from_date=None,
        to_date=None,
        status=None,
        min_score=None,
        only_missing_description=True,
        min_desc_len=40,
        limit=1000,
        sleep_ms=200,
    )
    print("[pipeline] Enriching offer details…")
    cmd_enrich(eargs)

    # 3) Export
    xargs = Namespace(
        format="md",
        days=args.published_since_days,
        from_date=None,
        to_date=None,
        status=None,
        min_score=args.min_score,
        limit=args.export_top,
        outfile=None,
        desc_chars=args.desc_chars,
    )
    print("[pipeline] Exporting results…")
    cmd_export(xargs)

    # 4) Keyword stats
    kargs = Namespace(
        keywords_list=args.stats_keywords,
        mode="word",
        group_by="none",
        days=args.published_since_days,
        from_date=None,
        to_date=None,
        status=None,
        min_score=None,
        limit=100000,
        outfile=args.stats_outfile,
        sort_by="offers",
    )
    print("[pipeline] Computing keyword stats…")
    cmd_stats(kargs)

    # 5) NLP stats
    nlp = Namespace(
        days=args.published_since_days,
        from_date=None,
        to_date=None,
        status=None,
        min_score=None,
        limit=200000,
        top=args.nlp_top,
        min_df=args.nlp_min_df,
        max_df=args.nlp_max_df,
        stop_add=args.nlp_stop_add,
        outfile_tokens=args.nlp_outfile_tokens,
        outfile_bigrams=args.nlp_outfile_bigrams,
    )
    print("[pipeline] Computing NLP stats…")
    cmd_nlp_stats(nlp)

    # 6) Watchlist companies
    wargs = Namespace(
        days=args.published_since_days,
        from_date=None,
        to_date=None,
        min_score=None,
        limit=50000,
        outfile="data/out/watchlist_companies.csv",
    )
    print("[pipeline] Building company watchlist…")
    cmd_watchlist(wargs)

    # 7) Charts (PNG + CSV)
    cargs = Namespace(
        days=args.published_since_days,
        from_date=None,
        to_date=None,
        status=None,
        min_score=None,
        limit=200000,
        outdir="data/out/charts",
        require_mpl=False,
    )
    print("[pipeline] Generating charts…")
    cmd_charts(cargs)


def cmd_tui(_args):
    # Minimal interactive menu to help non-technical users select categories, days, and location
    from argparse import Namespace as _NS
    import os as _os

    cfg = load_config()
    print("\n=== FT Job Alerts — Assistant interactif ===\n")
    print("Mode:", "SIMULATE (local)" if cfg.api_simulate else "REAL API")
    if cfg.api_simulate:
        print("Astuce: vous pouvez tout tester sans réseau (FT_API_SIMULATE=1).\n")

    categories = [
        ("Robotique / ROS", ["ros2", "ros", "robotique", "robot"]),
        ("Vision industrielle", ["vision", "opencv", "halcon", "cognex", "keyence"]),
        ("Navigation / SLAM", ["navigation", "slam", "path planning"]),
        ("ROS stack (nav2, moveit…)", ["moveit", "nav2", "gazebo", "urdf", "tf2", "pcl", "rclcpp", "rclpy"]),
        ("Marques robots", ["fanuc", "abb", "kuka", "staubli", "yaskawa", "ur"]),
        ("Automatisme / PLC", ["automatisme", "plc", "grafcet", "siemens", "twincat"]),
        ("Langages", ["c++", "python"]),
        ("Capteurs", ["lidar", "camera", "imu"]),
    ]

    def ask(prompt: str, default: str | None = None) -> str:
        sfx = f" [{default}]" if default is not None else ""
        val = input(f"{prompt}{sfx}: ").strip()
        return val if val else (default or "")

    def ask_yes(prompt: str, default: bool = True) -> bool:
        d = "Y/n" if default else "y/N"
        v = input(f"{prompt} ({d}): ").strip().lower()
        if not v:
            return default
        return v in ("y", "yes", "o", "oui")

    # Categories selection
    print("Choisissez des catégories (ex: 1,3,5). Laissez vide pour utiliser les mots-clés par défaut.")
    for i, (label, _) in enumerate(categories, start=1):
        print(f"  {i}) {label}")
    sel = input("Votre sélection: ").strip()
    selected_keywords: list[str] = []
    if sel:
        try:
            ids = [int(x) for x in sel.replace(" ", "").split(",") if x]
            for i in ids:
                if 1 <= i <= len(categories):
                    selected_keywords.extend(categories[i - 1][1])
        except Exception:
            pass
    if not selected_keywords:
        selected_keywords = cfg.default_keywords
    extra_kw = ask("Mots-clés supplémentaires (séparés par des virgules)", "").strip()
    if extra_kw:
        selected_keywords.extend([k.strip() for k in extra_kw.split(",") if k.strip()])
    # Remove duplicates, keep order
    seen = set()
    keywords = [k for k in selected_keywords if not (k in seen or seen.add(k))]

    # Location
    print("\nFiltrage géographique (optionnel):")
    use_dept = ask_yes("  Filtrer par département(s) ?", True)
    dept = None
    commune = None
    distance_km = None
    if use_dept:
        dept = ask("  Code(s) département (ex: 68 ou 68,67)", cfg.default_dept)
    else:
        if ask_yes("  Rechercher autour d'une commune (INSEE) ?", False):
            commune = ask("    Code INSEE commune", "") or None
            if commune:
                try:
                    distance_km = int(ask("    Distance (km)", str(cfg.default_radius_km)))
                except Exception:
                    distance_km = cfg.default_radius_km

    # Time window and export options
    print("\nFenêtre temporelle de publication (Offres v2). Valeurs permises: 1,3,7,14,31")
    try:
        pdays = int(ask("  Nombre de jours", "7"))
    except Exception:
        pdays = 7
    try:
        topn = int(ask("  Nombre maximal d'offres à exporter", "100"))
    except Exception:
        topn = 100
    fmt = ask("  Format d'export (txt/md/csv/jsonl)", "md").lower() or "md"
    full_desc = fmt in ("md", "txt") and ask_yes("  Inclure la description complète ?", True)
    desc_chars = -1 if full_desc else (500 if fmt == "md" else 400)

    # Summary
    print("\nRésumé:")
    print("  Mots-clés:", ", ".join(keywords))
    if dept:
        print("  Département(s):", dept)
    elif commune:
        print(f"  Autour de {commune} à {distance_km} km")
    else:
        print("  France entière")
    print(f"  Jours: {pdays}  |  Export: {fmt} (top {topn})")
    if not ask_yes("Lancer maintenant ?", True):
        print("Annulé.")
        return

    # 1) Fetch (or simulate)
    fargs = _NS(
        keywords=",".join(keywords),
        rome=None,
        auto_rome=False,
        dept=dept,
        commune=commune,
        distance_km=distance_km,
        radius_km=None,
        limit=100,
        page=0,
        sort=1,
        published_since_days=pdays,
        min_creation=None,
        max_creation=None,
        origine_offre=None,
        fetch_all=True,
        max_pages=10,
    )
    print("\n[1/2] Récupération des offres…")
    cmd_fetch(fargs)

    # 2) Export selection
    print("[2/2] Export…")
    rows = query_offers(
        days=pdays,
        from_date=None,
        to_date=None,
        status=None,
        min_score=None,
        limit=topn,
        order_by="score_desc",
    )
    from .exporter import export_txt, export_md, export_csv, export_jsonl
    _os.makedirs("data/out", exist_ok=True)
    if fmt == "txt":
        out_path = export_txt(rows, None, desc_chars=desc_chars if isinstance(desc_chars, int) else 400)
    elif fmt == "md":
        out_path = export_md(rows, None, desc_chars=desc_chars if isinstance(desc_chars, int) else 500)
    elif fmt == "csv":
        out_path = export_csv(rows, None)
    else:
        out_path = export_jsonl(rows, None)
    print(f"Fini. Export: {out_path}")

    # 3) Petit guide IA (affiché + fichier)
    guide = (
        "\nConseil — Analyse avec un agent IA (gratuit):\n"
        "1) Ouvrez Google AI Studio (https://aistudio.google.com) → ‘Create a prompt’.\n"
        "2) Ouvrez le fichier exporté (" + out_path + ") et copiez le contenu.\n"
        "3) Collez-le dans le chat puis utilisez un prompt comme: \n\n"
        "Vous êtes mon assistant emploi. Profil: junior robotique (ROS2/C++/vision), mobilité limitée.\n"
        "À partir des offres collées, propose un top 10 trié par pertinence, avec:\n"
        "- résumé en 2 lignes,\n- principaux critères correspondants (ROS2/vision/robot brands/remote),\n"
        "- score 0–10 et raison,\n- questions à poser au recruteur.\n\n"
        "Ensuite, liste 5 entreprises à suivre (fréquence des offres).\n"
    )
    print(guide)
    try:
        with open("data/out/ai_prompt_example.txt", "w", encoding="utf-8") as f:
            f.write(guide)
        print("Guide IA enregistré: data/out/ai_prompt_example.txt")
    except Exception:
        pass


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

    s_stats = sub.add_parser("stats", help="Compute keyword stats over offers")
    s_stats.add_argument("--keywords-list", required=True,
                         help="Semicolon-separated keywords to count (e.g., 'ros2;ros;robotique;c++')")
    s_stats.add_argument("--mode", choices=["word", "regex"], default="word",
                         help="word: smart word-boundary; regex: raw regex patterns")
    s_stats.add_argument("--group-by", choices=["none", "dept"], default="none")
    s_stats.add_argument("--days", type=int, default=None)
    s_stats.add_argument("--from", dest="from_date", default=None)
    s_stats.add_argument("--to", dest="to_date", default=None)
    s_stats.add_argument("--status", default=None)
    s_stats.add_argument("--min-score", dest="min_score", type=float, default=None)
    s_stats.add_argument("--limit", type=int, default=100000)
    s_stats.add_argument("--outfile", default=None, help="Write CSV if provided; otherwise print")
    s_stats.add_argument("--sort-by", choices=["offers", "occurrences"], default="offers")
    s_stats.set_defaults(func=cmd_stats)

    s_nlp = sub.add_parser("nlp-stats", help="Semantic-ish stats: log-odds tokens/bigrams for CORE_ROBOTICS vs others")
    s_nlp.add_argument("--days", type=int, default=31)
    s_nlp.add_argument("--from", dest="from_date", default=None)
    s_nlp.add_argument("--to", dest="to_date", default=None)
    s_nlp.add_argument("--status", default=None)
    s_nlp.add_argument("--min-score", dest="min_score", type=float, default=None)
    s_nlp.add_argument("--limit", type=int, default=200000)
    s_nlp.add_argument("--top", type=int, default=40)
    s_nlp.add_argument("--min-df", dest="min_df", type=float, default=0.005, help="Min doc freq ratio to keep token/bigram")
    s_nlp.add_argument("--max-df", dest="max_df", type=float, default=0.4, help="Max doc freq ratio to keep token/bigram")
    s_nlp.add_argument("--stop-add", dest="stop_add", default=None, help="Extra stopwords (semicolon-separated)")
    s_nlp.add_argument("--outfile-tokens", dest="outfile_tokens", default=None)
    s_nlp.add_argument("--outfile-bigrams", dest="outfile_bigrams", default=None)
    s_nlp.set_defaults(func=cmd_nlp_stats)

    # Pipeline presets
    s_pipe = sub.add_parser("pipeline", help="Run a full pipeline (daily/weekly presets)")
    pipe_sub = s_pipe.add_subparsers(dest="pipeline", required=True)

    p_daily = pipe_sub.add_parser("daily", help="Daily preset: fetch → enrich → export")
    p_daily.add_argument("--keywords", default="robotique")
    p_daily.add_argument("--dept", default=None)
    p_daily.add_argument("--commune", default=None)
    p_daily.add_argument("--distance-km", type=int, default=None)
    p_daily.add_argument("--published-since-days", type=int, default=31)
    p_daily.add_argument("--limit", type=int, default=100)
    p_daily.add_argument("--all", dest="fetch_all", action="store_true", default=True,
                        help="Fetch multiple pages (default on)")
    p_daily.add_argument("--max-pages", type=int, default=10)
    p_daily.add_argument("--export-top", type=int, default=200)
    p_daily.add_argument("--export-format", choices=["md","txt"], default="md")
    p_daily.add_argument("--min-score", type=float, default=2.0)
    p_daily.add_argument("--desc-chars", type=int, default=-1)
    p_daily.add_argument("--enrich", action="store_true", default=True)
    p_daily.add_argument("--enrich-limit", type=int, default=500)
    p_daily.add_argument("--enrich-sleep-ms", type=int, default=200)
    p_daily.set_defaults(func=cmd_pipeline_daily)

    p_week = pipe_sub.add_parser("weekly", help="Weekly preset: sweep → enrich → export → stats → nlp-stats")
    p_week.add_argument("--keywords-list", default="robotique;robot;ros2;ros;automatisme;cobot;vision;ivvq;agv;amr")
    p_week.add_argument("--dept", default=None)
    p_week.add_argument("--commune", default=None)
    p_week.add_argument("--distance-km", type=int, default=None)
    p_week.add_argument("--published-since-days", type=int, default=31)
    p_week.add_argument("--limit", type=int, default=100)
    p_week.add_argument("--max-pages", type=int, default=20)
    p_week.add_argument("--export-top", type=int, default=300)
    p_week.add_argument("--min-score", type=float, default=2.0)
    p_week.add_argument("--desc-chars", type=int, default=-1)
    p_week.add_argument("--stats-keywords", default="ros2;ros;robotique;automatisme;vision;opencv;slam;moveit;gazebo;c++")
    p_week.add_argument("--stats-outfile", default="data/out/keyword-stats.csv")
    p_week.add_argument("--nlp-top", type=int, default=60)
    p_week.add_argument("--nlp-min-df", type=float, default=0.005)
    p_week.add_argument("--nlp-max-df", type=float, default=0.4)
    p_week.add_argument("--nlp-stop-add", default="poste;profil;mission;client;vous;h/f;cdi;interim;operateur;soudure;pieces;equipements")
    p_week.add_argument("--nlp-outfile-tokens", default="data/out/tokens.csv")
    p_week.add_argument("--nlp-outfile-bigrams", default="data/out/bigrams.csv")
    p_week.set_defaults(func=cmd_pipeline_weekly)

    # Watchlist companies (top by count in window)
    s_watch = sub.add_parser("watchlist", help="Top companies over a window (writes CSV)")
    s_watch.add_argument("--days", type=int, default=31)
    s_watch.add_argument("--from", dest="from_date", default=None)
    s_watch.add_argument("--to", dest="to_date", default=None)
    s_watch.add_argument("--min-score", dest="min_score", type=float, default=None)
    s_watch.add_argument("--limit", type=int, default=50000)
    s_watch.add_argument("--outfile", default="data/out/watchlist_companies.csv")
    s_watch.set_defaults(func=cmd_watchlist)

    s_charts = sub.add_parser("charts", help="Generate charts (PNGs and CSVs) from current selection")
    s_charts.add_argument("--days", type=int, default=31)
    s_charts.add_argument("--from", dest="from_date", default=None)
    s_charts.add_argument("--to", dest="to_date", default=None)
    s_charts.add_argument("--status", default=None)
    s_charts.add_argument("--min-score", dest="min_score", type=float, default=None)
    s_charts.add_argument("--limit", type=int, default=200000)
    s_charts.add_argument("--outdir", default="data/out/charts")
    s_charts.add_argument("--require-mpl", dest="require_mpl", action="store_true", help="Fail if matplotlib is not installed")
    s_charts.set_defaults(func=cmd_charts)

    # TUI (interactive helper)
    s_tui = sub.add_parser("tui", help="Assistant interactif (sélection catégories/jours/localisation → fetch+export)")
    s_tui.set_defaults(func=cmd_tui)

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
