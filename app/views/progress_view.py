import flet as ft
from app.data_api.user_data import PlannerStorage
from app.views.view import View
class ProgressView(View):
    def __init__(self):
        super().__init__()
        self.storage = PlannerStorage()
        self.refresh()

    def build_controls(self):
        return [
            ft.Text("Your Progress", size=28, weight=ft.FontWeight.BOLD),
        ]
