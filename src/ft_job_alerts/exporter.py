from __future__ import annotations

import csv
import datetime as dt
import os
from typing import Iterable

from .tags import compute_labels


def _ensure_out_dir() -> str:
    os.makedirs("data/out", exist_ok=True)
    return "data/out"


def _row_to_dict(row) -> dict:
    if isinstance(row, dict):
        return row
    return {k: row[k] for k in row.keys()}


def export_txt(rows, outfile: str | None = None, desc_chars: int | None = 400) -> str:
    outdir = _ensure_out_dir()
    if not outfile:
        ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        outfile = os.path.join(outdir, f"offres-{ts}.txt")
    with open(outfile, "w", encoding="utf-8") as f:
        for r0 in rows:
            r = _row_to_dict(r0)
            labels = {k: r.get(k) for k in ("CORE_ROBOTICS","ADJACENT_CATEGORIES","REMOTE","SENIORITY","PLC_TAGS","LANG_TAGS","SENSOR_TAGS","AGENCY")}
            if labels.get("CORE_ROBOTICS") is None:
                labels = compute_labels(r)
            desc = r.get("description") or ""
            if desc_chars == 0:
                desc = ""
            elif desc_chars is not None and desc_chars > 0 and len(desc) > desc_chars:
                desc = desc[: desc_chars].rstrip() + "…"
            loc_detail = f"{r.get('city','')} ({r.get('department','')})" if r.get("city") else r.get("location", "")
            link = r.get("url") or r.get("apply_url") or (f"https://candidat.francetravail.fr/offres/recherche/detail/{r.get('offer_id')}" if r.get("offer_id") else "")

            f.write(f"- ID: {r.get('offer_id','')} | TITLE: {r.get('title','')}\n")
            f.write(
                f"  COMPANY: {r.get('company','')} | CITY: {r.get('city','')} | DEPT: {r.get('department','')} | CONTRACT: {r.get('contract_type','')} | PUBLISHED: {r.get('published_at','')}\n"
            )
            f.write(f"  URL: {link} | APPLY_URL: {r.get('apply_url','')}\n")
            shortage = r.get("offres_manque_candidats")
            f.write(
                "  LABELS: "
                f"CORE_ROBOTICS={ 'yes' if labels.get('CORE_ROBOTICS') else 'no' }; "
                f"SENIORITY={labels.get('SENIORITY')}; "
                f"REMOTE={ 'yes' if labels.get('REMOTE') else 'no' }; "
                f"AGENCY={ 'yes' if labels.get('AGENCY') else 'no' }; "
                f"SHORTAGE={ 'yes' if shortage else 'no' }\n"
            )
            def _fmt_list(name, arr):
                arr = arr or []
                if not arr:
                    return f"  {name}: []\n"
                return f"  {name}: [" + ", ".join(arr) + "]\n"
            f.write(_fmt_list("TAGS_TECH", labels.get("PLC_TAGS")))
            f.write(_fmt_list("TAGS_ADJACENT", labels.get("ADJACENT_CATEGORIES")))
            f.write(_fmt_list("LANGS", labels.get("LANG_TAGS")))
            f.write(_fmt_list("SENSORS", labels.get("SENSOR_TAGS")))
            f.write(f"  SALARY_TEXT: {r.get('salary','')}\n")
            if desc:
                f.write("  DESCRIPTION:\n")
                for line in desc.splitlines():
                    f.write("    " + line + "\n")
            f.write("\n")
    return outfile


def export_md(rows, outfile: str | None = None, desc_chars: int | None = 500) -> str:
    outdir = _ensure_out_dir()
    if not outfile:
        ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        outfile = os.path.join(outdir, f"offres-{ts}.md")
    with open(outfile, "w", encoding="utf-8") as f:
        f.write("# Offres (sélection)\n\n")
        for r0 in rows:
            r = _row_to_dict(r0)
            labels = {k: r.get(k) for k in ("CORE_ROBOTICS","ADJACENT_CATEGORIES","REMOTE","SENIORITY","PLC_TAGS","LANG_TAGS","SENSOR_TAGS","AGENCY")}
            if labels.get("CORE_ROBOTICS") is None:
                labels = compute_labels(r)
            loc_detail = f"{r.get('city','')} ({r.get('department','')})" if r.get("city") else r.get("location", "")
            link = r.get("url") or r.get("apply_url") or (f"https://candidat.francetravail.fr/offres/recherche/detail/{r.get('offer_id')}" if r.get("offer_id") else "")
            f.write(f"## {r.get('title','')} ({r.get('score',0):.2f})\n")
            f.write(f"- ID: `{r.get('offer_id','')}`\n")
            f.write(f"- Entreprise: {r.get('company','')}\n")
            f.write(f"- Lieu: {loc_detail}\n")
            f.write(f"- Contrat: {r.get('contract_type','')}\n")
            f.write(f"- Publiée: {r.get('published_at','')}\n")
            f.write(f"- URL: {link}\n")
            f.write(f"- Apply: {r.get('apply_url','')}\n")
            shortage = r.get("offres_manque_candidats")
            f.write(f"- Labels: CORE={ 'yes' if labels.get('CORE_ROBOTICS') else 'no' }; SENIORITY={labels.get('SENIORITY')}; REMOTE={ 'yes' if labels.get('REMOTE') else 'no' }; AGENCY={ 'yes' if labels.get('AGENCY') else 'no' }; SHORTAGE={ 'yes' if shortage else 'no' }\n")
            def _md_list(name, arr):
                arr = arr or []
                if not arr:
                    f.write(f"- {name}: []\n")
                else:
                    f.write(f"- {name}: [" + ", ".join(arr) + "]\n")
            _md_list("Tags tech", labels.get("PLC_TAGS"))
            _md_list("Adjacents", labels.get("ADJACENT_CATEGORIES"))
            _md_list("Langages", labels.get("LANG_TAGS"))
            _md_list("Capteurs", labels.get("SENSOR_TAGS"))
            f.write(f"- Salaire: {r.get('salary','')}\n")
            desc = r.get("description") or ""
            if desc_chars == 0:
                desc = ""
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
