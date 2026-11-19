import flet as ft
from app.data_api.app_data import get_programs
from app.data_api.user_data import PlannerStorage
from app.views.view import View
class SettingsView(View):
    def __init__(self):
        super().__init__()
        self.storage = PlannerStorage()
        self.refresh()

    def on_select(self, e):
        programs = self.storage.get_user_programs()
        if e.control.value in get_programs() and e.control.value not in programs:
            self.storage.add_program(e.control.value)
        self.update()

    def build_controls(self):
        programs = self.storage.get_user_programs()
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
                on_select=self.on_select,
                editable=True,
                enable_search=True,
                enable_filter=True,
            ),
        ]
