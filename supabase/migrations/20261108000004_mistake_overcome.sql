-- Repeated mistakes overcome (specs/022): the correct exercises in a row that overcome a
-- mistake join the repeated_mistakes criteria group, default 3, in every stored group.

update public.pedagogy_criteria
set repeated_mistakes = repeated_mistakes || '{"overcome_after": 3}'
where repeated_mistakes is not null and not repeated_mistakes ? 'overcome_after';
