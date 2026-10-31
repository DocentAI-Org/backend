# Feature Specification: Study Questionnaires

**Feature Branch**: `012-questionnaires`

**Created**: 2026-10-31

**Status**: Draft

**Input**: Requirement **P4** "Satisfaction, usefulness and trust questionnaires (an external tool
such as Tally is fine)"; the KPIs also need a teacher survey (requirements §5, "lower teacher
workload"). The questionnaires live in the external tool; DocentAI only says which are open and
links to them.

**Builds on**: [011](../011-study-export/spec.md) for `study_ref` (merge 011 first).
**Frontend**: `frontend/specs/013-questionnaires`.

## Decisions (provisional, for the study team and the Data Protection Officer)

- The admin (study team) manages the list; teachers do not.
- A questionnaire is for students or for teachers, and is open or closed.
- Students see student questionnaires only while their study consent is given.
- If the link contains `{study_ref}`, a student's link has it replaced by their pseudonymous
  export code, so answers can be joined with the export without telling the external tool who
  they are; for teachers it is removed. Whether to use it is the study team's decision.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — The study team publishes a questionnaire (Priority: P1) 🎯

1. **Given** an admin, **When** they add a title, an `https` link and the audience, **Then** it is
   listed as open.
2. **Given** a questionnaire, **When** the admin closes, reopens, renames or deletes it, **Then**
   the list shows the change.
3. **Given** a link that is not `https`, **Then** it is rejected (422).
4. **Given** a teacher or a student, **Then** the admin endpoints answer 403.

### User Story 2 — Students and teachers find the open ones (Priority: P1)

1. **Given** open and closed questionnaires for both audiences, **When** a consenting student
   lists theirs, **Then** they get only open student questionnaires, with `{study_ref}` replaced
   by their export code.
2. **Given** a student without consent, **Then** the list is empty.
3. **Given** a teacher, **Then** they get only open teacher questionnaires, with `{study_ref}`
   removed.

## Requirements *(mandatory)*

- **FR-001**: Table `questionnaires` (title, url, audience, status, timestamps), RLS on, no
  client access.
- **FR-002**: `GET/POST /v1/admin/questionnaires`, `PATCH/DELETE /v1/admin/questionnaires/{id}`;
  `GET /v1/me/questionnaires`.
- **FR-003**: Nothing about who answered is stored by DocentAI.

## Success Criteria *(mandatory)*

- **SC-001**: API tests cover every scenario; the full suite passes; the migration applies on a
  clean database.
