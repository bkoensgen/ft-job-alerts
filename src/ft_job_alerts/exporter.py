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


def export_txt(rows, outfile: str | None = None, desc_chars: int | None = 400, labels_mode: str = "auto") -> str:
    outdir = _ensure_out_dir()
    if not outfile:
        ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        outfile = os.path.join(outdir, f"offres-{ts}.txt")
    with open(outfile, "w", encoding="utf-8") as f:
        for r0 in rows:
            r = _row_to_dict(r0)
            labels = {k: r.get(k) for k in ("CORE_ROBOTICS","ADJACENT_CATEGORIES","REMOTE","SENIORITY","PLC_TAGS","LANG_TAGS","SENSOR_TAGS","AGENCY","ROS_STACK","ROBOT_BRANDS","VISION_LIBS")}
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
            # Generic header labels
            f.write(
                "  LABELS: "
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
            # Generic mode prints only high-signal items; robotics prints full set
            lm = (labels_mode or "auto").lower()
            is_robot = lm == "robotics" or (lm == "auto" and (labels.get("CORE_ROBOTICS") or labels.get("ROS_STACK")))
            # Always helpful
            f.write(_fmt_list("LANGS", labels.get("LANG_TAGS")))
            if is_robot:
                f.write(_fmt_list("TAGS_TECH", labels.get("PLC_TAGS")))
                f.write(_fmt_list("TAGS_ADJACENT", labels.get("ADJACENT_CATEGORIES")))
                f.write(_fmt_list("SENSORS", labels.get("SENSOR_TAGS")))
                f.write(_fmt_list("ROS_STACK", labels.get("ROS_STACK")))
                f.write(_fmt_list("ROBOT_BRANDS", labels.get("ROBOT_BRANDS")))
                f.write(_fmt_list("VISION_LIBS", labels.get("VISION_LIBS")))
            f.write(f"  SALARY_TEXT: {r.get('salary','')}\n")
            if desc:
                f.write("  DESCRIPTION:\n")
                for line in desc.splitlines():
                    f.write("    " + line + "\n")
            f.write("\n")
    return outfile


def export_md(rows, outfile: str | None = None, desc_chars: int | None = 500, labels_mode: str = "auto") -> str:
    outdir = _ensure_out_dir()
    if not outfile:
        ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        outfile = os.path.join(outdir, f"offres-{ts}.md")
    with open(outfile, "w", encoding="utf-8") as f:
        f.write("# Offres (sélection)\n\n")
        for r0 in rows:
            r = _row_to_dict(r0)
            labels = {k: r.get(k) for k in ("CORE_ROBOTICS","ADJACENT_CATEGORIES","REMOTE","SENIORITY","PLC_TAGS","LANG_TAGS","SENSOR_TAGS","AGENCY","ROS_STACK","ROBOT_BRANDS","VISION_LIBS")}
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
            f.write(f"- Labels: SENIORITY={labels.get('SENIORITY')}; REMOTE={ 'yes' if labels.get('REMOTE') else 'no' }; AGENCY={ 'yes' if labels.get('AGENCY') else 'no' }; SHORTAGE={ 'yes' if shortage else 'no' }\n")
            def _md_list(name, arr):
                arr = arr or []
                if not arr:
                    f.write(f"- {name}: []\n")
                else:
                    f.write(f"- {name}: [" + ", ".join(arr) + "]\n")
            lm = (labels_mode or "auto").lower()
            is_robot = lm == "robotics" or (lm == "auto" and (labels.get("CORE_ROBOTICS") or labels.get("ROS_STACK")))
            _md_list("Langages", labels.get("LANG_TAGS"))
            if is_robot:
                _md_list("Tags tech", labels.get("PLC_TAGS"))
                _md_list("Adjacents", labels.get("ADJACENT_CATEGORIES"))
                _md_list("Capteurs", labels.get("SENSOR_TAGS"))
                _md_list("ROS stack", labels.get("ROS_STACK"))
                _md_list("Marques robots", labels.get("ROBOT_BRANDS"))
                _md_list("Vision libs", labels.get("VISION_LIBS"))
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


def export_html(rows, outfile: str | None = None, desc_chars: int | None = 600, labels_mode: str = "auto") -> str:
    outdir = _ensure_out_dir()
    if not outfile:
        ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        outfile = os.path.join(outdir, f"offres-{ts}.html")
    def esc(s: str) -> str:
        import html
        return html.escape(s, quote=True)
    with open(outfile, "w", encoding="utf-8") as f:
        f.write("<!doctype html><html lang=\"fr\"><meta charset=\"utf-8\"><title>Offres (sélection)</title>")
        f.write("<style>body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,sans-serif;margin:24px;} .card{border:1px solid #ddd;border-radius:8px;padding:12px 14px;margin:12px 0;} .meta{color:#555;font-size:0.9em;margin:6px 0;} .tags{font-size:0.85em;color:#333} .tag{display:inline-block;background:#f2f2f2;border-radius:12px;padding:2px 8px;margin:2px} h2{margin:0 0 6px;} .score{color:#0a6} .link a{color:#06c;text-decoration:none} .link a:hover{text-decoration:underline}</style>")
        f.write("<h1>Offres (sélection)</h1>")
        for r0 in rows:
            r = _row_to_dict(r0)
            labels = {k: r.get(k) for k in ("CORE_ROBOTICS","ADJACENT_CATEGORIES","REMOTE","SENIORITY","PLC_TAGS","LANG_TAGS","SENSOR_TAGS","AGENCY","ROS_STACK","ROBOT_BRANDS","VISION_LIBS")}
            if labels.get("CORE_ROBOTICS") is None:
                labels = compute_labels(r)
            loc_detail = f"{r.get('city','')} ({r.get('department','')})" if r.get("city") else r.get("location", "")
            link = r.get("url") or r.get("apply_url") or (f"https://candidat.francetravail.fr/offres/recherche/detail/{r.get('offer_id')}" if r.get("offer_id") else "")
            f.write("<div class=\"card\">")
            f.write(f"<h2>{esc(str(r.get('title','')))} <span class=\"score\">({float(r.get('score',0)):.2f})</span></h2>")
            f.write("<div class=\"meta\">")
            f.write(f"ID: <code>{esc(str(r.get('offer_id','')))}</code> • ")
            f.write(f"Entreprise: {esc(str(r.get('company','')))} • ")
            f.write(f"Lieu: {esc(loc_detail)} • ")
            f.write(f"Contrat: {esc(str(r.get('contract_type','')))} • ")
            f.write(f"Publiée: {esc(str(r.get('published_at','')))}")
            f.write("</div>")
            if link:
                f.write(f"<div class=\"link\"><a href=\"{esc(link)}\" target=\"_blank\">Voir l’offre / Postuler</a></div>")
            shortage = r.get("offres_manque_candidats")
            chips = []
            if labels.get("REMOTE"): chips.append("Remote/Hybrid")
            if labels.get("AGENCY"): chips.append("Agence/ESN")
            ssen = labels.get("SENIORITY")
            if ssen and ssen != "unspecified": chips.append(ssen)
            if shortage: chips.append("Tension")
            f.write("<div class=\"tags\">")
            for c in chips:
                f.write(f"<span class=\"tag\">{esc(str(c))}</span>")
            # Generic first
            for name in ("LANG_TAGS",):
                arr = labels.get(name) or []
                for t in arr:
                    f.write(f"<span class=\"tag\">{esc(str(t))}</span>")
            lm = (labels_mode or "auto").lower()
            is_robot = lm == "robotics" or (lm == "auto" and (labels.get("CORE_ROBOTICS") or labels.get("ROS_STACK")))
            if is_robot:
                for name in ("PLC_TAGS","SENSOR_TAGS","ROS_STACK","ROBOT_BRANDS","VISION_LIBS","ADJACENT_CATEGORIES"):
                    arr = labels.get(name) or []
                    for t in arr:
                        f.write(f"<span class=\"tag\">{esc(str(t))}</span>")
            f.write("</div>")
            desc = r.get("description") or ""
            if desc_chars == 0:
                desc = ""
            elif desc_chars is not None and desc_chars > 0 and len(desc) > desc_chars:
                desc = desc[: desc_chars].rstrip() + "…"
            if desc:
                f.write(f"<div>{esc(desc).replace('\n','<br>')}</div>")
            f.write("</div>")
        f.write("</html>")
    return outfile
