-- The teacher's instructions per task (specs/019), a group like the others, and the test
-- messages teachers send to try their settings (counted for the limit of 20 an hour; they are
-- not student interactions).

alter table public.ai_settings add column instructions jsonb;

create table public.ai_tests (
  id uuid primary key default gen_random_uuid(),
  course_id uuid not null references public.courses (id) on delete cascade,
  teacher_id uuid not null references public.profiles (id) on delete cascade,
  task text not null,
  model text,
  created_at timestamptz not null default now()
);
create index ai_tests_by_teacher on public.ai_tests (teacher_id, created_at);

alter table public.ai_tests enable row level security;
revoke all on table public.ai_tests from anon, authenticated;
