# Tasks: Quizzes That Start From the Student's Mastery

**Spec**: [spec.md](spec.md)

- [x] T001 Tests first: the start level from mastery, no score, fixed, every topic; weak topics
  first; the quiz criteria group, its defaults, a course's length and streak, validation
  (`tests/api/test_adaptive_quiz_start.py`, `tests/api/test_pedagogy_criteria.py`)
- [x] T002 Migration, `QuizCriteria`, `StartBasis`, start and pick in `app/services/quizzes.py`;
  remove the `QUIZ_*` settings
- [x] T003 Contract note and `openapi.json`
