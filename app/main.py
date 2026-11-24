import flet as ft
from app.views.settings_view import SettingsView
from app.views.catalog_view import CatalogView
from app.views.planner_view import PlannerView
from app.views.program_view import ProgramView
from app.views.progress_view import ProgressView

def main(page: ft.Page):
    page.title = "Course Planner"
    page.padding = 0  
    page.window.maximized = True
    views = [
        PlannerView(),
        ProgressView(),
        ProgramView(),
        CatalogView(),
        SettingsView(),
    ]
    content_area = ft.Container(
        content=views[0],
        expand=True,
        padding=30,
        alignment=ft.Alignment.TOP_LEFT
    )
    def toggle_sidebar(e: ft.ControlEvent):
        rail.extended = not rail.extended
        page.update()
    def on_nav_change(e: ft.ControlEvent):
        selected = e.control.selected_index
        views[selected].refresh()
        content_area.content = views[selected]
        page.update()

    # Left Sidebar
    rail = ft.NavigationRail(
        selected_index=0,
        label_type=ft.NavigationRailLabelType.NONE,
        extended=True,                             
        min_width=40,
        min_extended_width=150,
        bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
        group_alignment=-0.9,
        leading=ft.IconButton(
            icon=ft.Icons.MENU,
            tooltip="Toggle Sidebar",
            on_click=toggle_sidebar,
        ),
        destinations=[
            ft.NavigationRailDestination(
                icon=ft.Icons.SPACE_DASHBOARD_OUTLINED,
                selected_icon=ft.Icons.SPACE_DASHBOARD,
                label="Planner",
            ),
            ft.NavigationRailDestination(
                icon=ft.Icons.BAR_CHART,
                selected_icon=ft.Icons.BAR_CHART,
                label="Your Progress",
            ),
            ft.NavigationRailDestination(
                icon=ft.Icons.BUSINESS,
                selected_icon=ft.Icons.BUSINESS,
                label="Your Program",
            ),
            ft.NavigationRailDestination(
                icon=ft.Icons.LIST_ALT,
                selected_icon=ft.Icons.LIST_ALT,
                label="Catalog",
            ),
            ft.NavigationRailDestination(
                icon=ft.Icons.SETTINGS_OUTLINED,
                selected_icon=ft.Icons.SETTINGS,
                label="Settings",
            ),
        ],
        on_change=on_nav_change,
    )

    page.add(
        ft.Row(
            controls=[
                rail,
                ft.VerticalDivider(width=1),
                content_area,
            ],
            expand=True,
            spacing=0,
        )
    )

if __name__ == "__main__":
    ft.run(main)
