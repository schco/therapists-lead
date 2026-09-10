"""Web scraping module for Psychology Today therapist profiles."""

from __future__ import annotations

import time
import re
from typing import Any

import requests
from bs4 import BeautifulSoup

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def build_psychology_today_url(city: str, state: str) -> str:
    """Build a Psychology Today search URL for a city/state."""
    city_slug = city.lower().strip().replace(" ", "-")
    state_slug = state.lower().strip()
    return f"https://www.psychologytoday.com/us/therapists/{state_slug}/{city_slug}"


def parse_profile_card(card: BeautifulSoup) -> dict[str, Any] | None:
    """Extract structured data from a single Psychology Today listing card."""
    try:
        # Name and profile link
        name_link = card.find("a", href=re.compile(r"/us/therapists/"))
        if not name_link:
            return None
        name = name_link.get_text(strip=True)

        # Profile URL
        profile_url = name_link.get("href", "")
        if profile_url and not profile_url.startswith("http"):
            profile_url = "https://www.psychologytoday.com" + profile_url

        # Credentials (often in a subtitle or span)
        credentials = ""
        cred_el = card.find(class_=re.compile(r"credential|title|subtitle", re.I))
        if cred_el:
            credentials = cred_el.get_text(strip=True)

        # Description / bio
        description = ""
        desc_el = card.find(class_=re.compile(r"description|bio|text", re.I))
        if desc_el:
            description = desc_el.get_text(strip=True)[:1000]

        # Specialties (tags)
        specialties = []
        for tag in card.find_all(class_=re.compile(r"specialt|tag|issue", re.I)):
            text = tag.get_text(strip=True)
            if text and len(text) < 60:
                specialties.append(text)
        specialties = list(dict.fromkeys(specialties))[:10]

        # Verified badge
        verified = bool(card.find(class_=re.compile(r"verified", re.I)))

        # Phone
        phone = ""
        phone_el = card.find(string=re.compile(r"\(\d{3}\)\s*\d{3}-\d{4}"))
        if phone_el:
            match = re.search(r"\(\d{3}\)\s*\d{3}-\d{4}", str(phone_el))
            if match:
                phone = match.group(0)

        # Location
        city = ""
        state = ""
        zip_code = ""
        location_el = card.find(class_=re.compile(r"location|address", re.I))
        if location_el:
            loc_text = location_el.get_text(" ", strip=True)
            loc_match = re.search(r"([A-Za-z\s]+),\s*([A-Z]{2})\s*(\d{5})?", loc_text)
            if loc_match:
                city = loc_match.group(1).strip()
                state = loc_match.group(2)
                zip_code = loc_match.group(3) or ""

        return {
            "name": name,
            "credentials": credentials,
            "specialties": ", ".join(specialties),
            "description": description,
            "phone": phone,
            "city": city,
            "state": state,
            "zip": zip_code,
            "website": "",
            "verified": 1 if verified else 0,
            "profile_url": profile_url,
            "source": "Psychology Today",
            "practice_size": "solo",
            "fee": "",
            "insurance": "",
            "telehealth": "",
            "pronouns": "",
            "modalities": "",
            "populations": "",
        }
    except Exception:
        return None


def scrape_with_requests(city: str, state: str, max_pages: int = 3) -> tuple[list[dict], list[str]]:
    """Scrape Psychology Today using requests + BeautifulSoup (static fallback)."""
    therapists = []
    errors = []
    base_url = build_psychology_today_url(city, state)

    for page in range(1, max_pages + 1):
        url = f"{base_url}?page={page}" if page > 1 else base_url
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                errors.append(f"Page {page} returned status {resp.status_code}")
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.find_all(class_=re.compile(r"result-row|profile-card", re.I))

            if not cards:
                break

            for card in cards:
                parsed = parse_profile_card(card)
                if parsed:
                    therapists.append(parsed)

            time.sleep(1)  # Be respectful to the server

        except Exception as e:
            errors.append(f"Error scraping page {page}: {e}")
            break

    return therapists, errors


def scrape_with_selenium(city: str, state: str, max_pages: int = 3) -> tuple[list[dict], list[str]]:
    """Scrape Psychology Today using Selenium (handles dynamic JS content)."""
    therapists = []
    errors = []
    base_url = build_psychology_today_url(city, state)

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument(f"user-agent={HEADERS['User-Agent']}")

    driver = None
    try:
        # Automatically download and manage ChromeDriver
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(30)

        for page in range(1, max_pages + 1):
            url = f"{base_url}?page={page}" if page > 1 else base_url
            driver.get(url)

            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "[class*='result-row'], [class*='profile-card']")
                    )
                )
            except Exception:
                errors.append(f"Page {page}: timeout waiting for results")
                break

            soup = BeautifulSoup(driver.page_source, "html.parser")
            cards = soup.find_all(class_=re.compile(r"result-row|profile-card", re.I))

            if not cards:
                break

            for card in cards:
                parsed = parse_profile_card(card)
                if parsed:
                    therapists.append(parsed)

            time.sleep(2)

    except Exception as e:
        errors.append(f"Selenium error: {e}")
    finally:
        if driver:
            driver.quit()

    return therapists, errors


def scrape_all(city: str, state: str, radius: int = 20) -> tuple[list[dict], list[str]]:
    """Main entry point: try Selenium first, fall back to requests."""
    if SELENIUM_AVAILABLE:
        therapists, errors = scrape_with_selenium(city, state)
        if therapists:
            return therapists, errors
        errors.append("Selenium returned no results; falling back to requests.")

    return scrape_with_requests(city, state)
