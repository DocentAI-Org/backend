# Feature Specification: Stable Classification of Exercise Mistakes

**Feature Branch**: `009-feedback-classification`

**Created**: 2026-10-31

**Status**: Draft

**Input**: User description: "The same mistake gets a different error type and topic on each
submission; make the classification stable" (open point of specs 003 and 005).

**Builds on**: [003](../003-exercise-feedback/spec.md) (feedback, taxonomy) and the topic
assignments of [001](../001-api-v1-contract/spec.md) US6 (T9).

## Problem

Measured on the real stack (specs 003, 005): the "bracket not distributed" mistake is filed as
`procedural` or `execution`, under "Paréntesis" or "Despejar la incógnita". Repeated-mistake
patterns (spec 005) then need 7 submissions instead of 3, and the teacher dashboard (spec 004)
splits one mistake across topics.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — The team can measure classification (Priority: P1) 🎯

1. **Given** the local model, **When** the team runs `uv run pytest -m eval`, **Then** a fixed set
   of worked exercises on `ecuaciones.md` is graded several times each and a report gives
   verdict, type and topic accuracy and consistency across runs.
2. **Given** the normal test suite, **Then** the evaluation does not run (it needs a model).

### User Story 2 — The same mistake gets the same type and topic (Priority: P1)

1. **Given** a course whose sections are assigned to topics, **When** feedback is produced,
   **Then** each material fragment tells the model its topic, and the topic of the mistake is the
   one of the material that covers the wrong step.
2. **Given** a feedback request, **Then** the model is asked with temperature 0.
3. **Given** a mistake between two types, **Then** the prompt's decision rules (subject-
   independent) say which one applies.

## Requirements *(mandatory)*

- **FR-001**: The evaluation cases MUST be data (`tests/eval/feedback_cases.json`): statement,
  answer, accepted verdicts, accepted types and accepted topics (a case may accept more than one
  where the taxonomy is ambiguous).
- **FR-002**: `material_block` MUST be able to add the topic of each fragment from confirmed
  topic assignments (document, or document and section); the chat is unchanged.
- **FR-003**: The temperature for feedback MUST be configurable (`LLM_FEEDBACK_TEMPERATURE`,
  default 0); the chat keeps 0.2.
- **FR-004**: No API or database change.

## Success Criteria *(mandatory)*

- **SC-001**: On the evaluation set with `qwen2.5:7b`, 3 runs per case: topic accuracy ≥ 90 %,
  type accuracy ≥ 80 %, consistency (same type and topic in all runs of a case) ≥ 80 %, verdict
  accuracy not lower than the baseline.
- **SC-002**: The full test suite passes.

## Assumptions

- The cases are written by the technical team on the sample material; the educational stream's
  evaluation set (§4.4) replaces them when it exists.
