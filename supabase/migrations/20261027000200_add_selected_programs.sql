alter table public.planner_plans
  add column if not exists selected_programs jsonb not null default '[]'::jsonb;
