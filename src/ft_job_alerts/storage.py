from __future__ import annotations

import datetime as dt
import os
import sqlite3
from typing import Any, Iterable


DB_PATH = os.path.join("data", "ft_jobs.db")


def ensure_dirs() -> None:
    os.makedirs("data", exist_ok=True)
    os.makedirs("data/out", exist_ok=True)
    os.makedirs("data/samples", exist_ok=True)


def connect() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        # Reasonable defaults for local apps
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    except Exception:
        pass
    return conn


def init_db() -> None:
    con = connect()
    cur = con.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS offers (
            offer_id TEXT PRIMARY KEY,
            title TEXT,
            company TEXT,
            location TEXT,
            city TEXT,
            department TEXT,
            postal_code TEXT,
            latitude REAL,
            longitude REAL,
            description TEXT,
            rome_codes TEXT,
            keywords TEXT,
            contract_type TEXT,
            published_at TEXT,
            source TEXT,
            url TEXT,
            apply_url TEXT,
            salary TEXT,
            salary_min_monthly_eur REAL,
            origin_code TEXT,
            offres_manque_candidats INTEGER,
            score REAL DEFAULT 0,
            inserted_at TEXT,
            last_seen_at TEXT,
            status TEXT DEFAULT 'new',
            followup1_due TEXT,
            followup2_due TEXT,
            last_notified_at TEXT,
            raw_json TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_offers_status ON offers(status);
        CREATE INDEX IF NOT EXISTS idx_offers_published_at ON offers(published_at);
        CREATE INDEX IF NOT EXISTS idx_offers_inserted_at ON offers(inserted_at);
        CREATE INDEX IF NOT EXISTS idx_offers_score ON offers(score);
        CREATE INDEX IF NOT EXISTS idx_offers_followups ON offers(status, followup1_due, followup2_due);
        CREATE INDEX IF NOT EXISTS idx_offers_department ON offers(department);
        CREATE INDEX IF NOT EXISTS idx_offers_salary_min ON offers(salary_min_monthly_eur);
        """
    )
    # Migrations for older DBs: add columns if missing
    ensure_offer_columns(cur)
    con.commit()
    con.close()


def ensure_offer_columns(cur: sqlite3.Cursor) -> None:
    cur.execute("PRAGMA table_info(offers)")
    cols = {row[1] for row in cur.fetchall()}
    def add(col: str, sql_type: str):
        cur.execute(f"ALTER TABLE offers ADD COLUMN {col} {sql_type}")
    wanted = {
        "city": "TEXT",
        "department": "TEXT",
        "postal_code": "TEXT",
        "latitude": "REAL",
        "longitude": "REAL",
        "description": "TEXT",
        "apply_url": "TEXT",
        "salary_min_monthly_eur": "REAL",
        "origin_code": "TEXT",
        "offres_manque_candidats": "INTEGER",
        "raw_json": "TEXT",
        "last_seen_at": "TEXT",
    }
    for name, typ in wanted.items():
        if name not in cols:
            add(name, typ)


def upsert_offers(offers: Iterable[dict[str, Any]]) -> int:
    con = connect()
    cur = con.cursor()
    now = dt.datetime.utcnow().isoformat()
    inserted = 0
    # lazy import to avoid cycles
    try:
        from .salary import parse_salary_min_monthly
    except Exception:
        parse_salary_min_monthly = lambda s: None  # type: ignore
    for o in offers:
        s_txt = o.get("salary") or o.get("description") or ""
        s_min = None
        try:
            s_min = parse_salary_min_monthly(str(s_txt))
        except Exception:
            s_min = None
        cur.execute(
            """
            INSERT INTO offers (
                offer_id, title, company, location,
                city, department, postal_code, latitude, longitude,
                description, rome_codes, keywords,
                contract_type, published_at, source, url, apply_url, salary, salary_min_monthly_eur,
                origin_code, offres_manque_candidats,
                score, inserted_at, last_seen_at, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(offer_id) DO UPDATE SET
                score=excluded.score,
                title=excluded.title,
                company=excluded.company,
                location=excluded.location,
                city=excluded.city,
                department=excluded.department,
                postal_code=excluded.postal_code,
                latitude=excluded.latitude,
                longitude=excluded.longitude,
                description=excluded.description,
                rome_codes=excluded.rome_codes,
                keywords=excluded.keywords,
                contract_type=excluded.contract_type,
                published_at=excluded.published_at,
                url=excluded.url,
                apply_url=excluded.apply_url,
                salary=excluded.salary,
                salary_min_monthly_eur=COALESCE(excluded.salary_min_monthly_eur, salary_min_monthly_eur),
                origin_code=excluded.origin_code,
                offres_manque_candidats=COALESCE(excluded.offres_manque_candidats, offres_manque_candidats),
                last_seen_at=excluded.last_seen_at
            ;
            """,
            (
                o.get("offer_id"),
                o.get("title"),
                o.get("company"),
                o.get("location"),
                o.get("city"),
                o.get("department"),
                o.get("postal_code"),
                o.get("latitude"),
                o.get("longitude"),
                o.get("description"),
                ",".join(o.get("rome_codes", [])),
                ",".join(o.get("keywords", [])),
                o.get("contract_type"),
                o.get("published_at"),
                o.get("source", "offres_v2"),
                o.get("url"),
                o.get("apply_url"),
                o.get("salary"),
                s_min,
                o.get("origin_code"),
                o.get("offres_manque_candidats"),
                float(o.get("score", 0)),
                now,
                now,
                o.get("raw_json"),
            ),
        )
        if cur.rowcount == 1:
            inserted += 1
    con.commit()
    con.close()
    return inserted


def set_status(offer_id: str, status: str) -> None:
    con = connect()
    cur = con.cursor()
    fu1 = fu2 = None
    if status == "applied":
        d1 = dt.date.today() + dt.timedelta(days=5)
        d2 = dt.date.today() + dt.timedelta(days=12)
        fu1, fu2 = d1.isoformat(), d2.isoformat()
    cur.execute(
        "UPDATE offers SET status=?, followup1_due=?, followup2_due=? WHERE offer_id=?",
        (status, fu1, fu2, offer_id),
    )
    con.commit()
    con.close()


def due_followups(today: dt.date | None = None) -> list[sqlite3.Row]:
    con = connect()
    cur = con.cursor()
    t = (today or dt.date.today()).isoformat()
    cur.execute(
        """
        SELECT * FROM offers
        WHERE status='applied' AND (
            followup1_due = ? OR followup2_due = ?
        )
        ORDER BY score DESC
        """,
        (t, t),
    )
    rows = cur.fetchall()
    con.close()
    return rows


def recent_new_offers(limit: int = 50) -> list[sqlite3.Row]:
    con = connect()
    cur = con.cursor()
    cur.execute(
        """
        SELECT * FROM offers
        WHERE status='new' AND (last_notified_at IS NULL OR last_notified_at = '')
        ORDER BY inserted_at DESC, score DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cur.fetchall()
    con.close()
    return rows


def mark_notified(offer_ids: list[str]) -> None:
    if not offer_ids:
        return
    con = connect()
    cur = con.cursor()
    now = dt.datetime.utcnow().isoformat()
    cur.executemany(
        "UPDATE offers SET last_notified_at=? WHERE offer_id=?",
        [(now, oid) for oid in offer_ids],
    )
    con.commit()
    con.close()


def query_offers(
    *,
    days: int | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    status: str | None = None,
    min_score: float | None = None,
    min_salary_monthly: float | None = None,
    limit: int = 100,
    order_by: str = "score_desc",
) -> list[sqlite3.Row]:
    con = connect()
    cur = con.cursor()
    where = []
    params: list[Any] = []

    # We filter on inserted_at (UTC ISO string) for recency; can be swapped for published_at if desired.
    if days is not None:
        start = (dt.datetime.utcnow() - dt.timedelta(days=days)).isoformat()
        where.append("inserted_at >= ?")
        params.append(start)
    if from_date:
        where.append("inserted_at >= ?")
        params.append(from_date)
    if to_date:
        # add one day to include the whole day when only a date is provided
        if len(to_date) == 10:
            to_dt = dt.datetime.fromisoformat(to_date) + dt.timedelta(days=1)
            where.append("inserted_at < ?")
            params.append(to_dt.isoformat())
        else:
            where.append("inserted_at <= ?")
            params.append(to_date)
    if status:
        where.append("status = ?")
        params.append(status)
    if min_score is not None:
        where.append("score >= ?")
        params.append(float(min_score))
    if min_salary_monthly is not None:
        where.append("(salary_min_monthly_eur IS NOT NULL AND salary_min_monthly_eur >= ?)")
        params.append(float(min_salary_monthly))

    order_sql = {
        "score_desc": "score DESC, inserted_at DESC",
        "date_desc": "inserted_at DESC, score DESC",
    }.get(order_by, "score DESC, inserted_at DESC")

    sql = "SELECT * FROM offers"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += f" ORDER BY {order_sql} LIMIT ?"
    params.append(int(limit))
    cur.execute(sql, params)
    rows = cur.fetchall()
    con.close()
    return rows


def update_offer_details(offer_id: str, fields: dict[str, Any]) -> None:
    if not fields:
        return
    con = connect()
    cur = con.cursor()
    # compute derived salary if needed
    if "salary" in fields:
        try:
            from .salary import parse_salary_min_monthly
            fields["salary_min_monthly_eur"] = parse_salary_min_monthly(str(fields.get("salary") or ""))
        except Exception:
            pass
    cols = []
    params: list[Any] = []
    for k, v in fields.items():
        cols.append(f"{k}=?")
        params.append(v)
    params.append(offer_id)
    sql = f"UPDATE offers SET {', '.join(cols)} WHERE offer_id=?"
    cur.execute(sql, params)
    con.commit()
    con.close()
