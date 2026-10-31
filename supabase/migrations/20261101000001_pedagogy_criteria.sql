-- Configurable pedagogical criteria (specs/015): the study defaults (course_id null) and each
-- course's overrides, per group; replaces risk_criteria and the REPEATED_MISTAKE_* and
-- PROGRESS_* settings, with the same values.

create table public.pedagogy_criteria (
  id uuid primary key default gen_random_uuid(),
  course_id uuid unique references public.courses (id) on delete cascade,
  inactive jsonb,
  error_rate jsonb,
  repeated_mistakes jsonb,
  adaptation jsonb,
  mastery jsonb,
  -- True until the educational stream agrees the defaults (requirements OQ3, OQ9, OQ12).
  provisional boolean not null default true,
  updated_at timestamptz not null default clock_timestamp(),
  updated_by uuid references public.profiles (id) on delete set null,
  constraint pedagogy_defaults_complete check (
    course_id is not null or (
      inactive is not null and error_rate is not null and repeated_mistakes is not null
      and adaptation is not null and mastery is not null
    )
  )
);
-- One row of study defaults.
create unique index pedagogy_criteria_one_default
  on public.pedagogy_criteria ((course_id is null)) where course_id is null;

alter table public.pedagogy_criteria enable row level security;
revoke all on table public.pedagogy_criteria from anon, authenticated;

insert into public.pedagogy_criteria
  (course_id, inactive, error_rate, repeated_mistakes, adaptation, mastery, provisional)
select
  null,
  jsonb_build_object('enabled', i.enabled, 'days', i.thresholds -> 'days'),
  jsonb_build_object(
    'enabled', e.enabled,
    'rate', e.thresholds -> 'rate',
    'min_exercises', e.thresholds -> 'min_exercises',
    'window_days', e.thresholds -> 'window_days'
  ),
  '{"count": 3, "window_days": 30}',
  '{"enabled": true}',
  '{"window": 10, "min_items": 3, "progressing": 0.5, "mastered": 0.8}',
  i.provisional or e.provisional
from public.risk_criteria i, public.risk_criteria e
where i.code = 'inactive' and e.code = 'error_rate';

drop table public.risk_criteria;
