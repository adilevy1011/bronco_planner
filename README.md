# CPP Course Planner

CPP Course Planner is an academic planning prototype for Cal Poly Pomona students. It turns catalog and department information into a workspace where students can choose one or more programs, inspect their requirements, and build a term-by-term course roadmap.

## What it does

- Scrapes CPP program pages for requirement sections and course details.
- Scrapes department pages for the full department course inventory.
- Connects department courses back to the programs that use them.
- Supports planning across multiple programs at once.
- Tracks planned courses, units, requirement progress, and recommended next courses.
- Stores authenticated student roadmaps in Supabase Postgres with Row Level Security.
- Serves the planner as a static frontend with a FastAPI catalog/auth API behind it.

## Data model

Program records contain program metadata, stated degree units, requirement groups, and the courses listed on the program page. Department records contain every course listed by that department. A course can point back to every program that uses it, while a program stores the department course codes it references.

The planner intentionally keeps catalog alternatives separate from requirement targets. For example, a section containing a list of elective choices is represented as a choice pool, not as if every listed course were required.

## Authentication and privacy

Supabase handles account authentication and stores planner records. Supabase credentials are read only by the backend from its environment; they are never shipped to the browser. The frontend communicates with the backend through HttpOnly session cookies.

## Current scope

This is an early prototype focused on Computer Science and Mathematics catalog data from the CPP 2026–2027 catalog. The scraper output and requirement interpretation will continue to improve as more catalog rules are modeled, including prerequisites, course availability, transfer credit, GE requirements, and degree audits.
