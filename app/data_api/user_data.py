import os
import json
from pathlib import Path
from typing import Any, Dict, List
from app.data_api.app_data import get_institutions
class PlannerStorage:
    DEFAULT_STATE: Dict[str, Any] = {
        "schema_version": 1,
        "institution":[],
        "program": [],
        "terms": {},
        "preferences": {
            "collapsed_terms": []
        }
    }

    def __init__(self, app_folder_name: str = "BroncoCoursePlanner", filename: str = "user_plan.json"):
        app_data = os.getenv("FLET_APP_STORAGE_DATA") or os.getenv("LOCALAPPDATA") or Path.home()
        self.base_dir = Path(app_data) / app_folder_name
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        self.file_path = self.base_dir / filename
        self.data: Dict[str, Any] = self.load()

    def load(self) -> Dict[str, Any]:
        """Loads state from AppData and ensures all top-level keys exist."""
        if not self.file_path.exists():
            return json.loads(json.dumps(self.DEFAULT_STATE))

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            
            # Ensure top-level keys match DEFAULT_STATE without overwriting user data
            state = json.loads(json.dumps(self.DEFAULT_STATE))
            for key in state:
                if key in loaded and isinstance(loaded[key], type(state[key])):
                    state[key] = loaded[key]
            if not isinstance(state["preferences"].get("collapsed_terms"), list):
                state["preferences"]["collapsed_terms"] = []
            return state

        except (json.JSONDecodeError, OSError):
            return json.loads(json.dumps(self.DEFAULT_STATE))
    
    def save(self) -> None:
        """Atomically saves current state to disk."""
        temp_path = self.file_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
        os.replace(temp_path, self.file_path)

    def add_institution(self, institution_name):
        institutions = get_institutions()
        user_institutions = self.data['institution']
        if institution_name not in user_institutions and institution_name in institutions:
            user_institutions.append(institution_name)
            self.save()
    def remove_institution(self,institution_name):
        if institution_name in self.data['institution']:
            self.data['institutions'].remove(institution_name)
            self.save()
    def get_user_institutions(self):
        return self.load().get('institution')
    # --- Program Helpers ---
    def add_program(self, program_id: Any) -> None:
        if program_id not in self.data["program"]:
            program = program_id.replace(' ', '_').lower()
            self.data["program"].append(program)
            self.save()

    def remove_program(self, program_id: Any) -> None:
        if program_id in self.data["program"]:
            self.data["program"].remove(program_id)
            self.save()
    def get_user_programs(self):
        return [s.replace("_", " ").title() for s in (self.load().get('program'))]
    # --- Term Helpers ---
    def add_term(self, term_name: str) -> None:
        if term_name not in self.data["terms"]:
            self.data["terms"][term_name] = []
            self.save()
    def remove_term(self, term_name: str) -> None:
        if term_name in self.data["terms"]:
            del self.data["terms"][term_name]
            collapsed_terms = self.get_collapsed_terms()
            if term_name in collapsed_terms:
                collapsed_terms.remove(term_name)
                self.data["preferences"]["collapsed_terms"] = collapsed_terms
            self.save()

    def reorder_terms(self, ordered_terms: List[str]) -> None:
        """Persist the terms in the order provided.

        Term order is represented by the insertion order of the JSON object's
        keys. Require an exact permutation of the existing terms so callers
        cannot accidentally remove a term while reordering.
        """
        terms = self.data["terms"]
        if len(ordered_terms) != len(terms) or set(ordered_terms) != set(terms):
            raise ValueError("ordered_terms must contain every term exactly once")

        self.data["terms"] = {
            term_name: terms[term_name]
            for term_name in ordered_terms
        }
        self.save()
    
    def get_user_terms(self):
        return self.load().get('terms')
    def get_term_courses(self,term_name:str):
        return self.load().get('terms').get(term_name)
    def set_term_courses(self, term_name: str, courses: List[Any]) -> None:
        self.data["terms"][term_name] = courses
        self.save()
    def add_course(self,term_name,code):
        self.data["terms"][term_name].append(code)
        self.save()
    def remove_course(self,term_name,code):
        self.data['terms'][term_name].remove(code)
        self.save()
    def clear_term_courses(self,term_name):
        self.data['terms'][term_name].clear()
        self.save()

    def move_course(self, source_term: str, destination_term: str, course_code: str) -> None:
        """Move a planned course between terms and persist the change."""
        if source_term not in self.data["terms"]:
            raise KeyError(f"Unknown source term: {source_term}")
        if destination_term not in self.data["terms"]:
            raise KeyError(f"Unknown destination term: {destination_term}")
        if source_term == destination_term:
            return
        if course_code not in self.data["terms"][source_term]:
            raise ValueError(f"Course is not planned in {source_term}: {course_code}")
        if course_code in self.data["terms"][destination_term]:
            return

        self.data["terms"][source_term].remove(course_code)
        self.data["terms"][destination_term].append(course_code)
        self.save()

    # --- Preference Helpers ---
    def set_pref(self, key: str, value: Any) -> None:
        self.data["preferences"][key] = value
        self.save()

    def get_pref(self, key: str, default: Any = None) -> Any:
        return self.data["preferences"].get(key, default)

    def get_collapsed_terms(self) -> List[str]:
        """Return the terms that should open collapsed in the planner."""
        collapsed_terms = self.get_pref("collapsed_terms", [])
        return collapsed_terms if isinstance(collapsed_terms, list) else []

    def set_term_collapsed(self, term_name: str, collapsed: bool) -> None:
        """Persist one term's expansion state."""
        collapsed_terms = self.get_collapsed_terms()
        if collapsed and term_name not in collapsed_terms:
            collapsed_terms.append(term_name)
        elif not collapsed and term_name in collapsed_terms:
            collapsed_terms.remove(term_name)
        else:
            return

        self.data["preferences"]["collapsed_terms"] = collapsed_terms
        self.save()

if __name__=="__main__":
    storage = PlannerStorage()
    print(storage.load())
