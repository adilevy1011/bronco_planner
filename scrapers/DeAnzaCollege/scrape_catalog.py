"""Scrape De Anza College course-listing pages into planner-friendly JSON.

Usage::

    python scrapers/DeAnzaCollege/get_urls.py
    python scrapers/DeAnzaCollege/scrape_catalog.py --only cis-computer-science-and-information-systems

This is deliberately a prototype: De Anza's Elumen pages are subject pages,
not CPP-style department/program pages, so each subject becomes a department
record and its courses are stored in ``data/DeAnzaCollege/departments``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import BrowserContext, Page, sync_playwright

from get_urls import DATA_DIR, OUTPUT_PATH, USER_AGENT


DETAIL_FIELDS = (
    "description", "prerequisites", "corequisites", "advisories",
    "transferability", "credit_status", "effective_term", "grading_method",
    "repeat_limit", "student_learning_outcomes", "limitation_on_enrollment",
)
COURSE_RE = re.compile(r"^([A-Z]{2,6})\s+(D?\d{1,4}[A-Z]{0,3})\b(?:\s*[-–:]\s*)?(.*)$", re.I)


def clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\xa0", " ").replace("\ufffd", " ")).strip()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_course_heading(text: str, subject_code: str = "") -> dict | None:
    text = clean_text(text)
    match = COURSE_RE.match(text)
    if not match and subject_code:
        match = re.match(rf"^({re.escape(subject_code)})\s+(D?\d{{1,4}}[A-Z]{{0,3}})\b(?:\s*[-–:]\s*)?(.*)$", text, re.I)
    if not match:
        return None
    department, number, title = match.groups()
    units_match = re.search(r"\b(\d+(?:\.\d+)?(?:\s*[-/]\s*\d+(?:\.\d+)?)?)\s*(?:units?|credits?)\b", title, re.I)
    units = units_match.group(1).replace(" ", "") if units_match else "N/A"
    if units_match:
        title = (title[:units_match.start()].strip(" -–:()") + " " + title[units_match.end():].strip(" -–:()"))
    title = title.strip()
    return {"code": f"{department.upper()} {number.upper()}", "title": title or "", "units": units}


def field_value(text: str, label: str, labels: list[str]) -> str:
    other = "|".join(re.escape(item) for item in labels if item.lower() != label.lower())
    match = re.search(rf"{re.escape(label)}\s*:?\s*(.*?)(?=\s+(?:{other})\s*:|$)", text, re.I)
    return clean_text(match.group(1)) if match else ""


def parse_course_container(container, heading, subject_code: str) -> dict | None:
    course = parse_course_heading(heading.get_text(" "), subject_code)
    if not course:
        return None
    text = clean_text(container.get_text(" "))
    labels = ["Description", "Prerequisite", "Prerequisites", "Advisory", "Advisories", "Course Content"]
    course["description"] = field_value(text, "Description", labels)
    course["prerequisites"] = field_value(text, "Prerequisites", labels) or field_value(text, "Prerequisite", labels)
    course["advisories"] = field_value(text, "Advisories", labels) or field_value(text, "Advisory", labels)
    course["course_content"] = field_value(text, "Course Content", labels)
    course["source_text"] = text[:4000]
    return course


def course_api_url(href: str) -> str:
    slug = href.rstrip("/").split("/")[-1].split("#", 1)[0]
    return f"https://api-prod.elumenapp.com/catalog/sites/publish/content/2026-2027,course,{quote(slug)}?tenant=deanza.elumenapp.com"


def extract_course_cards(soup: BeautifulSoup, subject_code: str, base_url: str) -> list[dict]:
    """Extract the course cards used by De Anza subject pages."""
    courses, seen = [], set()
    for card in soup.select(".course-list .course-item, div.course-item[data-code]"):
        anchor = card.select_one("a[href*='/course/']")
        if not anchor:
            continue
        code_element = card.select_one("small[id$='-code'], small")
        code = clean_text(code_element.get_text(" ") if code_element else card.get("data-code", ""))
        title = clean_text(card.get("data-title") or anchor.get_text(" "))
        if not code:
            parsed = parse_course_heading(title, subject_code)
            if not parsed:
                continue
            code, title = parsed["code"], parsed["title"]
        code = re.sub(r"\s+", " ", code).strip()
        if code in seen:
            continue
        href = anchor.get("href", "").split("#", 1)[0]
        source_url = urljoin(base_url, href)
        courses.append({
            "code": code,
            "title": title,
            "units": "N/A",
            "description": "",
            "prerequisites": "",
            "advisories": "",
            "course_content": "",
            "source_url": source_url,
            "api_url": course_api_url(href),
        })
        seen.add(code)
    return courses


def extract_courses(soup: BeautifulSoup, subject_code: str) -> list[dict]:
    """Extract headings and their nearest content blocks from a subject page."""
    # Subject pages use course cards; course detail pages use headings.
    card_courses = extract_course_cards(soup, subject_code, "https://deanza.elumenapp.com/catalog/")
    if card_courses:
        return card_courses
    courses, seen = [], set()
    body = soup.select_one("#mainContent") or soup.find("main") or soup
    for heading in body.find_all(["h2", "h3", "h4", "h5", "h6"]):
        if not parse_course_heading(heading.get_text(" "), subject_code):
            continue
        container = heading.find_parent(class_=re.compile(r"course|card|accordion|listing", re.I))
        if not container:
            container = heading.parent
        course = parse_course_container(container, heading, subject_code)
        if course and course["code"] not in seen:
            courses.append(course)
            seen.add(course["code"])
    return courses


def parse_course_detail(soup: BeautifulSoup, course: dict) -> dict:
    """Parse a De Anza course page's description and Course Information DL."""
    main = soup.select_one("#mainContent") or soup.find("main") or soup
    description = main.select_one("#c-desc")
    units = main.select_one("#units-designator")
    if description:
        course["description"] = clean_text(description.get_text(" "))
    if units:
        course["units"] = clean_text(units.get_text(" ")).replace(" Units", "").strip()

    metadata: dict[str, str | list[str]] = {}
    for label in main.select("dt"):
        value_node = label.find_next_sibling("dd")
        key = clean_text(label.get_text(" "))
        value = clean_text(value_node.get_text(" ") if value_node else "")
        if not key:
            continue
        previous = metadata.get(key)
        if previous is None:
            metadata[key] = value
        elif previous != value:
            metadata[key] = previous + [value] if isinstance(previous, list) else [previous, value]
    course["metadata"] = metadata
    outline_link = main.find("a", string=re.compile(r"View Active Outline", re.I))
    if outline_link and outline_link.get("href"):
        course["outline_url"] = urljoin("https://www.deanza.edu/", outline_link["href"])

    promoted = {
        "prerequisites": "Prerequisite(s)",
        "corequisites": "Corequisite(s)",
        "advisories": "Advisory(ies)",
        "transferability": "Transferability",
        "credit_status": "Course Credit Status",
        "effective_term": "Effective Term",
        "grading_method": "Grading Method",
        "repeat_limit": "Repeat Limit",
        "student_learning_outcomes": "Student Learning Outcomes",
        "limitation_on_enrollment": "Limitation(s) on Enrollment",
    }
    for field, label in promoted.items():
        value = metadata.get(label, "")
        if isinstance(value, list):
            value = "; ".join(item for item in value if item)
        course[field] = value
    return course


def outline_section_value(container, label: str) -> str:
    """Collect text between an outline h3 label and the next h3."""
    heading = next(
        (item for item in container.find_all("h3") if clean_text(item.get_text(" ")).rstrip(":").lower() == label.lower()),
        None,
    )
    if not heading:
        return ""
    values = []
    for sibling in heading.find_next_siblings():
        if sibling.name == "h3":
            break
        value = clean_text(sibling.get_text(" "))
        if value and value.lower() not in {"course information", "course development options"}:
            values.append(value)
    return clean_text(" ".join(values))


def parse_active_outline(soup: BeautifulSoup, course: dict) -> dict:
    """Parse the small subset of the active outline needed by the planner."""
    main = soup.select_one("#cor-full") or soup.select_one("#mainContent") or soup
    description = next(
        (clean_text(dt.find_next_sibling("dd").get_text(" "))
         for dt in main.select("dt")
         if clean_text(dt.get_text(" ")).lower() == "course description" and dt.find_next_sibling("dd")),
        "",
    )
    if description:
        course["description"] = description
    course["prerequisites"] = outline_section_value(main, "Prerequisite(s)") or course.get("prerequisites", "")
    course["corequisites"] = outline_section_value(main, "Corequisite(s)") or course.get("corequisites", "")
    course["advisories"] = outline_section_value(main, "Advisory(ies)") or course.get("advisories", "")
    course["limitation_on_enrollment"] = outline_section_value(main, "Limitation(s) on Enrollment") or course.get("limitation_on_enrollment", "")

    outline_metadata = {}
    for dt in main.select("dt"):
        dd = dt.find_next_sibling("dd")
        if dd:
            outline_metadata[clean_text(dt.get_text(" "))] = clean_text(dd.get_text(" "))
    course["grading_basis"] = outline_metadata.get("Grade Options", "") or outline_metadata.get("Grading Method", "")
    course["repeat_for_credit"] = outline_metadata.get("Repeat Limit", "")
    course["when_offered"] = outline_metadata.get("Effective Term", "")
    return course


def fetch_course_detail(context: BrowserContext, course: dict) -> None:
    """Fill a course record from its Elumen detail endpoint."""
    try:
        response = context.request.get(course["api_url"], timeout=60_000)
        if response.ok:
            parse_course_detail(BeautifulSoup(response.text(), "html.parser"), course)
            outline_url = course.get("outline_url")
            if outline_url:
                outline_response = context.request.get(outline_url, timeout=60_000)
                if outline_response.ok:
                    parse_active_outline(BeautifulSoup(outline_response.text(), "html.parser"), course)
        else:
            print(f"  warning: detail request returned {response.status} for {course['code']}", file=sys.stderr)
    except Exception as error:
        print(f"  warning: detail failed for {course['code']}: {error}", file=sys.stderr)


def fetch_subject_html(context: BrowserContext, page: Page, subject: dict) -> str:
    page.goto(subject["source_url"], wait_until="domcontentloaded", timeout=90_000)
    try:
        page.wait_for_selector("#mainContent", timeout=30_000)
    except Exception:
        pass
    html = page.content()
    if len(extract_courses(BeautifulSoup(html, "html.parser"), subject["subject_code"])) > 0:
        return html
    response = context.request.get(subject["api_url"], timeout=60_000)
    if response.ok:
        return response.text()
    raise RuntimeError(f"subject page/API failed: {subject['source_url']} ({response.status})")


def load_subjects() -> list[dict]:
    if not OUTPUT_PATH.exists():
        raise RuntimeError(f"Missing {OUTPUT_PATH}; run get_urls.py first")
    return json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))["subjects"]


def load_programs() -> list[dict]:
    if not OUTPUT_PATH.exists():
        raise RuntimeError(f"Missing {OUTPUT_PATH}; run get_urls.py first")
    return json.loads(OUTPUT_PATH.read_text(encoding="utf-8")).get("programs", [])


def extract_program(soup: BeautifulSoup, program: dict) -> dict:
    main = soup.select_one("#mainContent") or soup.find("main") or soup
    title_node = main.find(["h1", "h2"]) or soup.find("title")
    title = clean_text(title_node.get_text(" ") if title_node else program["name"])
    courses, requirements, groups, seen = [], [], {}, set()
    for anchor in main.find_all("a"):
        if "/course/" not in anchor.get("href", ""):
            continue
        code_node = anchor.select_one("small")
        raw = clean_text(anchor.get_text(" "))
        if code_node:
            code = clean_text(code_node.get_text(" "))
            title = raw[len(code):].strip(" -–:") if raw.upper().startswith(code.upper()) else raw
            course = {"code": code, "title": title, "units": "N/A"}
        else:
            course = parse_course_heading(raw, "")
        if not course:
            continue
        href = anchor.get("href", "").split("#", 1)[0]
        course.update({"source_url": urljoin("https://deanza.elumenapp.com/catalog/", href), "api_url": course_api_url(href), "description": "", "prerequisites": "", "corequisites": "", "advisories": ""})
        if course["code"] not in seen:
            courses.append(course)
            seen.add(course["code"])
        heading = anchor.find_previous(["h2", "h3", "h4", "h5", "h6"])
        requirement_name = clean_text(heading.get_text(" ")) if heading else "General Requirements"
        if requirement_name not in groups:
            groups[requirement_name] = {"name": requirement_name, "courses": [], "raw_text": requirement_name}
            requirements.append(groups[requirement_name])
        if course["code"] not in groups[requirement_name]["courses"]:
            groups[requirement_name]["courses"].append(course["code"])

    # Program pages list curriculum in tables rather than course links.
    # Preserve alternatives such as ``ACCT 1A / ACCT 1AH`` as separate course
    # records while keeping them in the same requirement group.
    for row in main.select("tr"):
        code_cell = row.select_one(".fix-code")
        title_cell = row.select_one(".course-name")
        if not code_cell or not title_cell:
            continue
        raw_codes = re.split(r"\s*/\s*", clean_text(code_cell.get_text(" ")))
        title = clean_text(title_cell.get_text(" "))
        units_node = row.select_one(".units")
        units = clean_text(units_node.get_text(" ") if units_node else "") or "N/A"
        table = row.find_parent("table")
        caption = table.select_one("caption") if table else None
        heading = row.find_previous(["h3", "h4"])
        requirement_name = clean_text(caption.get_text(" ")) if caption else (clean_text(heading.get_text(" ")) if heading else "Program Requirements")
        if requirement_name not in groups:
            groups[requirement_name] = {"name": requirement_name, "courses": [], "raw_text": requirement_name}
            requirements.append(groups[requirement_name])
        for raw_code in raw_codes:
            parsed = parse_course_heading(f"{raw_code} - {title}", "")
            if not parsed:
                continue
            parsed.update({"units": units, "description": "", "prerequisites": "", "corequisites": "", "advisories": ""})
            if parsed["code"] not in seen:
                courses.append(parsed)
                seen.add(parsed["code"])
            if parsed["code"] not in groups[requirement_name]["courses"]:
                groups[requirement_name]["courses"].append(parsed["code"])

    # Elumen API responses may contain the same curriculum as custom hidden
    # elements instead of visible table rows.
    for node in main.find_all("course"):
        code_node = node.find("course-code")
        title_node = node.find("course-name")
        if not code_node or not title_node:
            continue
        raw_code = clean_text(code_node.get_text(" ")).rstrip(".")
        encoded = re.match(r"^([A-Z/]+)D0*(\d+[A-Z]*)$", raw_code, re.I)
        code = f"{encoded.group(1).upper()} {encoded.group(2).upper()}" if encoded else raw_code
        parsed = parse_course_heading(f"{code} - {clean_text(title_node.get_text(' '))}", "")
        if not parsed or parsed["code"] in seen:
            continue
        units_node = node.find("units")
        parsed.update({
            "units": clean_text(units_node.get_text(" ")) if units_node else "N/A",
            "description": "", "prerequisites": "", "corequisites": "", "advisories": "",
        })
        courses.append(parsed)
        seen.add(parsed["code"])
        requirement_name = requirements[-1]["name"] if requirements else "Program Requirements"
        if requirement_name not in groups:
            groups[requirement_name] = {"name": requirement_name, "courses": [], "raw_text": requirement_name}
            requirements.append(groups[requirement_name])
        if parsed["code"] not in groups[requirement_name]["courses"]:
            groups[requirement_name]["courses"].append(parsed["code"])
    return {
        "schema_version": 1, "scraped_at": now_iso(), "id": program["id"], "name": program["name"],
        "title_on_page": title, "department": program.get("department", ""), "department_id": program.get("department_id", ""),
        "source_url": program["source_url"], "api_url": program["api_url"],
        "program_text": clean_text(main.get_text(" "))[:4000], "requirements": requirements, "courses": courses,
    }


def fetch_program_html(context: BrowserContext, page: Page, program: dict) -> str:
    # The browser-rendered page contains the curriculum tables. The API can
    # expose the surrounding program metadata without those rendered tables,
    # so use it only as a fallback.
    page.goto(program["source_url"], wait_until="domcontentloaded", timeout=90_000)
    try:
        page.wait_for_function(
            """() => document.querySelectorAll(
                "#mainContent table.program-group"
            ).length > 0""",
            timeout=30_000,
        )
    except Exception:
        pass
    html = page.content()
    if ("program-group" in html and "course-name" in html) or "<course-code>" in html:
        return html
    api_response = context.request.get(program["api_url"], timeout=60_000)
    if api_response.ok:
        api_html = api_response.text()
        if ("program-group" in api_html and "course-name" in api_html) or "<course-code>" in api_html:
            return api_html
    status = api_response.status if api_response else "unavailable"
    raise RuntimeError(f"program page/API failed: {program['source_url']} ({status})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--program", action="append", help="Program id or exact name; repeatable")
    parser.add_argument("--department", action="append", help="Department id, subject code, or exact name; repeatable")
    parser.add_argument("--all-programs", action="store_true", help="Scrape every discovered De Anza program")
    parser.add_argument("--all-departments", action="store_true", help="Scrape every discovered De Anza department")
    parser.add_argument("--force", action="store_true", help="Replace selected existing department files")
    args = parser.parse_args()
    subjects = load_subjects()
    programs = load_programs()
    if args.department:
        wanted = {item.lower() for item in args.department}
        subjects = [s for s in subjects if s["id"].lower() in wanted or s["subject_code"].lower() in wanted or s["name"].lower() in wanted]
        if not subjects:
            parser.error("no matching De Anza department")
    elif args.all_departments:
        subjects = subjects
    else:
        subjects = [] if (args.program or args.all_programs) else subjects

    if args.program:
        wanted = {item.lower() for item in args.program}
        programs = [p for p in programs if p["id"].lower() in wanted or p["name"].lower() in wanted]
        if not programs:
            parser.error("no matching De Anza program")
    elif args.all_programs:
        if not programs:
            parser.error("no De Anza programs found; run get_urls.py first")
    else:
        programs = [] if (args.department or args.all_departments) else programs
    output_dir = DATA_DIR / "departments"
    programs_dir = DATA_DIR / "programs"
    output_dir.mkdir(parents=True, exist_ok=True)
    programs_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"schema_version": 1, "scraped_at": now_iso(), "institution": "De Anza College", "departments": [], "programs": []}
    manifest_path = DATA_DIR / "manifest.json"
    if manifest_path.exists() and not args.force:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()
        for subject in subjects:
            path = output_dir / f"{subject['id']}.json"
            if path.exists() and not args.force:
                continue
            print(f"[{subject['subject_code']}] {subject['name']}")
            try:
                html = fetch_subject_html(context, page, subject)
                soup = BeautifulSoup(html, "html.parser")
                courses = extract_courses(soup, subject["subject_code"])
                for course in courses:
                    fetch_course_detail(context, course)
                result = {
                    "schema_version": 1, "scraped_at": now_iso(), "id": subject["id"],
                    "name": subject["name"], "subject_code": subject["subject_code"],
                    "title_on_page": clean_text((soup.find("h2") or soup.find("title")).get_text(" ")),
                    "source_url": subject["source_url"], "api_url": subject["api_url"],
                    "department_text": clean_text((soup.select_one("#mainContent") or soup).get_text(" "))[:4000],
                    "courses": courses, "programs": [],
                }
                path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                print(f"  scraped {len(courses)} courses")
            except Exception as error:
                print(f"  ERROR: {error}", file=sys.stderr)
            time.sleep(0.15)
        for program in programs:
            path = programs_dir / f"{program['id']}.json"
            if path.exists() and not args.force:
                continue
            print(f"[PROGRAM] {program['name']}")
            try:
                result = extract_program(BeautifulSoup(fetch_program_html(context, page, program), "html.parser"), program)
                path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                print(f"  scraped {len(result['courses'])} courses in {len(result['requirements'])} requirement groups")
            except Exception as error:
                print(f"  ERROR: {error}", file=sys.stderr)
            time.sleep(0.15)
        browser.close()
    records = []
    for path in sorted(output_dir.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        records.append({"id": record["id"], "name": record["name"], "subject_code": record["subject_code"], "source_url": record["source_url"], "file": f"departments/{path.name}", "course_count": len(record["courses"])})
    manifest.update({"scraped_at": now_iso(), "departments": records})
    program_records = []
    for path in sorted(programs_dir.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        program_records.append({"id": record["id"], "name": record["name"], "department": record.get("department", ""), "source_url": record["source_url"], "file": f"programs/{path.name}", "course_count": len(record["courses"]), "requirement_count": len(record["requirements"])})
    manifest["programs"] = program_records
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote manifest to {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
