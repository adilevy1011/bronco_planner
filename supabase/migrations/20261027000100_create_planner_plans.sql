create table if not exists public.planner_plans (
  user_id uuid primary key references auth.users(id) on delete cascade,
  terms jsonb not null default '[]'::jsonb,
  updated_at timestamptz not null default now()
);

alter table public.planner_plans enable row level security;

create policy "Users can read their own planner"
  on public.planner_plans for select
  using (auth.uid() = user_id);

create policy "Users can create their own planner"
  on public.planner_plans for insert
  with check (auth.uid() = user_id);

create policy "Users can update their own planner"
  on public.planner_plans for update
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create or replace function public.touch_planner_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists planner_plans_updated_at on public.planner_plans;
create trigger planner_plans_updated_at
before update on public.planner_plans
for each row execute function public.touch_planner_updated_at();
