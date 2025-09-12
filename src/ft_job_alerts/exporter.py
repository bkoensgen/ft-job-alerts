from __future__ import annotations

import csv
import datetime as dt
import os
from typing import Iterable


def _ensure_out_dir() -> str:
    os.makedirs("data/out", exist_ok=True)
    return "data/out"


def export_txt(rows, outfile: str | None = None) -> str:
    outdir = _ensure_out_dir()
    if not outfile:
        ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        outfile = os.path.join(outdir, f"offres-{ts}.txt")
    with open(outfile, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(
                f"- [{r['score']:.2f}] {r['title']} — {r['company']} — {r['location']} — {r['contract_type']} — {r['published_at']}\n  ID: {r['offer_id']}\n  URL: {r['url']}\n\n"
            )
    return outfile


def export_md(rows, outfile: str | None = None) -> str:
    outdir = _ensure_out_dir()
    if not outfile:
        ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        outfile = os.path.join(outdir, f"offres-{ts}.md")
    with open(outfile, "w", encoding="utf-8") as f:
        f.write("# Offres (sélection)\n\n")
        for r in rows:
            f.write(f"## {r['title']} ({r['score']:.2f})\n")
            f.write(f"- Entreprise: {r['company']}\n")
            f.write(f"- Lieu: {r['location']}\n")
            f.write(f"- Contrat: {r['contract_type']}\n")
            f.write(f"- Publiée: {r['published_at']}\n")
            f.write(f"- ID: `{r['offer_id']}`\n")
            f.write(f"- URL: {r['url']}\n\n")
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
        "contract_type",
        "published_at",
        "source",
        "url",
        "salary",
        "score",
        "status",
        "inserted_at",
    ]
    with open(outfile, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in fieldnames})
    return outfile

