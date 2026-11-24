"""Scrape CPP catalog program pages into planner-friendly JSON.

Usage:
    python scrapers/CalPolyPomona/scrape_catalog.py
    python scrapers/CalPolyPomona/scrape_catalog.py --only "Computer Science, B.S."
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import BrowserContext, Page, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "CalPolyPomona"
URLS_PATH = DATA_DIR / "cpp_urls.json"
PROGRAMS_DIR = DATA_DIR / "programs"
DEPARTMENTS_DIR = DATA_DIR / "departments"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
COURSE_RE = re.compile(r"^([A-Z]{2,6}\s+\d{3,4}[A-Z]?)\s*-\s*(.*)$")
DETAIL_LABELS = r"(Prerequisite\(s\):|Grading Basis:|Repeat for Credit:|When Offered:|$)"
DETAIL_FIELDS = ("description", "prerequisites", "grading_basis", "repeat_for_credit", "when_offered")


def clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\xa0", " ")).strip()


def clean_detail_value(value: str | None) -> str:
    """Remove catalog page chrome that appears after course metadata."""
    value = clean_text(value)
    return clean_text(re.split(r"Back to Top|Print-Friendly Page|Facebook this Page|Tweet this Page|Add to Portfolio", value, maxsplit=1, flags=re.I)[0])


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value or "program"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def catalog_id(url: str) -> str:
    return parse_qs(urlparse(url).query).get("catoid", ["unknown"])[0]


def load_program_urls() -> list[dict]:
    """Flatten department -> program entries from cpp_urls.json."""
    source = json.loads(URLS_PATH.read_text(encoding="utf-8"))
    programs = []
    for department_slug, departments in source.items():
        for department in departments:
            for program_group in department.get("programs", []):
                for name, url in program_group.items():
                    programs.append({
                        "id": slugify(name), "name": name,
                        "department_id": slugify(department_slug),
                        "department": department_slug.replace("_", " ").title(),
                        "department_url": department.get("department"),
                        "department_pages": department.get("department_pages"),
                        "url": url, "catoid": catalog_id(url),
                    })
    return programs


def parse_course_link(raw_text: str) -> dict | None:
    cleaned = clean_text(raw_text)
    match = COURSE_RE.match(cleaned)
    if not match:
        return None
    code, remainder = match.groups()
    # Catalog pages can append more than one bracketed annotation, e.g.
    # ``(3) [GE 4B] [AmInst-B]``.  Only the GE annotation belongs in ``ge``;
    # the other annotations are catalog metadata, not part of the title.
    annotations = []
    while True:
        annotation_match = re.search(r"\s*\[([^]]+)\]\s*$", remainder)
        if not annotation_match:
            break
        annotations.insert(0, annotation_match.group(1).strip())
        remainder = remainder[:annotation_match.start()].rstrip()
    ge = next((item for item in annotations if re.match(r"GE\b", item, re.I)), None)
    unit_match = re.search(r"\s*\((\d+(?:\s*-\s*\d+)?)\)\s*$", remainder)
    units = re.sub(r"\s*", "", unit_match.group(1)) if unit_match else None
    if unit_match:
        remainder = remainder[:unit_match.start()].rstrip()
    return {"code": code, "title": remainder, "units": units or "N/A", "ge": ge}


def extract_coid(element) -> str | None:
    attributes = f"{element.get('href', '')} {element.get('onclick', '')}"
    for pattern in [
        r"coid[=,]\s*['\"]?(\d+)",
        r"showCourse\s*\(\s*['\"]?\d+['\"]?\s*,\s*['\"]?(\d+)",
        # Expanded department pages use hideCatalogData(catoid, entity, coid, ...).
        r"hideCatalogData\s*\(\s*['\"]?\d+['\"]?\s*,\s*['\"]?\d+['\"]?\s*,\s*['\"]?(\d+)",
    ]:
        match = re.search(pattern, attributes, re.I)
        if match:
            return match.group(1)
    return None


def parse_course_details(html_text: str) -> dict:
    soup = BeautifulSoup(html_text, "html.parser")
    # Expanded rows can contain the page toolbar and hidden tooltip markup.
    # Those are presentation chrome, not course metadata.
    for node in soup.select(".gateway-toolbar, .tooltip, script, style"):
        node.decompose()
    content = soup.find("td", class_="block_content") or soup.find("div", class_="custompad_style") or soup
    text = clean_text(content.get_text(" "))
    details = {"description": "", "prerequisites": "", "grading_basis": "", "repeat_for_credit": "", "when_offered": ""}
    fields = {
        "prerequisites": r"Prerequisite\(s\):\s*(.*?)\s*(?=" + DETAIL_LABELS + ")",
        "grading_basis": r"Grading Basis:\s*(.*?)\s*(?=" + DETAIL_LABELS + ")",
        "repeat_for_credit": r"Repeat for Credit:\s*(.*?)\s*(?=" + DETAIL_LABELS + ")",
        "when_offered": r"When Offered:\s*(.*?)\s*(?=" + DETAIL_LABELS + ")",
    }
    for name, pattern in fields.items():
        match = re.search(pattern, text, re.I)
        if match:
            details[name] = clean_detail_value(match.group(1))
    description = re.split(DETAIL_LABELS, text, maxsplit=1, flags=re.I)[0]
    description = re.sub(
        r"^(?:[A-Z]{2,6}\s+\d{3,4}[A-Z]?\s*-\s*.*?\([\d.-]+\)\s*)+",
        "", description, flags=re.I,
    )
    description = re.sub(r"(Back to Top|Print-Friendly Page|Facebook this Page|Tweet this Page|Add to Portfolio).*", "", description, flags=re.I)
    details["description"] = clean_text(description)
    return details


def inline_course_details(anchor) -> dict:
    """Read details already expanded inside a department/program page."""
    parent = anchor.find_parent("li") or anchor.parent
    if not parent:
        return {}
    text = clean_text(parent.get_text(" "))
    if not re.search(r"(?:Prerequisite\(s\)|Grading Basis|Repeat for Credit|When Offered):", text, re.I):
        return {}
    return parse_course_details(str(parent))


def merge_course_details(course: dict, details: dict) -> None:
    """Keep inline data when a detail request fails or returns no fields."""
    for field in DETAIL_FIELDS:
        course.setdefault(field, "")
        value = clean_text(details.get(field))
        if value:
            course[field] = value


def parse_requirement_name(element) -> str:
    heading = element.find_previous(["h2", "h3", "h4", "h5", "h6", "b", "strong"])
    return clean_text(heading.get_text(" ")) if heading else "General Requirements"


def extract_course_candidates(soup: BeautifulSoup, requirement_name: str | None = None) -> list[dict]:
    """Extract and deduplicate course links from either a program or department page."""
    courses, seen = [], set()
    for anchor in soup.find_all("a"):
        course = parse_course_link(anchor.get_text(" "))
        if not course or course["code"] in seen:
            continue
        course["coid"] = extract_coid(anchor)
        merge_course_details(course, inline_course_details(anchor))
        if requirement_name is not None:
            course["requirement"] = requirement_name
        courses.append(course)
        seen.add(course["code"])
    return courses


def extract_program(soup: BeautifulSoup, program: dict) -> dict:
    title_element = soup.find("h1") or soup.find("title")
    title = clean_text(title_element.get_text(" ") if title_element else program["name"])
    body = soup.find("main") or soup.find("body") or soup
    raw_text = clean_text(body.get_text(" "))
    candidates = []
    for anchor in soup.find_all("a"):
        course = parse_course_link(anchor.get_text(" "))
        if course:
            candidates.append((anchor, course))

    requirements, courses, seen_courses, seen_requirements = [], [], set(), {}
    for anchor, course in candidates:
        category = parse_requirement_name(anchor)
        course["coid"] = extract_coid(anchor)
        merge_course_details(course, inline_course_details(anchor))
        course["requirement"] = category
        if course["code"] not in seen_courses:
            courses.append(course)
            seen_courses.add(course["code"])
        if category not in seen_requirements:
            seen_requirements[category] = {"name": category, "courses": [], "raw_text": category}
            requirements.append(seen_requirements[category])
        if course["code"] not in seen_requirements[category]["courses"]:
            seen_requirements[category]["courses"].append(course["code"])

    return {
        "schema_version": 1, "scraped_at": now_iso(), "id": program["id"], "name": program["name"],
        "title_on_page": title, "department": program["department"], "department_id": program["department_id"], "source_url": program["url"],
        "department_url": program["department_url"], "catalog_id": program["catoid"],
        "program_text": raw_text[:4000], "requirements": requirements, "courses": courses,
    }


def extract_department(soup: BeautifulSoup, department: dict) -> dict:
    title_element = soup.find("h1") or soup.find("title")
    title = clean_text(title_element.get_text(" ") if title_element else department["name"])
    body = soup.find("main") or soup.find("body") or soup
    courses = extract_course_candidates(body)
    return {
        "schema_version": 1, "scraped_at": now_iso(), "id": department["id"], "name": department["name"],
        "title_on_page": title, "source_url": department["url"], "catalog_id": department["catoid"],
        "source_pages": department.get("pages") or [department["url"]],
        "department_text": clean_text(body.get_text(" "))[:4000], "courses": courses, "programs": [],
    }


def fetch_course_details(context: BrowserContext, course: dict, cache: dict, catoid: str) -> None:
    coid = course.get("coid")
    if not coid:
        for field in DETAIL_FIELDS:
            course.setdefault(field, "")
        return
    if coid not in cache:
        url = f"https://catalog.cpp.edu/preview_course_nopop.php?catoid={catoid}&coid={coid}"
        for attempt in range(3):
            try:
                response = context.request.get(url, timeout=60000)
                cache[coid] = parse_course_details(response.text()) if response.ok else {}
                break
            except Exception as error:
                if attempt == 2:
                    print(f"  warning: detail failed for {course['code']}: {error}", file=sys.stderr)
                    cache[coid] = {}
                else:
                    time.sleep(1.5 * (attempt + 1))
        time.sleep(0.15)
    merge_course_details(course, cache[coid])
    for field in DETAIL_FIELDS:
        course.setdefault(field, "")


def scrape_program(page: Page, context: BrowserContext, program: dict, detail_cache: dict) -> dict:
    print(f"[{program['department']}] {program['name']}")
    page.goto(program["url"], wait_until="domcontentloaded", timeout=90000)
    try:
        page.wait_for_selector("a", timeout=30000)
    except Exception:
        print("  warning: page did not expose links before timeout", file=sys.stderr)
    result = extract_program(BeautifulSoup(page.content(), "html.parser"), program)
    for course in result["courses"]:
        fetch_course_details(context, course, detail_cache, program["catoid"])
    print(f"  scraped {len(result['courses'])} unique courses in {len(result['requirements'])} requirement groups")
    return result


def scrape_department(page: Page, department: dict, programs: list[dict]) -> dict:
    print(f"[{department['name']}] department catalog")
    page_urls = department.get("pages") or [department["url"]]
    result = None
    all_courses = {}
    page_text = []
    for page_url in page_urls:
        page.goto(page_url, wait_until="domcontentloaded", timeout=90000)
        try:
            page.wait_for_selector("a", timeout=30000)
        except Exception:
            print(f"  warning: department page did not expose links before timeout: {page_url}", file=sys.stderr)
        current = extract_department(BeautifulSoup(page.content(), "html.parser"), department)
        result = result or current
        page_text.append(current["department_text"])
        for course in current["courses"]:
            all_courses.setdefault(course["code"], course)
    result["courses"] = list(all_courses.values())
    result["department_text"] = clean_text(" ".join(page_text))[:4000]
    result["programs"] = [{"id": p["id"], "name": p["name"]} for p in programs]
    print(f"  scraped {len(result['courses'])} department courses across {len(page_urls)} page(s)")
    return result


def write_outputs(results: list[dict], departments: list[dict], force: bool = False) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    PROGRAMS_DIR.mkdir(exist_ok=True)
    DEPARTMENTS_DIR.mkdir(exist_ok=True)
    manifest_path = DATA_DIR / "manifest.json"
    # A forced targeted refresh must preserve records for departments/programs
    # that were not selected.  Individual records are replaced below.
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {"schema_version": 1, "scraped_at": now_iso(), "departments": [], "programs": []}
    manifest["scraped_at"] = now_iso()

    for department in departments:
        path = DEPARTMENTS_DIR / f"{department['id']}.json"
        path.write_text(json.dumps(department, indent=2, ensure_ascii=False), encoding="utf-8")
        record = {
            "id": department["id"], "name": department["name"], "source_url": department["source_url"],
            "file": f"departments/{path.name}", "course_count": len(department["courses"]),
        }
        manifest["departments"] = [item for item in manifest["departments"] if item.get("id") != department["id"]]
        manifest["departments"].append(record)
    for result in results:
        path = PROGRAMS_DIR / f"{result['id']}.json"
        path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        record = {
            "id": result["id"], "name": result["name"], "department": result["department"],
            "source_url": result["source_url"], "file": f"programs/{path.name}",
            "course_count": len(result["courses"]), "requirement_count": len(result["requirements"]),
        }
        manifest["programs"] = [item for item in manifest["programs"] if item.get("id") != result["id"]]
        manifest["programs"].append(record)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--program", "--only", dest="program", action="append", help="Scrape only this exact program name; repeatable")
    parser.add_argument(
        "--department", action="append",
        help="Refresh only this department catalog by id or exact name; repeatable",
    )
    parser.add_argument("--all-programs", action="store_true", help="Scrape every discovered program")
    parser.add_argument("--all-departments", action="store_true", help="Refresh every discovered department catalog")
    parser.add_argument("--force", action="store_true", help="re-scrape and replace all selected data")
    args = parser.parse_args()
    all_programs = load_program_urls()
    program_filter = set(args.program or [])
    if program_filter:
        wanted = {value.strip() for value in program_filter}
        selected_programs = [p for p in all_programs if p["name"] in wanted]
        missing = wanted - {p["name"] for p in selected_programs}
        if missing:
            parser.error(f"program not found in cpp_urls.json: {', '.join(sorted(missing))}")
    else:
        selected_programs = all_programs

    if args.department:
        wanted_departments = {value.strip().lower() for value in args.department}
        department_matches = {
            program["department_id"]: program["department"]
            for program in all_programs
            if program["department_id"] in wanted_departments
            or program["department"].lower() in wanted_departments
        }
        missing_departments = wanted_departments - set(department_matches) - {
            name.lower() for name in department_matches.values()
        }
        if missing_departments:
            parser.error(
                "department not found: " + ", ".join(sorted(missing_departments))
                + ". Use a department id such as mathematics-and-statistics."
            )
        department_programs = [
            program for program in all_programs
            if program["department_id"] in department_matches
        ]
    else:
        department_programs = all_programs

    if args.all_departments:
        department_programs = all_programs
    elif (args.program or args.all_programs) and not args.department:
        department_programs = []

    if args.program and args.department:
        department_programs = [p for p in department_programs if p["name"] in {item["name"] for item in selected_programs}]

    if args.all_programs:
        programs_to_scrape = selected_programs
    elif args.program:
        programs_to_scrape = selected_programs
    elif args.department or args.all_departments:
        programs_to_scrape = []
    else:
        programs_to_scrape = all_programs

    if not department_programs and not programs_to_scrape:
        parser.error("no programs found")

    results, departments, detail_cache = [], [], {}
    skipped_programs = 0
    skipped_departments = 0
    department_records = {}
    output_departments = {}
    department_groups = {}
    for program in department_programs:
        department_groups.setdefault(program["department_id"], []).append(program)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()
        for department in department_groups.values():
            representative = department[0]
            department_info = {
                "id": representative["department_id"], "name": representative["department"],
                "url": representative["department_url"], "catoid": representative["catoid"],
                "pages": representative.get("department_pages") or [representative["department_url"]],
            }
            try:
                department_path = DEPARTMENTS_DIR / f"{department_info['id']}.json"
                existing_department = None
                if department_path.exists() and not args.force:
                    existing_department = json.loads(department_path.read_text(encoding="utf-8"))
                expected_pages = set(department_info["pages"])
                recorded_pages = set((existing_department or {}).get("source_pages", []))
                existing_program_names = {p.get("name") for p in (existing_department or {}).get("programs", [])}
                needs_department = (
                    args.force
                    or existing_department is None
                    or any(p["name"] not in existing_program_names for p in department)
                    or (len(expected_pages) > 1 and not expected_pages.issubset(recorded_pages))
                )
                if needs_department:
                    department_result = scrape_department(page, department_info, department)
                    for course in department_result["courses"]:
                        fetch_course_details(context, course, detail_cache, department_info["catoid"])
                    department_records[department_info["id"]] = department_result
                    output_departments[department_info["id"]] = department_result
                else:
                    department_records[department_info["id"]] = existing_department
                    skipped_departments += 1
            except Exception as error:
                print(f"  ERROR scraping department {department_info['name']}: {error}", file=sys.stderr)
        for program in programs_to_scrape:
            program_path = PROGRAMS_DIR / f"{program['id']}.json"
            if program_path.exists() and not args.force:
                skipped_programs += 1
                continue
            try:
                results.append(scrape_program(page, context, program, detail_cache))
            except Exception as error:
                print(f"  ERROR: {error}", file=sys.stderr)
        browser.close()
    # Join program requirements to the complete department catalog by course code.
    for result in results:
        department = department_records.get(result["department_id"])
        if not department:
            continue
        department_codes = {c["code"] for c in department["courses"]}
        result["department_course_codes"] = sorted(c["code"] for c in result["courses"] if c["code"] in department_codes)
        for course in department["courses"]:
            if course["code"] in result["department_course_codes"]:
                course.setdefault("programs", []).append(result["id"])
        if department and department["id"] not in output_departments:
            output_departments[department["id"]] = department
    write_outputs(results, list(output_departments.values()), args.force)
    print(f"\nWrote {len(output_departments)} department files to {DEPARTMENTS_DIR}")
    print(f"Wrote {len(results)} program files to {PROGRAMS_DIR}")
    print(f"Wrote manifest to {DATA_DIR / 'manifest.json'}")
    if not results and not output_departments and (skipped_programs or skipped_departments):
        print(
            f"Nothing was refreshed ({skipped_programs} programs and "
            f"{skipped_departments} departments already existed). "
            "Use --force to apply scraper/parser changes to existing JSON."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
