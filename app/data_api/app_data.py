import json
import os
import sys
from functools import lru_cache
from pathlib import Path
from datetime import datetime
script_dir = Path(__file__).resolve().parent.parent

DATA_DIR = script_dir / ".." / "data"
# temporary since CPP is the only one available so far
INSTITUTION_DATA_DIR = DATA_DIR / "CalPolyPomona" 
PROGRAMS_DIR = INSTITUTION_DATA_DIR / "programs"
DEPART_DIR = INSTITUTION_DATA_DIR / "departments"
GENERAL_EDUCATION_FILE = INSTITUTION_DATA_DIR / "general-education.json"

def load_manifest():
    MANIFEST_FILE = INSTITUTION_DATA_DIR / "manifest.json"
    with MANIFEST_FILE.open('r',encoding="utf-8") as file:
        data = json.load(file)
    return data

def get_last_updated():
    date_str = load_manifest().get("scraped_at")
    local_dt = datetime.fromisoformat(date_str)
    return f"{local_dt:%Y/%m/%d}"
def get_programs():
    programs = load_manifest().get('programs')
    return [item["name"] for item in programs]
    

def get_program(program_name: str):
    program_name = program_name.replace(" ", "-").lower()
    program_file_name = program_name + ".json"
    program_file = PROGRAMS_DIR / program_file_name
    try:
        with program_file.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return data.get("requirements")
    except:
        return None

def get_program_courses(program_name:str):
    program_name = program_name.replace(" ", "-").lower()
    program_file_name = program_name + ".json"
    program_file = PROGRAMS_DIR / program_file_name
    try:
        with program_file.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return data.get("courses")
    except:
        return None
def get_institutions():
    institutions = [item.name for item in DATA_DIR.iterdir() if item.is_dir()]
    return institutions
def get_departments():
    departments = load_manifest().get('departments')
    return [item["name"] for item in departments]


@lru_cache(maxsize=1)
def get_course_prefix_index():
    """Return a cached mapping of course-code prefixes to department names."""
    prefix_index = {}
    for department in load_manifest().get("departments", []):
        department_file = INSTITUTION_DATA_DIR / department["file"]
        with department_file.open("r", encoding="utf-8") as file:
            courses = json.load(file).get("courses", [])

        for course in courses:
            code = str(course.get("code", "")).strip()
            if code:
                prefix = code.split(maxsplit=1)[0].upper()
                prefix_index[prefix] = department["name"]

    return prefix_index


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

def search_courses(
    department: str = None,
    units: str = None,
    course_code: str = None,
    ge: str = None,
    course_prefix: str = None,
):
    if not department and course_code:
        course_prefix = str(course_code).strip().split(maxsplit=1)[0]
    if not department and course_prefix:
        department = get_course_prefix_index().get(
            str(course_prefix).strip().upper()
        )
    if department:
        normalized_department = department.replace(" ", "-").lower()
        file_name = normalized_department + '.json'
        with (DEPART_DIR / file_name).open('r', encoding="utf-8") as file:
            course_list = json.load(file).get('courses')
    else:
        course_list = get_all_courses()
    if ge:
        course_list = [c for c in course_list if c.get('ge') == ge]
    if units:
        course_list = [c for c in course_list if str(c.get('units')) == str(units)]
    if course_code:
        return [c for c in course_list if c.get('code')==course_code]
    return course_list

def get_course_details(course_code)->dict:
    """Returns a dict with course details organized like this:\n
    {
        'code': 'CS 1300',
        'title': 'Discrete Structures', 
        'units': '3', 
        'ge': None, 
        'coid': '436699', 
        'description': 'Logic, proof techniques, sets, basic counting rules, relations, functions and recursion. Graphs and trees.', 
        'prerequisites': 'CS major, CS minor, or Cyber Security minor; and eligibility for MAT 1140 or C or better in: MAT 1050 or MAT 1052 , and MAT 1060 ; MAT 1140 ; MAT 1150 ; or MAT 2140 .', 
        'grading_basis': 'Graded Only', 
        'repeat_for_credit': 'May be taken only once', 
        'when_offered': 'Fall, Spring, Summer'
    }
    """
    return search_courses(course_code=course_code)[0]

if __name__=="__main__":
    print(get_course_details(course_code="CS 1300"))
