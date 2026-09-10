"""Flask web application for finding and managing therapist leads."""

from __future__ import annotations

import io
import os
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, send_file, url_for

import database
import scraper

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-this-local-secret"
app.config["TEMPLATES_AUTO_RELOAD"] = True


def parse_location(raw_location: str) -> tuple[str, str]:
    parts = [part.strip() for part in raw_location.split(",") if part.strip()]
    return (parts[0] if parts else "Old Bridge", parts[1] if len(parts) > 1 else "NJ")


@app.route("/", methods=["GET", "POST"])
def index():
    database.init_db()
    needs = database.get_needs()
    if request.method == "POST":
        need = request.form.get("need", "Adult ADHD")
        location = request.form.get("location", "Old Bridge, NJ")
        radius = max(1, min(100, int(request.form.get("radius", 20))))
        city, state = parse_location(location)
        leads, errors = scraper.scrape_all(city, state, radius)
        database.save_therapists(leads)
        for error in errors:
            flash(error, "warning")
        return redirect(url_for("results", need=need, location=f"{city}, {state}", radius=radius))
    return render_template("index.html", needs=needs, default_location="Old Bridge, NJ")


@app.route("/results")
def results():
    database.init_db()
    need = request.args.get("need", "Adult ADHD")
    location = request.args.get("location", "Old Bridge, NJ")
    matches = database.find_matches(need, location)
    return render_template("results.html", therapists=matches, need=need, location=location, radius=request.args.get("radius", "20"))


@app.post("/therapists/<int:therapist_id>/status")
def update_status(therapist_id: int):
    database.update_outreach(therapist_id, request.form.get("status", "not_contacted"), request.form.get("notes"))
    flash("Lead updated.", "success")
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/dashboard")
def dashboard():
    database.init_db()
    return render_template("dashboard.html", counts=database.dashboard_counts(), templates={
        "Client lead": "Subject: A client lead for your practice\n\nHi [Name],\n\nI have a client looking for support with [need]. Are you currently accepting new clients?\n\nBest,\n[Your name]",
        "Hybrid model": "Subject: Invitation to join our hybrid therapist network\n\nHi [Name],\n\nI would love to tell you about our hybrid model for therapists who want qualified referrals with flexible support. Would you be open to a brief conversation?\n\nBest,\n[Your name]",
        "Follow-up": "Subject: Following up\n\nHi [Name],\n\nI wanted to follow up on my note below. I would be glad to connect whenever the timing is right.\n\nBest,\n[Your name]",
    })


@app.get("/export.csv")
def export_csv():
    content = database.therapists_csv(database.all_therapists())
    return send_file(io.BytesIO(content.encode("utf-8")), mimetype="text/csv", as_attachment=True, download_name="therapist-leads.csv")


if __name__ == "__main__":
    database.init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
