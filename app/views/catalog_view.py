import flet as ft
from app.views.view import View
from app.data_api.app_data import (
    get_course_details,
    get_departments,
    get_ge_areas,
    search_courses,
    get_last_updated
)


class CatalogView(View):
    def __init__(self):
        super().__init__()
        self.refresh()

    def build_controls(self):
        page_size = 50
        all_matches = []
        visible_count = 0

        def course_detail_controls(course_code):
            try:
                details = get_course_details(course_code)
            except (IndexError, KeyError, TypeError):
                return [
                    ft.Text(
                        "Course details are not available in the catalog.",
                        italic=True,
                    )
                ]

            detail_fields = [
                ("Description", details.get("description")),
                ("Prerequisites", details.get("prerequisites")),
                ("Grading", details.get("grading_basis")),
                ("Repeat for credit", details.get("repeat_for_credit")),
                ("When offered", details.get("when_offered")),
            ]
            controls = []
            for label, value in detail_fields:
                if value:
                    controls.append(
                        ft.Text(
                            spans=[
                                ft.TextSpan(
                                    f"{label}: ",
                                    style=ft.TextStyle(weight=ft.FontWeight.BOLD),
                                ),
                                ft.TextSpan(str(value)),
                            ],
                        )
                    )
            return controls or [
                ft.Text("No additional course details available.", italic=True)
            ]

        def render_results():
            result_controls = []
            for course in all_matches[:visible_count]:
                code = course.get("code", "")
                title = course.get("title", "")
                result_controls.append(
                    ft.ExpansionTile(
                        title=ft.Text(f"{code} - {title}"),
                        subtitle=ft.Text(
                            f"{course.get('units', '')} units"
                            + (
                                f" · {course.get('ge')}"
                                if course.get("ge")
                                else ""
                            )
                        ),
                        controls=course_detail_controls(code),
                        expanded_cross_axis_alignment=ft.CrossAxisAlignment.START,
                    )
                )

            if not result_controls:
                result_controls.append(ft.Text("No matching courses."))

            results_list.controls = result_controls
            load_more_button.visible = visible_count < len(all_matches)

        def search_button_handler(e):
            nonlocal all_matches, visible_count

            base_matches = search_courses(
                department=department_filter.value,
                units=units_filter.value,
                ge=ge_filter.value,
            )
            query = (course_search_tf.value or "").strip().lower()
            all_matches = [
                course
                for course in base_matches
                if not query
                or query in course.get("code", "").lower()
                or query in course.get("title", "").lower()
            ]
            visible_count = min(page_size, len(all_matches))
            render_results()
            results_list.update()
            load_more_button.update()
        def reset_search_button_handler():
            self.refresh()
        def load_more_handler(e):
            nonlocal visible_count
            visible_count = min(visible_count + page_size, len(all_matches))
            render_results()
            results_list.update()
            load_more_button.update()

        departments = get_departments()
        department_filter = ft.Dropdown(
            label="Department Filter",
            width=240,
            menu_height=300,
            options=[
                ft.DropdownOption(key=department, text=department)
                for department in departments
            ],
            editable=True,
            enable_search=True,
            enable_filter=True,
        )
        units_filter = ft.Dropdown(
            label="Units",
            width=120,
            options=[
                ft.DropdownOption(key=str(units), text=str(units))
                for units in ["1", "2", "3", "4", "5", "9"]
            ],
        )
        ge_filter = ft.Dropdown(
            label="GE area",
            width=240,
            menu_height=300,
            options=[
                ft.DropdownOption(
                    key=f"GE {area['id']}",
                    text=f"{area['id']} - {area['name'].split(' ', 1)[-1]}"
                )
                for area in get_ge_areas()
            ],
        )
        course_search_tf = ft.TextField(
            label="Search course code or title",
            expand=True,
            on_submit=search_button_handler,
        )
        results_list = ft.ListView(
            expand=True,
            spacing=0,
            auto_scroll=False,
        )
        load_more_button = ft.TextButton(
            "Load more",
            visible=False,
            on_click=load_more_handler,
        )
        render_results()

        return [
            ft.Text("Course Catalog", size=28, weight=ft.FontWeight.BOLD),
            ft.Text(f"Catalog last updated: {get_last_updated()}",size=11),
            ft.Row(controls=[course_search_tf]),
            ft.Row(controls=[department_filter, units_filter, ge_filter]),
            ft.Row(
                controls=[
                    ft.FilledButton("Search", on_click=search_button_handler),
                    ft.FilledButton("New search", on_click=reset_search_button_handler)
                ],
            ),
            results_list,
            load_more_button,
        ]
