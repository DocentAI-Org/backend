-- Quizzes that start from the student's mastery (specs/021): the quiz settings become a criteria
-- group (replacing QUIZ_LENGTH, QUIZ_STREAK and QUIZ_START_LEVEL, same values), and each quiz
-- keeps why it started where it did.

alter table public.pedagogy_criteria add column quiz jsonb;

update public.pedagogy_criteria
set quiz = '{"length": 5, "streak": 2, "start_level": 2, "adaptive": true}'
where course_id is null;

alter table public.pedagogy_criteria drop constraint pedagogy_defaults_complete;
alter table public.pedagogy_criteria add constraint pedagogy_defaults_complete check (
  course_id is not null or (
    inactive is not null and error_rate is not null and repeated_mistakes is not null
    and adaptation is not null and mastery is not null and quiz is not null
  )
);

-- Null for quizzes started before.
alter table public.quizzes add column start_basis jsonb;
