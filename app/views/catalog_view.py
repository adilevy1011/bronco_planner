import flet as ft
from app.views.view import View
class CatalogView(View):
    def __init__(self):
        super().__init__()
        self.refresh()

    def build_controls(self):
        return [
            ft.Text("Course Catalog", size=28, weight=ft.FontWeight.BOLD),
        ]
