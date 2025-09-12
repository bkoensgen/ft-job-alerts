from __future__ import annotations

import datetime as dt
import os
import smtplib
from email.message import EmailMessage
from typing import Iterable

from .config import Config


def format_offers(rows) -> str:
    lines = []
    for r in rows:
        link = r["url"] or r["apply_url"] or (f"https://candidat.francetravail.fr/offres/recherche/detail/{r['offer_id']}" if r["offer_id"] else "")
        line = f"[{r['score']:.2f}] {r['title']} — {r['company']} — {r['location']} — {link}"
        lines.append(line)
    return "\n".join(lines)


def notify(cfg: Config, subject: str, body: str) -> None:
    if cfg.email_to and cfg.smtp_host:
        _send_email(cfg, subject, body)
    else:
        _write_file_and_print(subject, body)


def _send_email(cfg: Config, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg.smtp_user or "ft-job-alerts"
    msg["To"] = cfg.email_to
    msg.set_content(body)

    with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=10) as server:
        if cfg.smtp_starttls:
            server.starttls()
        if cfg.smtp_user and cfg.smtp_password:
            server.login(cfg.smtp_user, cfg.smtp_password)
        server.send_message(msg)


def _write_file_and_print(subject: str, body: str) -> None:
    os.makedirs("data/out", exist_ok=True)
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join("data/out", f"notification-{ts}.txt")
    content = subject + "\n\n" + body
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("\n=== Notification ===")
    print(content)
    print(f"Saved to {path}")
