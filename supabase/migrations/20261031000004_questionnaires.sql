-- Study questionnaires (specs/012): links to an external tool, open or closed, per audience.

create table public.questionnaires (
  id uuid primary key default gen_random_uuid(),
  title text not null check (length(btrim(title)) between 1 and 200),
  url text not null check (url like 'https://%'),
  audience text not null check (audience in ('student', 'teacher')),
  status text not null default 'open' check (status in ('open', 'closed')),
  created_at timestamptz not null default clock_timestamp(),
  updated_at timestamptz not null default clock_timestamp()
);
create index questionnaires_audience_idx on public.questionnaires (audience, status);

alter table public.questionnaires enable row level security;
revoke all on table public.questionnaires from anon, authenticated;
