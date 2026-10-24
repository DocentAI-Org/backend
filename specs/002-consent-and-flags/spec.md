# Feature Specification: Study Consent and Course Corrections List

**Feature Branch**: `002-consent-and-flags`

**Created**: 2026-10-24

**Status**: Draft

**Input**: User description: "Backend support the frontend feature 002 needs and the API v1 lacks:
consent revocation from the student profile, the course flags list for teachers, and a
'corrected' marker on conversation summaries."

**Requirements source**: `knowledge-base/docs/requirements.md` (§4.1 informed consent, T6). The
frontend behavior is in `frontend/specs/001-mvp-prototype/spec.md` (US7 AS4, US8 AS1 and AS3,
FR-015) and `frontend/specs/002-app-api-integration/spec.md` (deviations D1 and D4).

## Clarifications

### Session 2026-10-24

- Q: Is revocation added to the backend now? → A: Yes; revoking blocks the tutor until the
  student accepts again.
- Q: Are the course flags list and the "corrected" marker added now? → A: Yes; the topic filter on
  conversations is deferred.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Student gives, reviews and revokes study consent (Priority: P1)

**Role**: Student · **Covers**: §4.1, frontend 001 US7 AS4, FR-015

On first use a student gives their informed consent to take part in the study. They can review
it, with its date and version, and revoke it at any time from their profile. While consent is not
given, the tutor and exercise feedback are blocked; the student can still read their own data and
give consent again.

**Why this priority**: Informed, revocable consent is a GDPR and Ethics Committee requirement of
the pilot.

**Independent Test**: As a new student, try to message the tutor (blocked), give consent, message
(accepted), revoke, message (blocked again), and read the consent history.

**Acceptance Scenarios**:

1. **Given** a student who never consented, **When** they read their profile, **Then** consent is
   reported as not given.
2. **Given** a student, **When** they give consent for the current consent version, **Then** it
   is recorded with date and version, and their profile reports it as given.
3. **Given** a student without consent, **When** they send a tutor message or submit an exercise,
   **Then** the request is rejected with `consent_required` and nothing is counted or sent to the
   model.
4. **Given** a student with consent, **When** they revoke it, **Then** it is recorded, their
   profile reports it as not given, and tutor and exercise requests are rejected again.
5. **Given** the consent version changes, **When** a student who consented to the old version
   uses the tutor, **Then** they must consent to the new version first.
6. **Given** a student, **When** they read their consent history, **Then** they see every give and
   revoke event with its date and version, and no one else's.

---

### User Story 2 — Teacher lists the corrections of a course (Priority: P1)

**Role**: Teacher · **Covers**: T6, frontend 001 US8 AS3 (screen #25)

**Why this priority**: Required by the flags screen of the frontend 002 release.

**Independent Test**: Flag a tutor message and an exercise feedback in a course, then list the
course's flags.

**Acceptance Scenarios**:

1. **Given** a course with flags, **When** the teacher lists them, **Then** each item shows the
   category, correction, author, dates, the student's display name, the original tutor text, and
   what it belongs to (a conversation message or an exercise), so the screen can link back to it.
2. **Given** another teacher's course, **When** a teacher lists its flags, **Then** it is not
   found.

---

### User Story 3 — Teacher sees which conversations have corrections (Priority: P1)

**Role**: Teacher · **Covers**: T4, T6, frontend 001 US8 AS1

**Acceptance Scenarios**:

1. **Given** a conversation with at least one corrected tutor message, **When** the teacher lists
   conversations, **Then** its summary is marked as corrected; others are not.
2. **Given** the conversation list, **When** the teacher filters by "has correction", **Then**
   only matching conversations are returned.

### Edge Cases

- Revoking when consent was never given: no event is recorded; the profile still reports "not
  given".
- Giving consent twice for the same version: the second call succeeds without a duplicate event.
- Teachers and admins have no study consent; the endpoints are for students only.
- A student who revokes keeps read access to their own conversations, submissions and learning
  record; erasure of their data is a separate request (§4.1) out of scope here.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The API MUST record study consent per student as an append-only history of give and
  revoke events, each with time and consent version.
- **FR-002**: The current consent version MUST be configurable; consent counts as given only for
  the current version.
- **FR-003**: Students MUST be able to read their consent status (given, version, date) and
  history, give consent and revoke it.
- **FR-004**: Tutor messages, retries and exercise submissions MUST be rejected with
  `consent_required` while consent is not given, before any allowance is used or the model is
  called.
- **FR-005**: Teachers MUST be able to list the flags of a course they own, paginated, newest
  first, with the fields in US2 AS1.
- **FR-006**: Conversation summaries for teachers MUST include whether the conversation has at
  least one teacher correction, and the list MUST be filterable by it.
- **FR-007**: All changes MUST be additive to the API v1 contract (no removed or changed fields).

### Key Entities

- **ConsentEvent**: student, action (given / revoked), consent version, time. Append-only.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of tutor and exercise requests without current consent are rejected without
  using the allowance or calling the model.
- **SC-002**: Every consent change is recoverable from the history with its date and version.
- **SC-003**: The frontend 002 can implement screens #13 (revocation), #23 (corrected marker) and
  #25 (flags list) with types generated from the contract, with no hand-written types.
- **SC-004**: The API v1 contract stays backward compatible (additive changes only); existing tests
  pass with only the consent step added to their shared setup.

## Assumptions

- The consent text itself lives in the frontend (translated); the backend stores only the version
  identifier the student accepted (default `2026-10`), set by configuration and changed when the
  text approved by the Ethics Committee changes.
- Existing students in local data have no consent and must give it once.
- Per-course AI disclosure (API v1) stays as it is; study consent is account-wide and checked in
  addition to it.
