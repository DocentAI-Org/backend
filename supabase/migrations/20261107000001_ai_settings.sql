-- AI settings per course (specs/019): the study's values (course_id null) and each
-- course's, per group; a null group inherits (course -> study -> the server's env).
-- `models` holds one entry per task that has its own model.

create table public.ai_settings (
  id uuid primary key default gen_random_uuid(),
  course_id uuid unique references public.courses (id) on delete cascade,
  models jsonb not null default '{}',
  limits jsonb,
  retrieval jsonb,
  -- Messages per student and day across all courses: the study's only.
  ceiling jsonb,
  updated_at timestamptz not null default clock_timestamp(),
  updated_by uuid references public.profiles (id) on delete set null,
  constraint ai_settings_ceiling_is_the_studys check (course_id is null or ceiling is null)
);
create unique index ai_settings_one_study_row
  on public.ai_settings ((course_id is null)) where course_id is null;

insert into public.ai_settings (course_id) values (null);

-- Messages a student used in a course, per period: `day` and `week` start on their
-- first day, `course` on 1970-01-01. The daily ceiling keeps using daily_usage.
create table public.course_usage (
  student_id uuid not null references public.profiles (id) on delete cascade,
  course_id uuid not null references public.courses (id) on delete cascade,
  period text not null check (period in ('day', 'week', 'course')),
  period_start date not null,
  used integer not null default 0 check (used >= 0),
  primary key (student_id, course_id, period, period_start)
);

alter table public.ai_settings enable row level security;
alter table public.course_usage enable row level security;
revoke all on table public.ai_settings from anon, authenticated;
revoke all on table public.course_usage from anon, authenticated;
