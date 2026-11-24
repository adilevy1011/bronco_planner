import flet as ft
from app.data_api.app_data import get_programs, get_institutions
from app.data_api.user_data import PlannerStorage
from app.views.view import View
class SettingsView(View):
    def __init__(self):
        super().__init__()
        self.storage = PlannerStorage()
        self.refresh()

    def on_select_program(self, e):
        programs = self.storage.get_user_programs()
        if e.control.value in get_programs() and e.control.value not in programs:
            self.storage.add_program(e.control.value)
        self.update()
    def on_select_institution(self,e):
        institutions = self.storage.get_user_institutions()
        if e.control.value in get_institutions() and e.control.value not in institutions:
            self.storage.add_institution(e.control.value)
        self.update()

    def build_controls(self):
        programs = self.storage.get_user_programs()
        institutions = self.storage.get_user_institutions()
        return [
            ft.Text("Settings", size=28, weight=ft.FontWeight.BOLD),
            ft.Dropdown(
                label="Add a program",
                width=240,
                menu_height=300,
                options=[
                    ft.DropdownOption(key=program, text=program)
                    for program in get_programs() 
                    if program not in programs
                ],
                on_select=self.on_select_program,
                editable=True,
                enable_search=True,
                enable_filter=True,
            ),
            ft.Dropdown(
                label="Add an institution",
                width=240,
                menu_height=300,
                options=[
                    ft.DropdownOption(key=insti, text=insti)
                    for insti in get_institutions() 
                    if insti not in institutions
                ],
                on_select=self.on_select_institution,
                editable=True,
                enable_search=True,
                enable_filter=True,
            ),
        ]
