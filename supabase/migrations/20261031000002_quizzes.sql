-- Quiz questions approved by the teacher and adaptive quizzes (specs/006).
-- Quiz items keep a snapshot of the question as the student saw it (FR-005).

create table public.quiz_questions (
  id uuid primary key default gen_random_uuid(),
  course_id uuid not null references public.courses (id) on delete cascade,
  topic_id uuid not null references public.topics (id) on delete cascade,
  statement text not null,
  options text[] not null check (cardinality(options) = 4),
  correct_option smallint not null check (correct_option between 0 and 3),
  explanation text not null,
  difficulty smallint not null check (difficulty between 1 and 3),
  status text not null default 'pending' check (status in ('pending', 'approved', 'rejected')),
  origin text not null default 'ai' check (origin in ('ai', 'edited')),
  reviewed_by uuid references public.profiles (id) on delete set null,
  reviewed_at timestamptz,
  created_at timestamptz not null default clock_timestamp()
);
create index quiz_questions_course_idx on public.quiz_questions (course_id, status, topic_id);

create table public.quizzes (
  id uuid primary key default gen_random_uuid(),
  course_id uuid not null references public.courses (id) on delete cascade,
  student_id uuid not null references public.profiles (id) on delete cascade,
  topic_id uuid references public.topics (id) on delete set null,
  topic_name text,
  status text not null default 'in_progress' check (status in ('in_progress', 'completed')),
  question_count smallint not null check (question_count > 0),
  level smallint not null check (level between 1 and 3),
  -- Consecutive right (> 0) or wrong (< 0) answers since the last level change.
  streak smallint not null default 0,
  started_at timestamptz not null default clock_timestamp(),
  completed_at timestamptz
);
create index quizzes_student_idx on public.quizzes (course_id, student_id, started_at);

create table public.quiz_items (
  id uuid primary key default gen_random_uuid(),
  quiz_id uuid not null references public.quizzes (id) on delete cascade,
  question_id uuid references public.quiz_questions (id) on delete set null,
  position smallint not null,
  topic_id uuid references public.topics (id) on delete set null,
  topic_name text not null,
  statement text not null,
  options text[] not null,
  correct_option smallint not null,
  explanation text not null,
  difficulty smallint not null,
  choice smallint check (choice between 0 and 3),
  correct boolean,
  answered_at timestamptz,
  unique (quiz_id, position)
);
create index quiz_items_question_idx on public.quiz_items (question_id);

do $$
declare
  t text;
begin
  foreach t in array array['quiz_questions', 'quizzes', 'quiz_items'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on table public.%I from anon, authenticated', t);
  end loop;
end
$$;

alter table public.citations
  add column question_id uuid references public.quiz_questions (id) on delete cascade;
create index citations_question_idx on public.citations (question_id);
alter table public.citations drop constraint citations_check;
alter table public.citations
  add constraint citations_check
  check (num_nonnulls(message_id, submission_id, review_id, question_id) = 1);

-- Generating questions is a teacher action: no student reference.
alter table public.interaction_logs alter column student_ref drop not null;
alter table public.interaction_logs drop constraint interaction_logs_kind_check;
alter table public.interaction_logs
  add constraint interaction_logs_kind_check
  check (kind in ('chat', 'exercise', 'review', 'quiz_generation'));
alter table public.interaction_logs
  add constraint interaction_logs_student_ref_check
  check ((student_ref is null) = (kind = 'quiz_generation'));
