-- Quiz key check (specs/025): each AI draft solved without its key. `agrees`,
-- `disagrees` or `several`, with the options the check found right; null when not
-- checked (the check failed, or the teacher changed the options or the key).

alter table public.quiz_questions
  add column key_check text check (key_check in ('agrees', 'disagrees', 'several')),
  add column key_check_options smallint[];
