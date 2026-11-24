import flet as ft
from app.views.view import View
from app.data_api.user_data import PlannerStorage
from app.data_api.app_data import (
    get_course_details,
    get_departments,
    get_ge_areas,
    search_courses,
)
class PlannerView(View):
    def __init__(self):
        super().__init__()
        # Keep scrolling inside the ReorderableListView so its built-in drag
        # auto-scroller has a bounded viewport to work with.
        self.scroll = None
        self.storage = PlannerStorage()
        self.refresh()
    
    def build_controls(self):
        def add_term_button_handler():
            terms = self.storage.get_user_terms()
            if term_name_field.value != '' and term_name_field.value not in terms:
                self.storage.add_term(term_name_field.value)
            self.refresh()
        def add_course(term_name:str,course_code: str):
            self.storage.add_course(term_name,course_code)
             
        def add_course_button_handler(selected_term):
            page_size = 50
            all_matches = []
            visible_count = 0
            selected_courses = []

            def select_course(course_code):
                if course_code in selected_courses:
                    selected_courses.remove(course_code)
                else:
                    selected_courses.append(course_code)
                render_results()
                render_selected_courses()
                results_list.update()
                selected_courses_list.update()

            def render_selected_courses():
                if not selected_courses:
                    selected_courses_list.controls = [
                        ft.Text("No courses selected yet.", italic=True)
                    ]
                else:
                    selected_courses_list.controls = [
                        ft.Text(course_code)
                        for course_code in selected_courses
                    ]

            def render_results():
                result_controls = []
                for course in all_matches[:visible_count]:
                    code = course.get("code", "")
                    title = course.get("title", "")
                    result_controls.append(
                        ft.ListTile(
                            leading=ft.Icon(
                                ft.Icons.CHECK
                                if code in selected_courses
                                else ft.Icons.CIRCLE_OUTLINED
                            ),
                            title=ft.Text(f"{code} - {title}"),
                            subtitle=ft.Text(f"{course.get('units', '')} units"),
                            on_click=lambda e, code=code: select_course(code),
                        )
                    )

                if not result_controls:
                    result_controls.append(ft.Text("No matching courses."))

                results_list.controls = result_controls
                load_more_button.visible = visible_count < len(all_matches)

            def search_button_handler(e):
                nonlocal all_matches, visible_count

                query = (course_search_tf.value or "").strip().lower()
                course_prefix = query.split(maxsplit=1)[0] if query else None
                base_matches = search_courses(
                    department=department_filter.value,
                    units=units_filter.value,
                    ge=ge_filter.value,
                    course_prefix=course_prefix,
                )
                all_matches = [
                    course for course in base_matches
                    if not query
                    or query in course.get("code", "").lower()
                    or query in course.get("title", "").lower()
                ]
                visible_count = min(page_size, len(all_matches))
                render_results()
                results_list.update()
                load_more_button.update()

            def load_more_handler(e):
                nonlocal visible_count
                visible_count = min(visible_count + page_size, len(all_matches))
                render_results()
                results_list.update()
                load_more_button.update()

            def submit_course(e):
                if not term_name_dd.value or not selected_courses:
                    return

                for course_code in selected_courses:
                    add_course(term_name_dd.value, course_code)
                self.page.pop_dialog()
                self.refresh()
                self.page.update()
            terms_dd_options = self.storage.get_user_terms()
            term_name_dd = ft.Dropdown(
                label="Select a term",
                value=selected_term,
                width=240,
                menu_height=300,
                options=[
                    ft.DropdownOption(key=term, text=term)
                    for term in terms_dd_options
                ],
                editable=True,
                enable_search=True,
                enable_filter=True,
            )
            departments = get_departments()
            department_filter = ft.Dropdown(
                label='Department Filter',
                width=240,
                menu_height=300,
                options=[
                    ft.DropdownOption(key=depart, text=depart)
                    for depart in departments
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
            )
            selected_courses_list = ft.Column(
                spacing=2,
                scroll=ft.ScrollMode.AUTO,
            )
            results_list = ft.ListView(
                height=180,
                spacing=0,
                auto_scroll=False,
            )
            load_more_button = ft.TextButton(
                "Load more",
                visible=False,
                on_click=load_more_handler,
            )
            selected_courses_heading = ft.Text(
                "Selected Courses",
                weight=ft.FontWeight.BOLD,
            )
            render_selected_courses()
            render_results()

            popup_dialog = ft.AlertDialog(
                modal=True,
                title=ft.Row(
                    controls=[
                        ft.Text("Add a course", weight=ft.FontWeight.BOLD, size=18),
                        ft.IconButton(ft.Icons.CLOSE, on_click=lambda e: self.page.pop_dialog()),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                content=ft.Container(
                    width=900,
                    height=600,
                    content=ft.Column(
                        controls=[
                            term_name_dd,
                            course_search_tf,
                            ft.Row(controls=[department_filter, units_filter]),
                            ge_filter,
                            ft.Row(
                                controls=[
                                    ft.FilledButton("Search", on_click=search_button_handler),
                                ],
                            ),
                            results_list,
                            selected_courses_heading,
                            selected_courses_list,
                            load_more_button,
                        ],
                        spacing=15,
                        scroll=ft.ScrollMode.AUTO,
                    ),
                ),
                actions=[
                    ft.TextButton("Cancel", on_click=lambda e: self.page.pop_dialog()),
                    ft.FilledButton("Add", on_click=submit_course),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            self.page.show_dialog(popup_dialog)
        
        term_name_field = ft.TextField(label="Term name")
        terms = self.storage.get_user_terms()
        collapsed_terms = set(self.storage.get_collapsed_terms())
        term_order = list(terms)
        term_items = []
        term_controls = {}

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
                ("Units", details.get('units')),
                ("GE", details.get("ge")),
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
            return controls or [ft.Text("No additional course details available.", italic=True)]

        def remove_course(term_name, course_code):
            self.storage.remove_course(term_name, course_code)
            self.refresh()
            self.page.update()

        def remove_term(term_name):
            self.storage.remove_term(term_name)
            self.refresh()
            self.page.update()

        def move_course_between_terms(e, destination_term):
            course_data = e.src.data
            if not isinstance(course_data, dict):
                return

            source_term = course_data.get("term")
            course_code = course_data.get("course")
            if not source_term or not course_code:
                return

            self.storage.move_course(source_term, destination_term, course_code)
            self.refresh()
            self.page.update()

        def term_expansion_changed(e, term_name):
            is_expanded = (
                e.data is True
                or str(e.data).lower() == "true"
            )
            self.storage.set_term_collapsed(term_name, not is_expanded)

        for term_name, courses in terms.items():
            courses = sorted(courses)
            term_unit_count = 0
            course_controls = []
            for course in courses:
                course_code = str(course)
                course_title = get_course_details(course_code).get("title")
                course_tile = ft.ExpansionTile(
                    leading=ft.IconButton(
                        icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
                        tooltip="Remove course",
                        on_click=lambda e, term=term_name, code=course_code: remove_course(term, code),
                    ),
                    title=ft.Text(f"{course_code} - {course_title}"),
                    controls=course_detail_controls(course_code),
                    expanded_cross_axis_alignment=ft.CrossAxisAlignment.START,
                )
                course_controls.append(
                    ft.Draggable(
                        group="planned_courses",
                        data={"term": term_name, "course": course_code},
                        axis=ft.Axis.VERTICAL,
                        affinity=ft.Axis.VERTICAL,
                        content=course_tile,
                        content_feedback=ft.Container(
                            width=520,
                            bgcolor=ft.Colors.SURFACE_CONTAINER,
                            border_radius=8,
                            padding=ft.Padding.symmetric(horizontal=16, vertical=10),
                            content=ft.Row(
                                controls=[
                                    ft.Icon(
                                        ft.Icons.DRAG_HANDLE,
                                        size=22,
                                    ),
                                    ft.Text(
                                        f"{course_code} - {course_title}",
                                        size=18,
                                    ),
                                ],
                                spacing=10,
                            ),
                        ),
                    )
                )
            for course in courses:
                course_units = get_course_details(str(course)).get('units')
                try:
                    term_unit_count += float(course_units)
                except:
                    continue

                
            if not course_controls:
                course_controls = [
                    ft.ListTile(
                        title = ft.Text("No courses planned")
                    )
                ]
            course_controls.append(
                    ft.ListTile(
                        leading=ft.Icon(ft.Icons.ADD),
                        title=ft.Text("Add course"),
                        on_click=lambda e, term=term_name: add_course_button_handler(term),
                    )
            )
            
            term_tile = ft.ExpansionTile(
                leading=ft.ReorderableDragHandle(
                    content=ft.Icon(ft.Icons.DRAG_HANDLE),
                    mouse_cursor=ft.MouseCursor.GRAB,
                ),
                title=ft.Text(f"{term_name} ({term_unit_count})", style=ft.TextStyle(weight=ft.FontWeight.BOLD), size=20),
                controls=course_controls,
                expanded=term_name not in collapsed_terms,
                on_change=lambda e, term=term_name: term_expansion_changed(e, term),
            )
            term_context_menu = ft.ContextMenu(
                content=term_tile,
                secondary_items=[
                    ft.PopupMenuItem(
                        content="Remove term",
                        icon=ft.Icons.DELETE_OUTLINE,
                        on_click=lambda e, term=term_name: remove_term(term),
                    ),
                ],
            )
            term_controls[term_name] = ft.DragTarget(
                group="planned_courses",
                content=term_context_menu,
                on_accept=lambda e, term=term_name: move_course_between_terms(e, term),
            )
            term_items.append(term_controls[term_name])

        def reorder_terms(e: ft.OnReorderEvent):
            if e.old_index is None or e.new_index is None:
                return

            moved_term = term_order.pop(e.old_index)
            term_order.insert(e.new_index, moved_term)
            self.storage.reorder_terms(term_order)

            # ReorderableListView does not reorder its controls automatically.
            e.control.controls = [term_controls[term] for term in term_order]
            e.control.update()

        return [
            ft.Row(
                controls=[
                    ft.Text("Course Planner", size=28, weight=ft.FontWeight.BOLD),
                    ft.Container(expand=True),
                    term_name_field,
                    ft.Button(
                        content=ft.Text("+ Add term"),
                        on_click=add_term_button_handler,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            ft.ReorderableListView(
                controls=term_items,
                expand=True,
                spacing=8,
                show_default_drag_handles=False,
                auto_scroller_velocity_scalar=20,
                on_reorder=reorder_terms,
            ),
        ]
