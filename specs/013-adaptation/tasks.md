# Tasks: Explanations Adapted to the Student

**Spec**: [spec.md](spec.md)

- [x] T001 Tests first: focus thresholds, chat and exercise adaptation, null cases, teacher view
  (`tests/api/test_adaptation.py`)
- [x] T002 Migration, `Adaptation` schema, `app/services/adaptation.py`, prompt note
- [x] T003 Contract note and `openapi.json`
- [x] T004 Fix from the end-to-end review: the note goes among the prompt's rules, before the
  reply format (after it, `qwen2.5:3b` dropped "cited" and adapted exercises came back
  `not_assessed`); no adaptation is SQL NULL, not JSON null
