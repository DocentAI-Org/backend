# Tasks: Stable Classification of Exercise Mistakes

**Spec**: [spec.md](spec.md)

- [x] T001 Evaluation: cases `tests/eval/feedback_cases.json`, runner `tests/eval/test_feedback_eval.py`
  (marker `eval`, excluded by default), report in `evaluation.md`; baseline run
- [x] T006 US3: exercise retrieval threshold (`RETRIEVAL_MIN_SIMILARITY_EXERCISES`, 0.40), test first
- [ ] T002 Tests first: topic per fragment, feedback temperature, prompt rules (unit and API)
- [ ] T003 Topic per fragment from confirmed assignments; feedback temperature setting
- [ ] T004 Prompt: how to pick the topic; decision rules between types
- [ ] T005 Re-run the evaluation; record before/after in `evaluation.md`
