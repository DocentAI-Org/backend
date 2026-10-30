-- Real exercise feedback (specs/003): the error taxonomy as data, and a verdict for exercises the
-- course material does not cover.

create table public.error_types (
  code text primary key check (code ~ '^[a-z_]+$'),
  position integer not null unique,
  label_es text not null,
  label_en text not null,
  description_es text not null,
  description_en text not null,
  -- True until the educational stream replaces the draft (specs/003-exercise-feedback/taxonomy.md).
  provisional boolean not null default true
);

alter table public.error_types enable row level security;
revoke all on table public.error_types from anon, authenticated;

insert into public.error_types
  (code, position, label_es, label_en, description_es, description_en)
values
  ('comprehension', 1, 'Comprensión del enunciado', 'Understanding the task',
   'Interpreta mal lo que se pide, los datos o las condiciones del enunciado.',
   'Misreads what is asked, the data or the conditions of the task.'),
  ('conceptual', 2, 'Error conceptual', 'Conceptual error',
   'Entiende mal un concepto, una regla o una definición.',
   'Misunderstands a concept, rule or definition.'),
  ('procedural', 3, 'Error de procedimiento', 'Procedural error',
   'Conoce los conceptos pero aplica un método equivocado, se salta un paso o los hace en otro orden.',
   'Knows the concepts but applies a wrong method, skips a step or uses the wrong order.'),
  ('execution', 4, 'Error de ejecución', 'Slip',
   'Se equivoca al llevar a cabo un método correcto: cálculo, copia u ortografía.',
   'Makes a slip while carrying out a correct method: calculation, copying or spelling.'),
  ('incomplete', 5, 'Respuesta incompleta', 'Incomplete answer',
   'Se detiene antes del final o deja sin responder una parte de la tarea.',
   'Stops before the end or leaves part of the task unanswered.'),
  ('expression', 6, 'Expresión o notación', 'Expression or notation',
   'La idea es correcta pero está mal expresada, escrita o justificada (notación, unidades, registro).',
   'The idea is right but it is stated, written or justified poorly (notation, units, register).');

-- Learning-record entries written by the v1 stub keep their 'placeholder' type, so there is no
-- foreign key to error_types; the API only writes codes from the table.
alter table public.exercise_submissions drop constraint exercise_submissions_verdict_check;
alter table public.exercise_submissions add constraint exercise_submissions_verdict_check
  check (verdict in ('correct', 'partially_correct', 'incorrect', 'not_assessed'));
