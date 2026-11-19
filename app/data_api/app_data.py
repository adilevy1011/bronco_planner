import json
import os
import sys
from pathlib import Path

script_dir = Path(__file__).resolve().parent.parent

DATA_DIR = script_dir / ".." / "data" / "CalPolyPomona"
PROGRAMS_DIR = DATA_DIR / "programs"
DEPART_DIR = DATA_DIR / "departments"
GENERAL_EDUCATION_FILE = DATA_DIR / "general-education.json"

def get_programs():
    programs = [
        f.stem.replace("-", " ").title()
        for f in PROGRAMS_DIR.iterdir()
        if f.is_file() and f.suffix == ".json"
    ]
    return programs


def get_departments():
    programs = [
        f.stem.replace("-", " ").title()
        for f in DEPART_DIR.iterdir()
        if f.is_file() and f.suffix == ".json"
    ]
    return programs


def get_ge_areas():
    with GENERAL_EDUCATION_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)
    return data.get("requirements", [])

def get_all_courses():
    courses = []
    for file_path in DEPART_DIR.glob("*.json"):
        with file_path.open('r',encoding="utf-8") as file:
            data = json.load(file)
            course_list = data.get('courses')
            for course in course_list:
                courses.append(course)
    return courses

def search_courses(department: str = None,units: str = None ,course_code: str =None ,ge: str = None):
    course_list = get_all_courses()
    if department:
        normalized_department = department.replace(" ", "-").lower()
        file_name = normalized_department + '.json'
        with (DEPART_DIR / file_name).open('r', encoding="utf-8") as file:
            course_list = json.load(file).get('courses')
    if ge:
        course_list = [c for c in course_list if c.get('ge') == ge]
    if units:
        course_list = [c for c in course_list if str(c.get('units')) == str(units)]
    if course_code:
        return [c for c in course_list if c.get('code')==course_code]
    return course_list


if __name__=="__main__":
    print(search_courses(course_code='CS 1400'))
