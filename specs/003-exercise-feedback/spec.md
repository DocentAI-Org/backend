# Feature Specification: Real Exercise Feedback with a Provisional Error Taxonomy

**Feature Branch**: `003-exercise-feedback`

**Created**: 2026-10-30

**Status**: Draft

**Input**: User description: "Replace the exercise feedback stub with real feedback; prepare a
provisional error taxonomy (no information from the educational stream yet)."

**Builds on**: [001 US7](../001-api-v1-contract/spec.md) (exercise submission, delivered as a
contract-honoring stub, FR-100) and requirement **S4** (`knowledge-base/docs/requirements.md`).
Taxonomy: [taxonomy.md](taxonomy.md).

## Clarifications

### Session 2026-10-30

- Q: Is there an agreed error taxonomy or a chosen pilot topic? → A: No. Use a provisional,
  subject-independent taxonomy, stored as data so the educational stream can change it.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — A student gets real feedback on a worked exercise (Priority: P1) 🎯

**Role**: Student · **Covers**: S4, S2, S3

The student submits a problem statement and their worked answer. The tutor compares it with the
course material and returns a verdict, where the first mistake is, its error type and course
topic, and an explanation grounded in the material with citations. When the material does not
cover the exercise, the tutor says so and does not judge it.

**Acceptance Scenarios**:

1. **Given** an enrolled student and material covering the exercise, **When** they submit an
   answer with a mistake, **Then** the feedback has verdict `incorrect` or `partially_correct`,
   the mistake location, an error type from the taxonomy, a topic of the course (or none if the
   course has no topics), an explanation and at least one citation; `is_stub` is false.
2. **Given** a correct answer, **When** it is submitted, **Then** the verdict is `correct`, there
   is no error type, and nothing is saved to the learning record.
3. **Given** an exercise the material does not cover, **When** it is submitted, **Then** the
   verdict is `not_assessed`, the explanation is the "not covered" notice, there are no citations
   and nothing is saved to the learning record; the model is not asked.
4. **Given** a course whose tutor only gives hints, **When** the feedback is produced, **Then** it
   explains the mistake without writing out the full solution.
5. **Given** a model reply that is unusable (no valid citation, unknown verdict), **When** it is
   received, **Then** the submission is stored as `not_assessed` with the "not covered" notice
   rather than unfounded feedback.
6. **Given** the model provider fails, **When** a student submits, **Then** they get
   `503 tutor_unavailable`, nothing is stored, and the daily allowance is not consumed.

### User Story 2 — Mistakes go to the learning record with type and topic (Priority: P1)

**Acceptance Scenarios**:

1. **Given** feedback with a mistake and a known error type, **When** it is produced, **Then** a
   learning-record entry with that type, the topic, the student, the course and the date is
   stored, and the feedback says it was saved.
2. **Given** a model reply with an error type that is not in the taxonomy, **When** it is
   received, **Then** the feedback is still returned without a type, nothing is saved to the
   record, and the interaction is logged as `unclassified`.

### User Story 3 — Anyone signed in can read the taxonomy (Priority: P1)

**Acceptance Scenarios**:

1. **Given** a signed-in user, **When** they list the error types, **Then** they get every type
   in order with its code, Spanish and English label and description, and whether the taxonomy is
   provisional.

### Edge Cases

- The model names a topic that is not one of the course's topics → no topic.
- The model cites fragments it was not given → those citations are dropped; with none left, see
  US1 AS5.
- A teacher deletes a topic later → the entry keeps its name and is shown as deleted (existing
  `topic_deleted`).

## Requirements *(mandatory)*

- **FR-001**: Feedback MUST come from the configured model, grounded only in the course's
  validated material retrieved for the statement and answer, with the same prompt-injection rules
  as the chat (material and student text are data, not instructions).
- **FR-002**: The model reply MUST be validated: verdict in the allowed set, citations only to
  fragments it was given, error type only from the taxonomy, topic only from the course's topics.
- **FR-003**: The verdict set MUST gain `not_assessed` (additive contract change).
- **FR-004**: The taxonomy MUST be stored as data (`error_types`: code, position, labels and
  descriptions in Spanish and English) and exposed read-only at `GET /v1/error-types`.
- **FR-005**: Feedback MUST respect the course's tutor settings (level, tone, solution policy).
- **FR-006**: Every submission MUST be logged like a chat interaction (model, tokens, latency,
  outcome = verdict, `unclassified` or `error`) and count toward the daily allowance, except when
  the provider fails.
- **FR-007**: No personal data MUST be sent to the model: only the statement, the answer, the
  material, the topic names and the taxonomy.

## Success Criteria *(mandatory)*

- **SC-001**: Every acceptance scenario has an API test with the fake model; the full suite
  passes.
- **SC-002**: Against the local Ollama model, the sample exercise with a known mistake (the
  `ecuaciones.md` fixture) gets an `incorrect` verdict with a citation and an error type.

## Assumptions

- The provisional taxonomy (taxonomy.md) is replaced by the educational stream's version through a
  migration; codes already stored stay valid as long as they are not removed.
- `is_stub` stays in the contract (always false now) so the frontend can drop it later.
