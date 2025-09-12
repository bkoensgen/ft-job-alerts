from __future__ import annotations

import csv
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Iterable, List, Dict, Tuple

from .tags import compute_labels


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _safe_matplotlib():
    try:
        import matplotlib
        matplotlib.use("Agg")  # headless
        import matplotlib.pyplot as plt
        return plt
    except Exception:
        return None


def _write_csv(path: str, headers: List[str], rows: Iterable[Iterable]):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)
        for r in rows:
            w.writerow(list(r))


def _ascii_bar(path: str, pairs: List[Tuple[str, int]], title: str = ""):
    width = 60
    total = max((v for _, v in pairs), default=1)
    lines = [title] if title else []
    for label, val in pairs:
        n = int((val / total) * width) if total else 0
        lines.append(f"{label:>15} | {'#'*n} {val}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _bar_chart(path_png: str, pairs: List[Tuple[str, int]], title: str):
    plt = _safe_matplotlib()
    if not plt:
        _ascii_bar(path_png.replace(".png", ".txt"), pairs, title)
        return
    labels = [p[0] for p in pairs]
    values = [p[1] for p in pairs]
    fig_h = max(3, min(12, 0.35 * len(labels)))
    plt.figure(figsize=(10, fig_h))
    plt.barh(labels, values)
    plt.gca().invert_yaxis()
    plt.title(title)
    plt.tight_layout()
    plt.savefig(path_png)
    plt.close()


def week_bucket(iso_ts: str | None) -> str:
    if not iso_ts:
        return "unknown"
    s = iso_ts.replace("Z", "").split(".")[0]
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        return "unknown"
    monday = dt - timedelta(days=dt.weekday())
    return monday.strftime("%Y-%m-%d")


def build_charts(rows, outdir: str):
    _ensure_dir(outdir)
    # Gather aggregates
    dept = Counter()
    company = Counter()
    contract = Counter()
    weeks = Counter()
    ros_stack = Counter()
    brands = Counter()
    vision = Counter()
    langs = Counter()
    plc = Counter()

    for r in rows:
        d = {k: r[k] for k in r.keys()} if not isinstance(r, dict) else r
        dept[d.get("department") or ""] += 1
        company[(d.get("company") or "").strip()] += 1
        contract[(d.get("contract_type") or "").strip()] += 1
        weeks[week_bucket(d.get("inserted_at") or d.get("published_at"))] += 1
        labels = compute_labels(d)
        for t in labels.get("ROS_STACK", []):
            ros_stack[t] += 1
        for t in labels.get("ROBOT_BRANDS", []):
            brands[t] += 1
        for t in labels.get("VISION_LIBS", []):
            vision[t] += 1
        for t in labels.get("LANG_TAGS", []):
            langs[t] += 1
        for t in labels.get("PLC_TAGS", []):
            plc[t] += 1

    def top_pairs(counter: Counter, n=20, drop_empty=True):
        items = [(k, v) for k, v in counter.items()]
        if drop_empty:
            items = [(k, v) for k, v in items if k]
        items.sort(key=lambda kv: kv[1], reverse=True)
        return items[:n]

    # Save CSVs and charts
    datasets = [
        ("departments", dept, 40),
        ("companies_top", company, 25),
        ("contracts", contract, 10),
        ("timeline_weeks", weeks, 60),
        ("ros_stack", ros_stack, 20),
        ("robot_brands", brands, 20),
        ("vision_libs", vision, 20),
        ("languages", langs, 20),
        ("plc_tags", plc, 20),
    ]
    for name, counter, n in datasets:
        pairs = top_pairs(counter, n=n)
        _write_csv(os.path.join(outdir, f"{name}.csv"), ["label", "count"], pairs)
        if name == "timeline_weeks":
            pairs.sort(key=lambda kv: kv[0])
        _bar_chart(os.path.join(outdir, f"{name}.png"), pairs, title=name.replace("_", " ").title())

