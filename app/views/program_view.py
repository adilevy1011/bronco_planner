import flet as ft
from app.data_api.user_data import PlannerStorage
from app.views.view import View
class ProgramView(View):
    def __init__(self):
        super().__init__()
        self.storage = PlannerStorage()
        self.refresh()

    def build_controls(self):
        programs = self.storage.get_user_programs()
        return [
            ft.Text("Your Program", size=28, weight=ft.FontWeight.BOLD),
            ft.ListView(
                expand=True,
                padding=20,
                spacing=10,
                controls=[
                    ft.Text(program, size=20) for program in programs
                ],
            ),
        ]
