-- Security for the DocentAI API v1 (research R8, R9, R16).
-- The API is the only access path in v1: RLS is enabled on every table with no client
-- policies, and client roles have no privileges on application tables.

do $$
declare
  t text;
begin
  foreach t in array array[
    'profiles', 'courses', 'enrolments', 'tutor_settings', 'documents', 'fragments', 'topics',
    'topic_assignments', 'conversations', 'messages', 'exercise_submissions', 'citations',
    'learning_record_entries', 'teacher_flags', 'interaction_logs', 'daily_usage'
  ]
  loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on table public.%I from anon, authenticated', t);
  end loop;
end
$$;

-- Every new auth user gets a profile. The role is always 'student' here; only the API
-- promotes accounts (research R8). Role and status are never read from user metadata.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, display_name, email)
  values (
    new.id,
    coalesce(
      nullif(trim(new.raw_user_meta_data ->> 'display_name'), ''),
      split_part(coalesce(new.email, 'student'), '@', 1)
    ),
    new.email
  );
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- Private bucket for course material, served only through signed URLs.
insert into storage.buckets (id, name, public)
values ('course-material', 'course-material', false)
on conflict (id) do nothing;
