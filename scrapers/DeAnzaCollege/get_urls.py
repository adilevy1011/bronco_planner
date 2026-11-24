"""Discover De Anza College subject/course-listing pages.

Run from the repository root with::

    python scrapers/DeAnzaCollege/get_urls.py

The catalog's Course Listings page is a static index, while individual
listing pages are loaded by the Elumen content API.  Keep both URLs in the
manifest so the scraper can use the browser URL as its public source URL and
the API URL as a stable fallback.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "DeAnzaCollege"
OUTPUT_PATH = DATA_DIR / "deanza_urls.json"
CATALOG_URL = "https://deanza.elumenapp.com/catalog/2026-2027/course-listings#mainContent"
DEGREE_LISTINGS_URL = "https://deanza.elumenapp.com/catalog/2026-2027/degree-and-certificate-listings#mainContent"
API_ROOT = "https://api-prod.elumenapp.com/catalog/sites/publish/content/2026-2027,{}?tenant=deanza.elumenapp.com"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"


def clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\xa0", " ")).strip()


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "subject"


def api_url_from_href(href: str) -> str:
    slug = href.rstrip("/").split("/")[-1].split("#", 1)[0]
    return API_ROOT.format(quote(slug, safe="-"))


def program_api_url_from_href(href: str) -> str:
    slug = href.rstrip("/").split("/")[-1].split("#", 1)[0].removeprefix("program,")
    return f"https://api-prod.elumenapp.com/catalog/sites/publish/content/2026-2027,program,{quote(slug, safe='-')}?tenant=deanza.elumenapp.com"


def extract_subjects(html: str, base_url: str = CATALOG_URL) -> list[dict[str, str]]:
    """Extract the subject cards from the Course Listings index."""
    soup = BeautifulSoup(html, "html.parser")
    # Elumen sets ``<base href="/catalog/">``.  Resolve links against that
    # base instead of the current /2026-2027/course-listings path.
    link_base = urljoin(base_url, soup.find("base").get("href")) if soup.find("base") else "https://deanza.elumenapp.com/catalog/"
    subjects, seen = [], set()
    for anchor in soup.select("#mainContent a.h5.stretched-link, main a.h5.stretched-link, a.h5.stretched-link"):
        name = clean_text(anchor.get_text(" "))
        href = anchor.get("href", "")
        if not name or not href or "course" not in name.lower() or href in seen:
            continue
        match = re.match(r"^([A-Z][A-Z0-9]+)\s+-\s+(.+?)\s+Courses?$", name, re.I)
        code, subject_name = match.groups() if match else ("", name)
        source_url = urljoin(link_base, href.split("#", 1)[0])
        slug = source_url.rstrip("/").split("/")[-1]
        subjects.append({
            "id": slugify(slug.removesuffix("-courses")),
            "subject_code": code.upper(),
            "name": subject_name.strip(),
            "source_url": source_url,
            "api_url": api_url_from_href(href),
        })
        seen.add(href)
    return subjects


def extract_program_departments(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    base = urljoin("https://deanza.elumenapp.com/catalog/", soup.find("base").get("href")) if soup.find("base") else "https://deanza.elumenapp.com/catalog/"
    departments, seen = [], set()
    for anchor in soup.find_all("a", href=re.compile(r"degrees-and-certificates")):
        name = clean_text(anchor.get_text(" "))
        href = anchor.get("href", "")
        href_path = urlparse(href).path.lstrip("/")
        if not href_path.endswith("-degrees-and-certificates"):
            continue
        source_url = urljoin(base, href.split("#", 1)[0])
        if source_url in seen:
            continue
        slug = source_url.rstrip("/").split("/")[-1].removesuffix("-degrees-and-certificates")
        display_name = name.removesuffix(" Degrees and Certificates").strip()
        if not display_name or display_name.lower() == name.lower():
            display_name = slug.replace("-", " ").title()
        departments.append({"id": slugify(slug), "name": display_name, "source_url": source_url, "api_url": api_url_from_href(href)})
        seen.add(source_url)
    return departments


def extract_programs(html: str, department: dict[str, str]) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    base = urljoin("https://deanza.elumenapp.com/catalog/", soup.find("base").get("href")) if soup.find("base") else "https://deanza.elumenapp.com/catalog/"
    programs, seen = [], set()
    for anchor in soup.find_all("a"):
        href = anchor.get("href", "")
        onclick = anchor.get("onclick", "")
        if "/program/" not in href and "program," not in href and ",program," not in onclick:
            continue
        source_url = urljoin(base, href.split("#", 1)[0])
        slug = source_url.rstrip("/").split("/")[-1].removeprefix("program,")
        if not slug or slug in seen:
            continue
        programs.append({"id": slugify(slug), "name": clean_text(anchor.get_text(" ")), "department": department["name"], "department_id": department["id"], "source_url": source_url, "api_url": program_api_url_from_href(href or slug)})
        seen.add(slug)
    return programs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html", type=Path, help="Parse a saved Course Listings HTML file")
    parser.add_argument("--degree-html", type=Path, help="Parse a saved Degree and Certificate Listings HTML file")
    args = parser.parse_args()
    if args.html:
        html = args.html.read_text(encoding="utf-8")
        subjects = extract_subjects(html, CATALOG_URL)
        programs = []
    elif args.degree_html:
        html = args.degree_html.read_text(encoding="utf-8")
        departments = extract_program_departments(html)
        programs = []
        subjects = []
    else:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(user_agent=USER_AGENT)
            page = context.new_page()
            page.goto(CATALOG_URL, wait_until="domcontentloaded", timeout=90_000)
            page.wait_for_selector("a.h5.stretched-link", timeout=45_000)
            subjects = extract_subjects(page.content(), page.url)
            page.goto(DEGREE_LISTINGS_URL, wait_until="domcontentloaded", timeout=90_000)
            # Wait for the actual degree-listing content, not merely the
            # matching links copied into hidden navigation markup.
            page.wait_for_function(
                """() => document.body.innerText.includes('Degree and Certificate Listings') &&
                    document.querySelectorAll("a[href*='degrees-and-certificates']").length > 10""",
                timeout=45_000,
            )
            departments = extract_program_departments(page.content())
            print(f"Discovered {len(departments)} program departments; collecting individual programs...")
            programs = []
            for department in departments:
                page.goto(department["source_url"], wait_until="domcontentloaded", timeout=90_000)
                page.wait_for_function(
                    """() => document.querySelectorAll(
                        "#mainContent a[href*='/program/'], #mainContent a[href*='program,']"
                    ).length > 0""",
                    timeout=45_000,
                )
                programs.extend(extract_programs(page.content(), department))
            browser.close()
    if not subjects and not args.degree_html:
        raise RuntimeError("No De Anza subject pages found")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if args.degree_html:
        programs = []
        departments = extract_program_departments(html)
    else:
        departments = locals().get("departments", [])
    OUTPUT_PATH.write_text(json.dumps({"catalog_url": CATALOG_URL, "degree_listings_url": DEGREE_LISTINGS_URL, "subjects": subjects, "program_departments": departments, "programs": programs}, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(subjects)} subject URLs and {len(programs)} program URLs to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
