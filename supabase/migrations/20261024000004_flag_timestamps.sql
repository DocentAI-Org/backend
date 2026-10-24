-- Flags are listed newest first (specs/002). now() is the transaction start, so flags written in
-- one transaction tie; clock_timestamp() orders them by when each was written, like messages.
alter table public.teacher_flags alter column created_at set default clock_timestamp();
alter table public.teacher_flags alter column updated_at set default clock_timestamp();
