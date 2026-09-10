"""Best-effort scrapers for Psychology Today and Google Maps.

Scraping public directories can fail because of rate limits, markup changes, or
bot checks. Each source is isolated so a failure still allows the other source
and any previously stored leads to be used.
"""

from __future__ import annotations

import re
import time
from datetime import date
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "TherapistLeadFinder/1.0 (local research tool)"}


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _phone(text: str) -> str:
    match = re.search(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}", text)
    return _clean(match.group(0) if match else "")


def _location_parts(city: str, state: str) -> tuple[str, str]:
    return _clean(city), _clean(state).upper()


def scrape_psychology_today(city: str, state: str, radius: int = 20, pages: int = 2) -> tuple[list[dict], list[str]]:
    """Scrape publicly visible Psychology Today search result cards."""
    results, errors = [], []
    city, state = _location_parts(city, state)
    for page in range(1, pages + 1):
        url = f"https://www.psychologytoday.com/us/therapists/{state.lower()}/{quote_plus(city.lower())}?page={page}"
        try:
            response = requests.get(url, headers=HEADERS, timeout=20)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            cards = soup.select("div.results-row, article.profile-card, .profile-card")
            for card in cards:
                name_node = card.select_one("h2, h3, .profile-title, .profile-name")
                name = _clean(name_node.get_text(" ", strip=True) if name_node else "")
                if not name:
                    continue
                profile = card.select_one("a[href*='/profile/'], a[href*='/us/therapists/']")
                profile_url = urljoin(url, profile.get("href", "")) if profile else ""
                text = _clean(card.get_text(" ", strip=True))
                specialties = _clean((card.select_one(".specialty, .profile-specialties") or card).get_text(" ", strip=True))
                results.append({
                    "name": name, "credentials": "", "specialties": specialties, "phone": _phone(text),
                    "email": "", "website": profile_url, "address": "", "city": city, "state": state,
                    "zip": "", "source": "Psychology Today", "practice_size": "unknown", "profile_url": profile_url,
                    "date_scraped": date.today().isoformat(),
                })
            time.sleep(1.5)
        except requests.RequestException as exc:
            errors.append(f"Psychology Today page {page}: {exc}")
        except Exception as exc:  # Keep one malformed card from stopping a search.
            errors.append(f"Psychology Today page {page}: {exc}")
    return _deduplicate(results), errors


def scrape_google_maps(city: str, state: str, radius: int = 20, max_results: int = 20) -> tuple[list[dict], list[str]]:
    """Use Selenium when installed; otherwise return a clear, non-fatal warning."""
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.chrome.options import Options
    except ImportError:
        return [], ["Google Maps skipped: install selenium and a Chrome/Chromium driver to enable it."]

    results, errors = [], []
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        query = quote_plus(f"therapist {city}, {state}")
        driver.get(f"https://www.google.com/maps/search/{query}")
        time.sleep(3)
        cards = driver.find_elements(By.CSS_SELECTOR, "div[role='article']")[:max_results]
        for card in cards:
            text = _clean(card.text)
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if not lines:
                continue
            link = card.find_elements(By.CSS_SELECTOR, "a[href]")
            website = link[0].get_attribute("href") if link else ""
            results.append({
                "name": lines[0], "credentials": "", "specialties": "therapist", "phone": _phone(text),
                "email": "", "website": website, "address": " ".join(lines[1:3]), "city": city,
                "state": state.upper(), "zip": "", "source": "Google Maps", "practice_size": "unknown",
                "profile_url": website, "date_scraped": date.today().isoformat(),
            })
    except Exception as exc:
        errors.append(f"Google Maps: {exc}")
    finally:
        if driver:
            driver.quit()
    return _deduplicate(results), errors


def scrape_all(city: str, state: str, radius: int = 20) -> tuple[list[dict], list[str]]:
    psychology_results, psychology_errors = scrape_psychology_today(city, state, radius)
    maps_results, maps_errors = scrape_google_maps(city, state, radius)
    return _deduplicate(psychology_results + maps_results), psychology_errors + maps_errors


def _deduplicate(items: list[dict]) -> list[dict]:
    unique = {}
    for item in items:
        key = (item.get("name", "").lower(), item.get("city", "").lower(), item.get("phone", ""))
        unique[key] = item
    return list(unique.values())
