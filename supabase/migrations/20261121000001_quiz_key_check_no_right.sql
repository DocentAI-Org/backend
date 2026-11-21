-- Quiz key check (specs/025): `no_right` when the check finds no right option, added after
-- the review of 2026-11-21.

alter table public.quiz_questions drop constraint quiz_questions_key_check_check;
alter table public.quiz_questions
  add constraint quiz_questions_key_check_check
  check (key_check in ('agrees', 'disagrees', 'several', 'no_right'));
