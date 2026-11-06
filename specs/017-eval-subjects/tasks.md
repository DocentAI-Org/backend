# Tasks: Evaluation Across Subjects and Open-Model Comparison

**Spec**: [spec.md](spec.md)

## US1 — Corpus

- [ ] T001 `scripts/eval_corpus.py`: download the OpenStax PDFs, check SHA-256, cut the chapter
  pages into `tests/eval/corpus/.cache/` (git-ignored)
- [ ] T002 Corpus loader `tests/eval/corpus.py`: subjects, material bytes (Markdown, DOCX built
  from Markdown, cached PDF), skip with a message when not fetched; a classroom per subject with
  its topics assigned through the API
- [ ] T003 Material and `subject.json` for the five subjects; the spec 009 cases move to
  `matematicas`

## US2 — Measures

- [ ] T004 Retrieval: hit@k, MRR, queries over the threshold, by subject
- [ ] T005 Exercise feedback on every subject (the spec 009 runner, generalised)
- [ ] T006 Tutor: kind and citation accuracy
- [ ] T007 Quiz drafts: usable drafts and keys confirmed by the judge (`EVAL_JUDGE_MODEL`);
  disagreements listed
- [ ] T008 Results as JSON (`EVAL_OUT`) and median latency per call for every task

## US3 — Comparison

- [ ] T009 Tests first, then `reasoning_effort` for OpenAI-compatible providers when an effort
  is configured (FR-007)
- [ ] T010 `scripts/eval_models.py`: run the evaluation per model and write the comparison table
- [ ] T011 Baseline with `qwen2.5:7b` in `evaluation.md`
- [ ] T012 Comparison of the candidates; recommendation per task in `evaluation.md`

## US4 — Prompts

- [ ] T013 Prompt changes on the recommended model, kept only if they meet SC-003; before/after
  in `evaluation.md`

## Polish

- [ ] T014 README: how to fetch the corpus and run the evaluation and the comparison; full suite
