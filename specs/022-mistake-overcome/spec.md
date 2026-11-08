# Feature Specification: Repeated Mistakes Overcome

**Feature Branch**: `022-mistake-overcome`

**Created**: 2026-11-08

**Status**: Draft

**Input**: Requirement **S5** (repeated error patterns, then targeted practice) and the KPI "fewer
recurring errors". Today a repeated mistake opens a notice, an explanation and practice, but
nothing ever says the student got past it: the pattern stays in the learning record and in the
next steps (spec 020) until it leaves the window. This feature closes the loop.

**Builds on**: [005](../005-repeated-mistakes/spec.md), [007](../007-progress/spec.md),
[015](../015-pedagogy-criteria/spec.md), [020](../020-next-steps/spec.md).
**Frontend**: `frontend/specs/022-mistake-overcome`.

## Decision (provisional)

- A mistake of a type in a topic is **overcome** once the student's next `overcome_after`
  assessed exercises in that topic (correct, partially correct or incorrect) are all correct.
  Any other result in the topic restarts the count; a new mistake of the type starts over.
- `overcome_after` (default **3**, 1–20) joins the `repeated_mistakes` criteria group (spec 015);
  course overrides saved before keep validating with the default.
- Quiz answers do not count: error types are only known for exercises.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — The student is told when they got past a repeated mistake (Priority: P1) 🎯

1. **Given** a repeated pattern (spec 005: 3 mistakes of a type in a topic within 30 days),
   **When** the student's third correct exercise in a row in that topic is assessed, **Then** its
   feedback carries `overcome: [{error_type, topic_name, count, correct}]`.
2. **Given** the second, or the fourth, correct exercise in a row, **Then** `overcome` is empty
   (it is said once).
3. **Given** a partially correct exercise in the topic in between, **Then** the count restarts.
4. **Given** mistakes that never reached the threshold, **Then** nothing is celebrated.

### User Story 2 — Progress shows how far each mistake is from overcome (Priority: P1)

1. **Given** a topic's frequent mistakes (spec 007 `top_errors`), **Then** each carries
   `correct_since` (correct exercises in a row in the topic after its latest occurrence) and
   `overcome` (`correct_since ≥ overcome_after`). The teacher sees the same.

### User Story 3 — Overcome patterns are not recommended (Priority: P1)

1. **Given** an overcome pattern, **Then** the next steps (spec 020) do not propose reviewing it;
   another repeated pattern that is not overcome may be proposed instead.

### User Story 4 — The threshold is a criterion (Priority: P2)

1. **Given** the study defaults, **Then** `repeated_mistakes` is `{count: 3, window_days: 30,
   overcome_after: 3}`; a course may set its own; values outside 1–20 give 422.

## Requirements *(mandatory)*

- **FR-001**: Migration adds `overcome_after: 3` to the stored `repeated_mistakes` groups.
- **FR-002**: `StudentSubmission.overcome`, `TopicError.correct_since` and `TopicError.overcome`.
- **FR-003**: Computed on read; no new table; no model call.

## Success Criteria *(mandatory)*

- **SC-001**: API tests cover every scenario; the full suite passes.
