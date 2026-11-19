"""Build ``data/CalPolyPomona/cpp_urls.json`` dynamically from the CPP catalog directory.

Run from the repository root with ``python scrapers/CalPolyPomona/get_urls.py``.
"""

from __future__ import annotations

import json
import os
import re
import time
import argparse
from pathlib import Path
from urllib.parse import parse_qsl, parse_qs, urlencode, urljoin, urlsplit, urlunsplit

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = ROOT / "data" / "CalPolyPomona" / "cpp_urls.json"
CATALOG_ID = "78"
HOME_URL = f"https://catalog.cpp.edu/index.php?catoid={CATALOG_ID}"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "Chrome/131.0.0.0 Safari/537.36"
)


def slugify_department(display_name: str) -> str:
    """Turn an official catalog department title into a clean snake_case key."""
    cleaned = display_name.replace("&", " and ").replace("\u2019", "'")
    cleaned = re.sub(r"^the\s+", "", cleaned, flags=re.I)
    cleaned = re.sub(r"^department of\s+", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+department$", "", cleaned, flags=re.I)
    cleaned = cleaned.replace("'", "")
    return re.sub(r"[^a-z0-9]+", "_", cleaned.lower()).strip("_")


def canonical_url(url: str) -> str:
    """Keep catalog parameters but remove transient return-to parameters."""
    parts = urlsplit(urljoin("https://catalog.cpp.edu/", url))
    query = [(key, value) for key, value in parse_qsl(parts.query) if key != "returnto"]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def is_roadmap_title(title: str) -> bool:
    """Identify roadmap catalog entries that should not be scraped."""
    return bool(re.search(r"\broadmaps?\b", title, flags=re.I))


def entity_oid(url: str) -> str | None:
    return parse_qs(urlsplit(url).query).get("ent_oid", [None])[0]


def entity_page_urls(page: Page, department_url: str) -> list[str]:
    """Return the base entity URL plus every numbered page exposed by it."""
    base_parts = urlsplit(department_url)
    base_query = parse_qs(base_parts.query)
    expected_catoid = base_query.get("catoid", [None])[0]
    expected_oid = base_query.get("ent_oid", [None])[0]
    urls = {canonical_url(department_url)}

    for item in catalog_links(page, "preview_entity.php"):
        candidate = canonical_url(item["url"])
        parts = urlsplit(candidate)
        query = parse_qs(parts.query)
        if (
            parts.path.endswith("preview_entity.php")
            and query.get("catoid", [None])[0] == expected_catoid
            and query.get("ent_oid", [None])[0] == expected_oid
            and query.get("p", [None])[0]
            and query["p"][0].isdigit()
        ):
            urls.add(candidate)

    def page_number(url: str) -> int:
        return int(parse_qs(urlsplit(url).query).get("p", ["1"])[0])

    return sorted(urls, key=page_number)


def catalog_links(page: Page, href_fragment: str) -> list[dict[str, str]]:
    return page.eval_on_selector_all(
        f"a[href*='{href_fragment}']",
        """els => els.map(e => ({
            name: (e.innerText || e.textContent || e.getAttribute('aria-label') || e.title || '')
                .replace(/\\s+/g, ' ').trim(),
            url: e.href
        }))""",
    )


def open_page(page: Page, url: str, required_fragment: str | None = None) -> None:
    for attempt in range(3):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=90_000)
            try:
                page.wait_for_load_state("networkidle", timeout=30_000)
            except PlaywrightTimeoutError:
                pass
            selector = f"a[href*='{required_fragment}']" if required_fragment else "a"
            page.wait_for_selector(selector, timeout=45_000)
            return
        except PlaywrightTimeoutError:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))


def find_directory_url(page: Page) -> str | None:
    """Find the Index of Academic Colleges, Departments, and Programs link."""
    for item in catalog_links(page, "content.php"):
        label = item["name"].lower()
        if ("college" in label or "academic" in label) and "department" in label:
            return canonical_url(item["url"])
    return None


def extract_index_entities(page: Page) -> list[dict[str, str]]:
    """Extract each preview_entity.php link paired with its heading on the Index page."""
    return page.evaluate(
        f"""(catoid) => {{
            const results = [];
            const links = Array.from(document.querySelectorAll(`a[href*='preview_entity.php?catoid=${{catoid}}']`));

            // Helper: extract only the direct heading text of a container, ignoring child links/sublists
            function findHeadingForLink(aTag) {{
                // 1. Check preceding text/elements inside the same parent or grandparent
                let curr = aTag;
                for (let depth = 0; depth < 4 && curr; depth++) {{
                    let prev = curr.previousSibling;
                    while (prev) {{
                        const raw = (prev.nodeType === 3 ? prev.textContent : prev.innerText) || '';
                        const firstLine = raw.split('\\n').map(s => s.trim()).filter(Boolean)[0] || '';
                        if (
                            firstLine &&
                            !firstLine.toLowerCase().startsWith('go to information') &&
                            !firstLine.toLowerCase().startsWith('display programs')
                        ) {{
                            return firstLine;
                        }}
                        prev = prev.previousSibling;
                    }}
                    curr = curr.parentElement;
                }}
                return '';
            }}

            for (const a of links) {{
                const linkText = (a.innerText || '').replace(/\\s+/g, ' ').trim();
                const heading = findHeadingForLink(a);
                results.push({{
                    heading: heading || linkText,
                    linkText,
                    url: a.href
                }});
            }}
            return results;
        }}""",
        CATALOG_ID,
    )


def extract_entity_page_heading(page: Page) -> str:
    """Fallback: get the non-'University Catalog' heading inside #acalog-content."""
    return page.evaluate(
        """() => {
            const candidates = Array.from(
                document.querySelectorAll('#acalog-content h1, #acalog-content h2, td.block_content h1, td.block_content h2')
            );
            for (const el of candidates) {
                const txt = (el.innerText || '').replace(/\\s+/g, ' ').trim();
                if (txt && txt.toLowerCase() !== 'university catalog') {
                    return txt;
                }
            }
            return '';
        }"""
    )


def scrape() -> dict[str, list[dict[str, object]]]:
    result: dict[str, list[dict[str, object]]] = {}

    with sync_playwright() as playwright:
        headless = os.getenv("CPP_HEADLESS", "0").lower() in {"1", "true", "yes"}
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()
        try:
            open_page(page, HOME_URL)
            page.wait_for_timeout(3_000)

            directory_url = find_directory_url(page)
            if not directory_url:
                raise RuntimeError(
                    f"Could not find the Colleges & Departments directory link on {page.url}."
                )

            open_page(page, directory_url, "preview_entity.php")

            raw_entities = extract_index_entities(page)
            seen_oids: set[str] = set()
            entities: list[tuple[str, str, str]] = []
            for item in raw_entities:
                clean_url = canonical_url(item["url"])
                oid = entity_oid(clean_url)
                if not oid or oid in seen_oids:
                    continue
                seen_oids.add(oid)
                entities.append((item["heading"], item["linkText"], clean_url))

            if not entities:
                raise RuntimeError(
                    "No preview_entity.php links found; WAF challenge may not have finished."
                )

            for index_heading, link_text, department_url in entities:
                # Skip top-level 'Go to information for this college.' links EXCEPT Collins College
                if "this college" in link_text.lower() and "hospitality" not in index_heading.lower():
                    print(f"[SKIP COLLEGE] {index_heading} ({department_url})")
                    continue

                open_page(page, department_url)
                # Entity pages can paginate both their program list and their
                # course inventory. Discover pages from each page so a page
                # link that is only rendered on a later page is not missed.
                department_pages = entity_page_urls(page, department_url)
                inspected_pages = set()
                programs: dict[str, str] = {}
                while len(inspected_pages) < len(department_pages):
                    page_url = next(url for url in department_pages if url not in inspected_pages)
                    open_page(page, page_url)
                    inspected_pages.add(page_url)
                    for discovered in entity_page_urls(page, department_url):
                        if discovered not in department_pages:
                            department_pages.append(discovered)
                    for item in catalog_links(page, "preview_program.php"):
                        if parse_qs(urlsplit(item["url"]).query).get("catoid", [None])[0] != CATALOG_ID:
                            continue
                        if is_roadmap_title(item["name"]):
                            continue
                        title = re.sub(r":\s*\d+\s*units$", "", item["name"], flags=re.I).strip()
                        if title:
                            programs.setdefault(title, canonical_url(item["url"]))

                if not programs:
                    print(f"[SKIP EMPTY] {index_heading} ({department_url})")
                    continue

                # Prefer the heading from the Index page; fall back to the entity page's h2/non-banner h1
                display_name = index_heading
                if not display_name or display_name.lower().startswith("go to information"):
                    display_name = extract_entity_page_heading(page) or f"department_{entity_oid(department_url)}"

                key = slugify_department(display_name)
                print(f"[OK] {key} ({display_name}) -> {len(programs)} programs")
                result[key] = [{
                    "department": department_url,
                    "department_pages": department_pages,
                    "programs": [programs],
                }]
        finally:
            browser.close()

    return result


def merge_with_existing(
    discovered: dict[str, list[dict[str, object]]],
    existing: dict[str, list[dict[str, object]]],
) -> dict[str, list[dict[str, object]]]:
    """Merge newly discovered pages/programs without dropping old catalog data."""
    merged = json.loads(json.dumps(existing))
    by_url = {
        entry.get("department"): (key, entry)
        for key, values in merged.items()
        for entry in values
        if entry.get("department")
    }
    for key, values in discovered.items():
        for entry in values:
            old_match = by_url.get(entry.get("department"))
            if not old_match:
                merged.setdefault(key, []).append(entry)
                by_url[entry.get("department")] = (key, entry)
                continue
            _, old_entry = old_match
            old_pages = set(old_entry.get("department_pages", []))
            old_entry["department_pages"] = sorted(old_pages | set(entry.get("department_pages", [])))
            old_programs = old_entry.setdefault("programs", [{}])
            old_map = old_programs[0] if old_programs else {}
            for program_group in entry.get("programs", []):
                old_map.update(program_group)
            old_entry["programs"] = [old_map]
    return merged


def write_json(data: dict[str, list[dict[str, object]]]) -> None:
    temporary = OUTPUT_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT_PATH)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="replace the existing URL manifest")
    args = parser.parse_args()
    discovered = scrape()
    existing = {}
    if OUTPUT_PATH.exists() and not args.force:
        existing = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    write_json(discovered if args.force else merge_with_existing(discovered, existing))
    print(f"Saved {OUTPUT_PATH}")
