from __future__ import annotations

import csv
import datetime as dt
import os
from typing import Iterable


def _ensure_out_dir() -> str:
    os.makedirs("data/out", exist_ok=True)
    return "data/out"


def export_txt(rows, outfile: str | None = None, desc_chars: int | None = 400) -> str:
    outdir = _ensure_out_dir()
    if not outfile:
        ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        outfile = os.path.join(outdir, f"offres-{ts}.txt")
    with open(outfile, "w", encoding="utf-8") as f:
        for r in rows:
            desc = r["description"] or ""
            if desc_chars is not None and desc_chars > 0 and len(desc) > desc_chars:
                desc = desc[: desc_chars].rstrip() + "…"
            loc_detail = f"{r['city']} ({r['department']})" if r["city"] else r["location"]
            line1 = (
                f"- [{r['score']:.2f}] {r['title']} — {r['company']} — {loc_detail} — {r['contract_type']} — {r['published_at']}\n"
                f"  ID: {r['offer_id']}\n  URL: {r['url']}\n"
            )
            f.write(line1)
            if desc:
                f.write(f"  Desc: {desc}\n")
            f.write("\n")
    return outfile


def export_md(rows, outfile: str | None = None, desc_chars: int | None = 500) -> str:
    outdir = _ensure_out_dir()
    if not outfile:
        ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        outfile = os.path.join(outdir, f"offres-{ts}.md")
    with open(outfile, "w", encoding="utf-8") as f:
        f.write("# Offres (sélection)\n\n")
        for r in rows:
            loc_detail = f"{r['city']} ({r['department']})" if r["city"] else r["location"]
            f.write(f"## {r['title']} ({r['score']:.2f})\n")
            f.write(f"- Entreprise: {r['company']}\n")
            f.write(f"- Lieu: {loc_detail}\n")
            f.write(f"- Contrat: {r['contract_type']}\n")
            f.write(f"- Publiée: {r['published_at']}\n")
            f.write(f"- ID: `{r['offer_id']}`\n")
            f.write(f"- URL: {r['url']}\n")
            desc = r["description"] or ""
            if desc:
                if desc_chars is not None and desc_chars > 0 and len(desc) > desc_chars:
                    desc = desc[: desc_chars].rstrip() + "…"
                f.write("\n" + desc + "\n")
            f.write("\n")
    return outfile


def export_csv(rows, outfile: str | None = None) -> str:
    outdir = _ensure_out_dir()
    if not outfile:
        ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        outfile = os.path.join(outdir, f"offres-{ts}.csv")
    fieldnames = [
        "offer_id",
        "title",
        "company",
        "location",
        "city",
        "department",
        "postal_code",
        "latitude",
        "longitude",
        "contract_type",
        "published_at",
        "source",
        "url",
        "apply_url",
        "salary",
        "score",
        "status",
        "inserted_at",
        "rome_codes",
        "keywords",
        "description",
    ]
    with open(outfile, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in fieldnames})
    return outfile


def export_jsonl(rows, outfile: str | None = None) -> str:
    outdir = _ensure_out_dir()
    if not outfile:
        ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        outfile = os.path.join(outdir, f"offres-{ts}.jsonl")
    import json
    with open(outfile, "w", encoding="utf-8") as f:
        for r in rows:
            obj = {k: r[k] for k in r.keys()}
            # Keep raw_json as is; consumers can parse if needed
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    return outfile
