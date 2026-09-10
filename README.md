# Therapist Lead Finder

A local Flask application for collecting therapist leads, matching them to client needs, and tracking outreach in SQLite.

## Features

- Searches Psychology Today with `requests` and BeautifulSoup.
- Optionally searches Google Maps with Selenium.
- Stores normalized leads in a local `therapists.db` SQLite file.
- Matches specialties to therapy needs and ranks by keyword relevance.
- Tracks outreach status and notes.
- Provides a CRM dashboard, outreach templates, and CSV export.

## Setup

1. Open a terminal in this folder.
2. Create and activate a virtual environment:

   ```text
   python -m venv .venv
   .venv\\Scripts\\activate
   ```

3. Install dependencies:

   ```text
   python -m pip install -r requirements.txt
   ```

4. Start the app:

   ```text
   python app.py
   ```

5. Open http://127.0.0.1:5000 in a browser.

The database is created automatically on first run. Google Maps scraping requires a local Chrome or Chromium installation; Selenium Manager normally downloads the compatible driver automatically. If it is unavailable, Psychology Today results and existing database records still work.

## Notes

Use respectful request rates and comply with each site's terms, robots rules, and applicable privacy law. Directory markup and bot protections can change, so scraping failures are shown as warnings rather than crashing the app. This application is intended for legitimate professional outreach, not bulk unsolicited messaging.
