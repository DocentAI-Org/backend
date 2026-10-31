-- Pre-test and post-test (specs/008): one test per course, taken once per phase by each student.

create table public.test_questions (
  id uuid primary key default gen_random_uuid(),
  course_id uuid not null references public.courses (id) on delete cascade,
  topic_id uuid references public.topics (id) on delete set null,
  topic_name text not null,
  position integer not null,
  statement text not null,
  options text[] not null check (cardinality(options) = 4),
  correct_option smallint not null check (correct_option between 0 and 3),
  created_at timestamptz not null default clock_timestamp()
);
create index test_questions_course_idx on public.test_questions (course_id, position);

create table public.test_phases (
  course_id uuid not null references public.courses (id) on delete cascade,
  phase text not null check (phase in ('pre', 'post')),
  status text not null default 'not_open' check (status in ('not_open', 'open', 'closed')),
  opened_at timestamptz,
  closed_at timestamptz,
  primary key (course_id, phase)
);

create table public.test_attempts (
  id uuid primary key default gen_random_uuid(),
  course_id uuid not null references public.courses (id) on delete cascade,
  student_id uuid not null references public.profiles (id) on delete cascade,
  phase text not null check (phase in ('pre', 'post')),
  submitted_at timestamptz not null default clock_timestamp(),
  unique (course_id, student_id, phase)
);

create table public.test_answers (
  attempt_id uuid not null references public.test_attempts (id) on delete cascade,
  question_id uuid not null references public.test_questions (id) on delete cascade,
  choice smallint not null check (choice between 0 and 3),
  correct boolean not null,
  primary key (attempt_id, question_id)
);

do $$
declare
  t text;
begin
  foreach t in array array['test_questions', 'test_phases', 'test_attempts', 'test_answers'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on table public.%I from anon, authenticated', t);
  end loop;
end
$$;
