-- Tags of one's own on courses (specs/016 US4): each teacher or student names and colours their
-- tags and puts them on the courses they teach or are in. Nobody sees anybody else's.

create table public.course_tags (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  name text not null check (char_length(btrim(name)) between 1 and 40),
  color text not null check (color in ('violet', 'green', 'blue', 'amber', 'red', 'gray')),
  created_at timestamptz not null default now()
);
create unique index course_tags_user_name on public.course_tags (user_id, lower(name));

create table public.course_tag_links (
  tag_id uuid not null references public.course_tags (id) on delete cascade,
  course_id uuid not null references public.courses (id) on delete cascade,
  primary key (tag_id, course_id)
);

alter table public.course_tags enable row level security;
alter table public.course_tag_links enable row level security;
revoke all on table public.course_tags from anon, authenticated;
revoke all on table public.course_tag_links from anon, authenticated;
