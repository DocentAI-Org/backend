-- Targeted help for repeated mistakes (specs/005): one review per submission, grounded in the
-- material, with its own citations; review requests are logged as interactions.

create table public.mistake_reviews (
  id uuid primary key default gen_random_uuid(),
  submission_id uuid not null unique references public.exercise_submissions (id) on delete cascade,
  course_id uuid not null references public.courses (id) on delete cascade,
  student_id uuid not null references public.profiles (id) on delete cascade,
  error_type text not null,
  topic_name text,
  kind text not null check (kind in ('answer', 'no_source')),
  explanation text not null,
  worked_example text,
  practice text[] not null default '{}',
  created_at timestamptz not null default clock_timestamp()
);

alter table public.mistake_reviews enable row level security;
revoke all on table public.mistake_reviews from anon, authenticated;

alter table public.citations
  add column review_id uuid references public.mistake_reviews (id) on delete cascade;
create index citations_review_idx on public.citations (review_id);
alter table public.citations drop constraint citations_check;
alter table public.citations
  add constraint citations_check check (num_nonnulls(message_id, submission_id, review_id) = 1);

alter table public.interaction_logs drop constraint interaction_logs_kind_check;
alter table public.interaction_logs
  add constraint interaction_logs_kind_check check (kind in ('chat', 'exercise', 'review'));
