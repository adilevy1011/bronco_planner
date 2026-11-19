import flet as ft


class View(ft.Column):
    def __init__(self):
        super().__init__()
        self.expand = True
        self.scroll = ft.ScrollMode.AUTO

    def refresh(self):
        self.controls = self.build_controls()

    def build_controls(self):
        raise NotImplementedError
