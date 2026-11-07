-- Keys for commercial models stored in the app (specs/019): the study's (course_id null),
-- offered to every course, and a teacher's own for one course. The key is encrypted with
-- LLM_CREDENTIALS_KEY (Fernet) by the API; only its last four characters are kept in clear.

create table public.llm_credentials (
  id uuid primary key default gen_random_uuid(),
  course_id uuid references public.courses (id) on delete cascade,
  provider text not null check (provider in ('openai', 'anthropic', 'openai_compatible')),
  label text not null,
  base_url text,
  encrypted_key text not null,
  key_hint text not null,
  -- The study's: the models courses may use; null is all of them.
  offered_models jsonb,
  created_by uuid references public.profiles (id) on delete set null,
  created_at timestamptz not null default now(),
  constraint llm_credentials_compatible_has_url
    check (provider <> 'openai_compatible' or base_url is not null)
);

alter table public.llm_credentials enable row level security;
revoke all on table public.llm_credentials from anon, authenticated;

-- Whether teachers may add their own keys (the study's row only), and the tasks that went
-- back to the inherited model because a key or model went away.
alter table public.ai_settings
  add column allow_teacher_keys boolean not null default false,
  add column notices jsonb not null default '[]';
