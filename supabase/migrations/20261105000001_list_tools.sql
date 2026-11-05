-- Search, sort and favourites in lists (specs/016): each user's starred courses, and unaccent
-- so a search for "garcia" finds "García".

create extension if not exists unaccent with schema extensions;

create table public.course_favorites (
  user_id uuid not null references public.profiles (id) on delete cascade,
  course_id uuid not null references public.courses (id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (user_id, course_id)
);

alter table public.course_favorites enable row level security;
revoke all on table public.course_favorites from anon, authenticated;
