# Feature Specification: Adaptive Surfaces

**Feature Branch**: `023-adaptive-surfaces`

**Created**: 2026-11-08

**Status**: Draft

**Input**: Follow-ups of spec 022. The tutor's adaptation (S8, spec 013) still minds error types
the student has already overcome, and the student only meets the next steps (spec 020) on the
progress page. The frontend brings the next step to the course list and the chat and shows the
teacher the overcome notice; the backend part is the adaptation.

**Builds on**: [013](../013-adaptation/spec.md), [022](../022-mistake-overcome/spec.md).
**Frontend**: `frontend/specs/023-adaptive-surfaces`.

## Decision (provisional)

- The adaptation counts a student's mistakes of an error type in the window **leaving out the
  patterns (error type and topic) already overcome** (spec 022). An error type whose remaining
  mistakes do not reach the repeated threshold is not minded; a new mistake in a topic brings that
  pattern back.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — The tutor stops minding mistakes the student got past (Priority: P1) 🎯

1. **Given** 3 procedural mistakes in a topic followed by `overcome_after` correct exercises in
   it, **When** the student asks the tutor or sends an exercise, **Then** there is no adaptation
   and the model gets no note.
2. **Given** the same pattern overcome and another repeated error type that is not, **Then** the
   adaptation minds the other one.
3. **Given** an overcome pattern and enough mistakes of the type in another topic, **Then** only
   those count.
4. **Given** a new mistake in the overcome topic, **Then** the pattern counts again.

## Requirements *(mandatory)*

- **FR-001**: No contract change: `adaptation` keeps its shape; only its basis changes.
- **FR-002**: Computed on read; no new table; no model call.

## Success Criteria *(mandatory)*

- **SC-001**: API tests cover every scenario; the full suite passes.
