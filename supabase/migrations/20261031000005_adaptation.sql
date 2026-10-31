-- Explanations adapted to the student (specs/013): the basis shown with each adapted answer,
-- {error_type, count, window_days}, stored so it does not change later.

alter table public.messages add column adaptation jsonb;
alter table public.exercise_submissions add column adaptation jsonb;
