"""SQLite persistence helpers for Therapist Lead Finder."""

from __future__ import annotations

import csv
import io
import sqlite3
from datetime import date
from pathlib import Path
from typing import Iterable

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "therapists.db"

THERAPY_NEEDS = [
    ("Adult ADHD", "adhd,attention,executive function,neurodiversity"),
    ("Anxiety", "anxiety,panic,worry,stress"),
    ("Couples Therapy", "couples,marriage,relationship,partner"),
    ("Depression", "depression,mood,low mood"),
    ("Grief Counseling", "grief,loss,bereavement"),
    ("Trauma and PTSD", "trauma,ptsd,emdr,post traumatic"),
    ("Child and Teen Therapy", "child,teen,adolescent,youth"),
    ("Family Therapy", "family,parenting,family systems"),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS therapists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    credentials TEXT DEFAULT '',
    specialties TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    email TEXT DEFAULT '',
    website TEXT DEFAULT '',
    address TEXT DEFAULT '',
    city TEXT DEFAULT '',
    state TEXT DEFAULT '',
    zip TEXT DEFAULT '',
    source TEXT DEFAULT '',
    practice_size TEXT DEFAULT 'unknown',
    profile_url TEXT DEFAULT '',
    date_scraped TEXT NOT NULL,
    outreach_status TEXT NOT NULL DEFAULT 'not_contacted',
    notes TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS client_needs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    need_name TEXT NOT NULL UNIQUE,
    keywords TEXT NOT NULL
);
"""


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with get_connection() as connection:
        connection.executescript(SCHEMA)
        connection.executemany(
            "INSERT OR IGNORE INTO client_needs (need_name, keywords) VALUES (?, ?)",
            THERAPY_NEEDS,
        )


def get_needs() -> list[sqlite3.Row]:
    with get_connection() as connection:
        return connection.execute("SELECT * FROM client_needs ORDER BY need_name").fetchall()


def save_therapists(therapists: Iterable[dict]) -> int:
    rows = list(therapists)
    if not rows:
        return 0
    with get_connection() as connection:
        for therapist in rows:
            existing = connection.execute(
                "SELECT id FROM therapists WHERE name = ? AND COALESCE(phone, '') = ? AND city = ?",
                (therapist.get("name", ""), therapist.get("phone", ""), therapist.get("city", "")),
            ).fetchone()
            values = (
                therapist.get("name", "Unknown therapist"), therapist.get("credentials", ""),
                therapist.get("specialties", ""), therapist.get("phone", ""), therapist.get("email", ""),
                therapist.get("website", ""), therapist.get("address", ""), therapist.get("city", ""),
                therapist.get("state", ""), therapist.get("zip", ""), therapist.get("source", ""),
                therapist.get("practice_size", "unknown"), therapist.get("profile_url", ""),
                therapist.get("date_scraped", date.today().isoformat()),
            )
            if existing:
                connection.execute(
                    """UPDATE therapists SET credentials=?, specialties=?, email=?, website=?, address=?,
                    state=?, zip=?, source=?, practice_size=?, profile_url=?, date_scraped=? WHERE id=?""",
                    (values[1], values[2], values[4], values[5], values[6], values[8], values[9], values[10],
                     values[11], values[12], values[13], existing["id"]),
                )
            else:
                connection.execute(
                    """INSERT INTO therapists (name, credentials, specialties, phone, email, website, address,
                    city, state, zip, source, practice_size, profile_url, date_scraped)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    values,
                )
        return len(rows)


def _score_therapist(row: sqlite3.Row, keywords: list[str], location: str) -> tuple[int, int]:
    haystack = f"{row['specialties']} {row['name']}".lower()
    matches = sum(1 for keyword in keywords if keyword.strip().lower() in haystack)
    score = matches
    if row["practice_size"] == "solo":
        score += 2
    if not row["website"]:
        score += 1
    if location and location.lower() in f"{row['city']} {row['address']}".lower():
        score += 1
    return matches, min(10, max(1, score))


def find_matches(need_name: str, location: str = "") -> list[dict]:
    with get_connection() as connection:
        need = connection.execute("SELECT keywords FROM client_needs WHERE need_name = ?", (need_name,)).fetchone()
        if not need:
            return []
        keywords = [item.strip() for item in need["keywords"].split(",") if item.strip()]
        rows = connection.execute("SELECT * FROM therapists ORDER BY name").fetchall()
    matches = []
    for row in rows:
        keyword_matches, recruitment_score = _score_therapist(row, keywords, location)
        if keyword_matches:
            item = dict(row)
            item["keyword_matches"] = keyword_matches
            item["recruitment_score"] = recruitment_score
            matches.append(item)
    return sorted(matches, key=lambda item: (-item["keyword_matches"], -item["recruitment_score"], item["name"]))


def update_outreach(therapist_id: int, status: str, notes: str | None = None) -> None:
    allowed = {"not_contacted", "contacted", "interested", "signed", "declined"}
    if status not in allowed:
        raise ValueError("Invalid outreach status")
    with get_connection() as connection:
        if notes is None:
            connection.execute("UPDATE therapists SET outreach_status=? WHERE id=?", (status, therapist_id))
        else:
            connection.execute("UPDATE therapists SET outreach_status=?, notes=? WHERE id=?", (status, notes, therapist_id))


def dashboard_counts() -> dict[str, int]:
    with get_connection() as connection:
        rows = connection.execute("SELECT outreach_status, COUNT(*) AS total FROM therapists GROUP BY outreach_status").fetchall()
    counts = {status: 0 for status in ("not_contacted", "contacted", "interested", "signed", "declined")}
    counts.update({row["outreach_status"]: row["total"] for row in rows})
    counts["total"] = sum(counts.values())
    return counts


def all_therapists() -> list[sqlite3.Row]:
    with get_connection() as connection:
        return connection.execute("SELECT * FROM therapists ORDER BY name").fetchall()


def therapists_csv(rows: Iterable[dict | sqlite3.Row]) -> str:
    fields = ["name", "credentials", "specialties", "phone", "email", "website", "address", "city", "state", "zip", "source", "practice_size", "profile_url", "date_scraped", "outreach_status", "notes"]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(dict(row) for row in rows)
    return output.getvalue()
