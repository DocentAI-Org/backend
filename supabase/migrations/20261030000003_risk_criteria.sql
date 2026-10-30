-- Teacher dashboard (specs/004): the at-risk criteria as data, so the educational stream (and,
-- later, each teacher per course) can change the thresholds without a code change.

create table public.risk_criteria (
  code text primary key check (code ~ '^[a-z_]+$'),
  position integer not null unique,
  enabled boolean not null default true,
  thresholds jsonb not null,
  -- True until the educational stream agrees the criteria (requirements OQ12).
  provisional boolean not null default true
);

alter table public.risk_criteria enable row level security;
revoke all on table public.risk_criteria from anon, authenticated;

-- specs/004-teacher-dashboard/risk-criteria.md
insert into public.risk_criteria (code, position, thresholds) values
  ('inactive', 1, '{"days": 7}'),
  ('error_rate', 2, '{"window_days": 14, "min_exercises": 5, "rate": 0.6}');
