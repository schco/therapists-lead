"""SQLite database operations for therapist lead management."""

from __future__ import annotations

import csv
import io
import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).parent / "therapists.db"

DEFAULT_NEEDS = [
    ("Adult ADHD", "adhd,attention,executive function,add"),
    ("Couples Therapy", "couples,marriage,relationship,premarital,divorce"),
    ("Grief Counseling", "grief,loss,bereavement,mourning"),
    ("Anxiety", "anxiety,panic,ocd,phobia,worry"),
    ("Trauma / PTSD", "trauma,ptsd,emdr,dissociative"),
    ("Depression", "depression,mood,dysthymia"),
    ("Child / Adolescent", "child,adolescent,teen,pediatric,play therapy"),
    ("Family Therapy", "family,parenting,family systems"),
]


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables and seed default client needs."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS therapists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            credentials TEXT,
            specialties TEXT,
            phone TEXT,
            email TEXT,
            website TEXT,
            address TEXT,
            city TEXT,
            state TEXT,
            zip TEXT,
            source TEXT,
            practice_size TEXT,
            profile_url TEXT,
            date_scraped TEXT DEFAULT CURRENT_TIMESTAMP,
            outreach_status TEXT DEFAULT 'not_contacted',
            notes TEXT,
            pronouns TEXT,
            verified INTEGER DEFAULT 0,
            modalities TEXT,
            populations TEXT,
            fee TEXT,
            insurance TEXT,
            telehealth TEXT,
            recruitment_score INTEGER DEFAULT 0,
            match_count INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS client_needs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            need_name TEXT UNIQUE NOT NULL,
            keywords TEXT NOT NULL
        )
    """)

    for need_name, keywords in DEFAULT_NEEDS:
        cur.execute(
            "INSERT OR IGNORE INTO client_needs (need_name, keywords) VALUES (?, ?)",
            (need_name, keywords),
        )

    conn.commit()
    conn.close()


def get_needs() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM client_needs ORDER BY need_name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_therapists(therapists: list[dict]) -> int:
    """Insert or update therapist records. Returns number saved."""
    if not therapists:
        return 0

    conn = get_connection()
    cur = conn.cursor()
    saved = 0

    for t in therapists:
        existing = cur.execute(
            "SELECT id FROM therapists WHERE name = ? AND (profile_url = ? OR profile_url IS NULL)",
            (t.get("name"), t.get("profile_url")),
        ).fetchone()

        if existing:
            cur.execute("""
                UPDATE therapists SET
                    credentials = COALESCE(?, credentials),
                    specialties = COALESCE(?, specialties),
                    phone = COALESCE(?, phone),
                    website = COALESCE(?, website),
                    city = COALESCE(?, city),
                    state = COALESCE(?, state),
                    zip = COALESCE(?, zip),
                    verified = COALESCE(?, verified),
                    profile_url = COALESCE(?, profile_url)
                WHERE id = ?
            """, (
                t.get("credentials"), t.get("specialties"), t.get("phone"),
                t.get("website"), t.get("city"), t.get("state"), t.get("zip"),
                t.get("verified"), t.get("profile_url"), existing["id"],
            ))
        else:
            cur.execute("""
                INSERT INTO therapists
                    (name, credentials, specialties, phone, email, website, address,
                     city, state, zip, source, practice_size, profile_url,
                     pronouns, verified, modalities, populations, fee, insurance, telehealth)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                t.get("name"), t.get("credentials"), t.get("specialties"),
                t.get("phone"), t.get("email"), t.get("website"), t.get("address"),
                t.get("city"), t.get("state"), t.get("zip"), t.get("source"),
                t.get("practice_size"), t.get("profile_url"), t.get("pronouns"),
                t.get("verified", 0), t.get("modalities"), t.get("populations"),
                t.get("fee"), t.get("insurance"), t.get("telehealth"),
            ))
            saved += 1

    conn.commit()
    conn.close()
    return saved


def find_matches(need: str, location: str = "") -> list[dict]:
    """Find therapists matching a client need and optionally a location."""
    conn = get_connection()

    need_row = conn.execute(
        "SELECT keywords FROM client_needs WHERE need_name = ?", (need,)
    ).fetchone()

    keywords = []
    if need_row:
        keywords = [k.strip().lower() for k in need_row["keywords"].split(",") if k.strip()]

    if location:
        city_filter = location.split(",")[0].strip()
        rows = conn.execute(
            "SELECT * FROM therapists WHERE city LIKE ? OR state LIKE ?",
            (f"%{city_filter}%", f"%{location.split(',')[-1].strip()}%"),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM therapists").fetchall()

    conn.close()

    results = []
    for row in rows:
        t = dict(row)
        specialties_lower = (t.get("specialties") or "").lower()
        description_lower = (t.get("description") or "").lower() if "description" in t else ""
        combined = specialties_lower + " " + description_lower

        match_count = sum(1 for kw in keywords if kw in combined)
        if match_count > 0:
            t["match_count"] = match_count
            t["recruitment_score"] = calculate_recruitment_score(t)
            results.append(t)

    results.sort(key=lambda x: (x["match_count"], x["recruitment_score"]), reverse=True)
    return results


def calculate_recruitment_score(t: dict) -> int:
    """Score a therapist on likelihood of joining the hybrid model (1-10)."""
    score = 0
    if t.get("practice_size") == "solo":
        score += 3
    if not t.get("website"):
        score += 2
    if t.get("verified"):
        score += 1
    if t.get("phone"):
        score += 1
    if t.get("specialties"):
        score += 1
    if not t.get("insurance"):
        score += 1
    return min(10, score)


def update_outreach(therapist_id: int, status: str, notes: str | None) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE therapists SET outreach_status = ?, notes = ? WHERE id = ?",
        (status, notes, therapist_id),
    )
    conn.commit()
    conn.close()


def dashboard_counts() -> dict:
    conn = get_connection()
    rows = conn.execute(
        "SELECT outreach_status, COUNT(*) as count FROM therapists GROUP BY outreach_status"
    ).fetchall()
    conn.close()
    counts = {r["outreach_status"]: r["count"] for r in rows}
    counts["total"] = sum(counts.values())
    return counts


def all_therapists() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM therapists ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def therapists_csv(therapists: list[dict]) -> str:
    if not therapists:
        return ""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=therapists[0].keys())
    writer.writeheader()
    writer.writerows(therapists)
    return output.getvalue()
