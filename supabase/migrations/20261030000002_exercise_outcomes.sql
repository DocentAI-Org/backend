-- Exercise interactions are logged with their verdict, or 'unclassified' when the model's error
-- type is not in the taxonomy (specs/003 FR-006). 'stub' stays for the v1 rows.
alter table public.interaction_logs drop constraint interaction_logs_outcome_check;
alter table public.interaction_logs add constraint interaction_logs_outcome_check
  check (outcome in (
    'answer', 'hint', 'no_source', 'error', 'stub',
    'correct', 'partially_correct', 'incorrect', 'not_assessed', 'unclassified'
  ));
