import os
import json
from pathlib import Path
from typing import Any, Dict, List

class PlannerStorage:
    DEFAULT_STATE: Dict[str, Any] = {
        "schema_version": 1,
        "program": [],
        "terms": {},
        "preferences": {}
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
            return state

        except (json.JSONDecodeError, OSError):
            return json.loads(json.dumps(self.DEFAULT_STATE))
    
    def save(self) -> None:
        """Atomically saves current state to disk."""
        temp_path = self.file_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
        os.replace(temp_path, self.file_path)

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
    # --- Preference Helpers ---
    def set_pref(self, key: str, value: Any) -> None:
        self.data["preferences"][key] = value
        self.save()

    def get_pref(self, key: str, default: Any = None) -> Any:
        return self.data["preferences"].get(key, default)

if __name__=="__main__":
    storage = PlannerStorage()
    storage.clear_term_courses('Fall 2025')
    print(storage.load())
        