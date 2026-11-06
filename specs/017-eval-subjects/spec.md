# Feature Specification: Evaluation Across Subjects and Open-Model Comparison

**Feature Branch**: `017-eval-subjects`

**Created**: 2026-11-06

**Status**: In progress

**Input**: User description: "Compare open-source models of at most 7–8B (there are no OpenAI or
Anthropic keys yet) and iterate on models and prompts. The platform is not tied to one subject:
it must support maths, Spanish language, university subjects and so on."

**Builds on**: [009](../009-feedback-classification/spec.md) (evaluation set and runner) and
[014](../014-llm-providers/spec.md) (provider and model per task).

## Problem

The only evaluation (spec 009) grades exercise feedback on one maths file, `ecuaciones.md`
(linear equations, four sections). Choosing a model on it picks the best model for linear
equations, not for the platform. The other tasks the model does (tutor replies, quiz question
drafts) and retrieval are not measured at all, and the end-to-end review of 2026-10-31 found
wrong answer keys in 3 of 5 AI quiz drafts.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — A corpus that spans subjects and levels (Priority: P1) 🎯

| Subject | Level | Material | Format |
|---|---|---|---|
| Matemáticas: ecuaciones | ESO | `ecuaciones.md` (spec 009) | Markdown |
| Lengua castellana: la oración y la acentuación | ESO | written by the team | Markdown |
| Historia: la Revolución Industrial | ESO / bachillerato | written by the team | DOCX |
| Química: estequiometría | bachillerato / university | OpenStax *Química 2ed*, ch. 4 | PDF |
| Estadística descriptiva | university | OpenStax *Introducción a la estadística*, ch. 2 | PDF |

1. **Given** a fresh clone, **When** the team runs `uv run python scripts/eval_corpus.py`,
   **Then** the PDF materials are downloaded from OpenStax, checked against a pinned SHA-256,
   cut to the chapter pages and cached outside git.
2. **Given** a subject, **Then** its `subject.json` holds its topics (the sections each covers),
   and its cases for each task. The cases are data; adding a subject needs no code.
3. **Given** a subject whose material has not been fetched, **When** the evaluation runs,
   **Then** that subject is skipped with a message saying how to fetch it.

### User Story 2 — Every model task and retrieval are measured (Priority: P1)

1. **Retrieval**: each query names the sections that answer it; the report gives hit@k (an
   expected section among the `RETRIEVAL_TOP_K` hits), MRR and how many queries pass the
   similarity threshold. It does not need the chat model.
2. **Exercise feedback**: the spec 009 runner, on every subject: verdict, error type, topic,
   consistency.
3. **Tutor**: each question says what the tutor should do — `answer` (and from which sections),
   `hint` (an exercise, solution not requested, default `hints_first` policy) or `no_source`
   (outside the material). The report gives the kind accuracy and the citation accuracy.
4. **Quiz drafts**: drafts are generated for some topics; the report gives how many were usable
   (`validate_drafts`) and how many keys a judge model confirms by answering the question from
   the cited material without seeing the key. Disagreements are listed for a human to check.
5. **Given** any task, **Then** the report breaks the results down by subject and gives the
   median latency per call.

### User Story 3 — Candidate models are compared in one run (Priority: P1)

1. **Given** a list of Ollama models, **When** the team runs
   `uv run python scripts/eval_models.py qwen2.5:7b qwen3:8b ...`, **Then** each model is
   evaluated on every task and subject, its results are saved as JSON, and a Markdown table
   compares the models by task and subject.
2. **Given** a model that thinks before answering, **Then** the comparison can run it with
   thinking off and on (`LLM_EFFORT`), and says which.

### User Story 4 — Prompts are improved on the best candidates (Priority: P2)

1. **Given** the comparison, **When** a prompt changes, **Then** it is kept only if the
   evaluation improves on average and no subject gets worse; the before/after goes in
   `evaluation.md`.
2. **Given** a prompt, **Then** it has no rules for one particular subject.

## Requirements *(mandatory)*

- **FR-001**: The corpus MUST live in `tests/eval/corpus/<subject>/subject.json`; the material
  either next to it (Markdown, or Markdown turned into DOCX by the runner) or fetched by
  `scripts/eval_corpus.py` into `tests/eval/corpus/.cache/` (git-ignored).
- **FR-002**: Downloaded material MUST be checked against a pinned SHA-256 and keep its source,
  licence and attribution in `subject.json` (OpenStax books are CC BY 4.0).
- **FR-003**: Topics MUST name their sections explicitly (headings, or page ranges of the cut
  PDF); the runner assigns them with the topic-assignment API, as a teacher would.
- **FR-004**: The evaluation MUST stay outside the normal suite (`pytest -m eval`).
- **FR-005**: Each evaluation MUST be able to write its results as JSON (`EVAL_OUT`) for the
  comparison, and print a Markdown report.
- **FR-006**: The judge model for quiz keys MUST be configurable (`EVAL_JUDGE_MODEL`, default
  `qwen2.5:7b`) and is never the only evidence: its disagreements are listed for review.
- **FR-007**: For OpenAI-compatible providers, a configured effort MUST reach the model as
  `reasoning_effort` (Ollama thinking models), and no effort MUST keep today's request.
- **FR-008**: No API or database change.

## Success Criteria *(mandatory)*

- **SC-001**: The five subjects run on every task with `qwen2.5:7b` (baseline in
  `evaluation.md`).
- **SC-002**: At least five open models of at most 8B parameters are compared, with a
  recommendation of a model per task for local use and the gaps that remain.
- **SC-003**: Prompt changes kept under US4 improve the average of their task and lower no
  subject (within one case of noise), measured with the recommended model.
- **SC-004**: The full test suite passes.

## Assumptions

- The cases are written by the technical team; the educational stream's evaluation set (§4.4)
  replaces or extends them when it exists. Real teacher material would replace the open books.
- The machine is an M2 Pro with 16 GB, so candidates are at most 8B (quantised, Ollama).
- The judge is a small model too: its verdicts are an estimate, checked by hand on the listed
  disagreements.
- Parsing and retrieval improvements (e.g. formulas lost by `pypdf`, hybrid search, slides)
  are a later spec; this one measures them.
