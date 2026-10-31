-- Answers without adaptation were stored as JSON null; make them SQL NULL (specs/013).
update public.messages set adaptation = null where adaptation = 'null'::jsonb;
update public.exercise_submissions set adaptation = null where adaptation = 'null'::jsonb;
