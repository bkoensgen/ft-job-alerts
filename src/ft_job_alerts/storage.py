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
            rome_codes TEXT,
            keywords TEXT,
            contract_type TEXT,
            published_at TEXT,
            source TEXT,
            url TEXT,
            salary TEXT,
            score REAL DEFAULT 0,
            inserted_at TEXT,
            status TEXT DEFAULT 'new',
            followup1_due TEXT,
            followup2_due TEXT,
            last_notified_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_offers_status ON offers(status);
        CREATE INDEX IF NOT EXISTS idx_offers_published_at ON offers(published_at);
        """
    )
    con.commit()
    con.close()


def upsert_offers(offers: Iterable[dict[str, Any]]) -> int:
    con = connect()
    cur = con.cursor()
    now = dt.datetime.utcnow().isoformat()
    inserted = 0
    for o in offers:
        cur.execute(
            """
            INSERT INTO offers (
                offer_id, title, company, location, rome_codes, keywords,
                contract_type, published_at, source, url, salary, score, inserted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(offer_id) DO UPDATE SET
                score=excluded.score,
                title=excluded.title,
                company=excluded.company,
                location=excluded.location
            ;
            """,
            (
                o.get("offer_id"),
                o.get("title"),
                o.get("company"),
                o.get("location"),
                ",".join(o.get("rome_codes", [])),
                ",".join(o.get("keywords", [])),
                o.get("contract_type"),
                o.get("published_at"),
                o.get("source", "offres_v2"),
                o.get("url"),
                o.get("salary"),
                float(o.get("score", 0)),
                now,
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
