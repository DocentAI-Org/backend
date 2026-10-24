-- Study consent as an append-only history (specs/002-consent-and-flags).

create table public.consent_events (
  id uuid primary key default gen_random_uuid(),
  student_id uuid not null references public.profiles (id) on delete cascade,
  action text not null check (action in ('given', 'revoked')),
  version text not null check (char_length(version) between 1 and 40),
  created_at timestamptz not null default clock_timestamp()
);
create index consent_events_student_idx on public.consent_events (student_id, created_at);

alter table public.consent_events enable row level security;
revoke all on table public.consent_events from anon, authenticated;
