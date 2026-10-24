# Feature Specification: DocentAI API v1 — Contract for the MVP "Must" Requirements

**Feature Branch**: `001-api-v1-contract`

**Created**: 2026-10-24

**Status**: Draft

**Input**: User description: "First version of the DocentAI backend API, in Python, building on the
existing backend files. Define the full API contract for every Must (M) requirement so the frontend
can generate its types from it, persist data in a local Supabase stack from day one, and manage
models through a provider-agnostic layer (OpenAI-compatible; Ollama locally, open or closed models
chosen by configuration)."

**Requirements source**: `knowledge-base/docs/requirements.md` (revised 2026-10-06). IDs T#, S#, P#
refer to its §3; §4.x to its non-functional requirements. The frontend's view of the same data is
in `frontend/specs/001-mvp-prototype/` (spec.md and data-model.md); this API MUST be able to supply
every field that data model lists for the M stories.

**Scope**: every M requirement — T1, T2, T3, T4, T6, T9, S1, S2, S3, S4, P1, P2. Should (S) and
Could (C) requirements (T5, T7, T8, S5–S8, P3–P5) are out of scope, except where an M requirement
must store data they will later read (e.g. the learning record written by S4).

## Clarifications

### Session 2026-10-24

- Q: How are models managed? → A: Through one OpenAI-compatible layer configured only by settings;
  Ollama is the local default for chat and embeddings; any OpenAI-compatible provider (open or
  closed models) can be used by changing configuration.
- Q: What is the scope of the first API version? → A: The full contract for every M requirement.
- Q: Is data persisted in this feature? → A: Yes, in the local Supabase stack, with versioned
  migrations from day one.
- Q: Which stories must fully work at the end of this feature, and which may ship as stubs? → A:
  The whole contract exists. Stories 1–6 and 8 are fully working (auth and roles, courses and
  enrolment, material processing with embeddings and validation, tutor settings, grounded chat with
  citations, daily allowance, interaction logging, topics, review and corrections). Story 7
  (exercise feedback) ships as a deterministic stub that honors the contract until the error
  taxonomy (requirements §5) is agreed.
- Q: How are student accounts provisioned? → A: Both ways: students can self-register (email +
  password) and join with a class code, and admins can create pseudonymous student accounts in
  bulk (code + password) for the pilot (§4.1).

## User Scenarios & Testing *(mandatory)*

> Every story is an M requirement. Priorities order the work inside this feature: P1 stories form
> the core loop (sign in → course → validated material → grounded answer); P2 stories complete the
> M set. Each story names its **role(s)** and the **requirement IDs** it covers. "API client" below
> means any authenticated caller, normally the frontend.

### User Story 1 — Users authenticate and every request is limited to what their role allows (Priority: P1)

**Role**: Admin, Teacher, Student · **Covers**: P1, §4.1, §4.2

A user signs in through the authentication service and calls the API with their session. The API
identifies who they are and their role, and every response contains only data that role and that
person may see. Students see only their own data and courses they are enrolled in; teachers see
only their own courses; admins see only account and course management.

**Why this priority**: No other story can be exposed safely without it.

**Independent Test**: With seeded admin, two teachers and two students, call each endpoint as each
user and confirm that allowed calls succeed and every cross-user or cross-role call is rejected.

**Acceptance Scenarios**:

1. **Given** a request with no session or an expired session, **When** it calls any protected
   endpoint, **Then** it is rejected as unauthenticated with a stable error code, and no data is
   returned.
2. **Given** a signed-in student, **When** they request their profile, **Then** they receive their
   own display name, role and preferred language, and nothing about other users.
3. **Given** student A, **When** they request a conversation, submission or learning-record entry
   belonging to student B, **Then** the request is rejected as not found, without revealing that it
   exists.
4. **Given** teacher A, **When** they request any resource of a course owned by teacher B, **Then**
   the request is rejected as not found.
5. **Given** a student or teacher, **When** they call an admin endpoint, **Then** it is rejected as
   forbidden.
6. **Given** an admin, **When** they list users, create a teacher account, create pseudonymous
   student accounts in bulk, or list courses, **Then** the request succeeds; no other admin
   capability exists.
7. **Given** a person without an account, **When** they self-register as a student, **Then** they
   get a student account (never teacher or admin) and can join courses with a class code.

---

### User Story 2 — Teacher creates a course and students join it with a class code (Priority: P1)

**Role**: Teacher, Student · **Covers**: T1

A teacher creates a course and gets a class code and invitation link they can regenerate or
disable. A student joins with the code or link, sees the course in their list, and can switch
between their courses.

**Why this priority**: Courses are the container for material, settings and conversations.

**Independent Test**: Create a course as a teacher, join it as a student with its code, and list
the student's courses.

**Acceptance Scenarios**:

1. **Given** a teacher, **When** they create a course with a valid name (1–80 characters), **Then**
   the course is created with an active class code and invitation link, and appears only in their
   course list.
2. **Given** a course with an active code, **When** a student joins with that code, **Then** they
   are enrolled, and the course appears in their course list with its name, description and
   teacher name.
3. **Given** a teacher regenerates or disables a code, **When** a student tries the old or disabled
   code, **Then** joining fails with a distinct error code for invalid, disabled or unknown codes.
4. **Given** a student already enrolled, **When** they join the same course again, **Then** the
   request succeeds without creating a duplicate enrolment.
5. **Given** a teacher, **When** they list a course's students, **Then** they receive each
   student's display name (pseudonym where used) and join date, and nothing else.

---

### User Story 3 — Teacher uploads, curates and validates course material (Priority: P1)

**Role**: Teacher · **Covers**: T2

A teacher uploads PDF, DOCX or Markdown files. Each file is processed into fragments with a page or
section reference. The teacher reviews the fragments, excludes those the tutor must not use,
validates the document, or excludes it entirely. Each document shows its processing status,
validation status, who validated it and when.

**Why this priority**: The tutor cannot answer without validated material.

**Independent Test**: Upload a sample document, wait for it to be ready, list its fragments,
exclude one, validate the document, and confirm that only non-excluded fragments of validated
documents are retrievable.

**Acceptance Scenarios**:

1. **Given** a teacher and a supported file within the size limit, **When** they upload it,
   **Then** the document is stored privately with status "processing" and validation status
   "pending validation", and the call returns without waiting for processing to finish.
2. **Given** processing finishes, **When** the teacher reads the document, **Then** its status is
   "ready" with page count, fragment count, and each fragment has its order, location label and
   text; **or** its status is "error" with a reason (unsupported format, too large, no readable
   text).
3. **Given** a ready document, **When** the teacher excludes a fragment, **Then** the fragment is
   marked excluded and is never retrieved or cited; **When** they include it again, **Then** it is
   retrievable again (if the document is validated).
4. **Given** a ready document, **When** the teacher validates it, **Then** its status becomes
   "validated" and records who validated it and when; **When** they exclude it, **Then** none of its
   fragments are retrievable; **When** they validate an excluded document, **Then** it becomes
   validated again.
5. **Given** an unsupported file type or a file over the size limit, **When** it is uploaded,
   **Then** it is rejected with a distinct error code and nothing is stored.
6. **Given** a teacher, **When** they request a document's file, **Then** they receive a
   short-lived link; the file is never publicly reachable.

---

### User Story 4 — Student asks the tutor and gets a grounded, cited answer (Priority: P1)

**Role**: Student · **Covers**: S1, S2, S3, T3 (applied), P2, §4.3

A student sends a question in a course chat. The tutor answers only from the course's validated
material, following the teacher's settings, and returns the citations it used. When the material
does not cover the question, the API returns an explicit "not covered" answer with no citations.
In guided mode, problem questions get numbered hints before any solution. Every interaction is
logged with its cost, and each student has a daily message allowance shared across their courses.

**Why this priority**: This is DocentAI's core value.

**Independent Test**: With one validated document seeded, ask a question it covers (answer with at
least one citation), a question it does not cover (not-covered answer), and exceed the daily limit
(blocked) — using a deterministic fake model.

**Acceptance Scenarios**:

1. **Given** an enrolled student who has not acknowledged the AI disclosure for the course,
   **When** they send a message, **Then** it is rejected with a "disclosure not acknowledged" error;
   **after** they acknowledge it, messages are accepted.
2. **Given** validated material that covers the question, **When** the student sends it, **Then**
   the response contains the tutor's answer, kind "answer", and at least one citation with document
   name, location label and the cited passage.
3. **Given** no validated, non-excluded fragment is relevant enough, **When** the student asks,
   **Then** the response has kind "no-source", contains no citations, and the language model is not
   asked to answer.
4. **Given** the course's solution policy is "hints only" or "hints first", **When** the student
   asks a problem question, **Then** the response has kind "hint" with a hint number, and a full
   solution is returned only when the policy allows it and the student asks for it.
5. **Given** any tutor reply, **When** it is produced, **Then** an interaction record is stored with
   the question, the retrieved fragment IDs, the answer, the model, input and output tokens,
   latency and estimated cost, without any identifying data of the student sent to the model.
6. **Given** a student with messages left, **When** they read their allowance, **Then** they get
   the limit, the remaining count and the reset time, shared across all their courses.
7. **Given** a student who reached the daily limit, **When** they send a message, **Then** it is
   rejected with a "daily limit reached" error that includes the reset time, and the model is not
   called.
8. **Given** the model provider fails or times out, **When** the student sends a message, **Then**
   the message is marked failed with a stable error code, and it does not count toward the limit.
9. **Given** an enrolled student, **When** they read the course's tutor settings, **Then** they get
   the level, tone and solution policy chosen by the teacher (read only).
10. **Given** a student, **When** they list their conversations or read one, **Then** they get their
    own messages in order, including any teacher correction attached to a tutor message.

---

### User Story 5 — Teacher configures the tutor (Priority: P2)

**Role**: Teacher · **Covers**: T3

The teacher sets the course level, tutor tone and solution policy (direct solutions allowed / hints
first, then solution / hints only). New courses start with defaults.

**Why this priority**: Required by M, but the tutor works with defaults until it is set.

**Independent Test**: Read the defaults of a new course, update them, and confirm the next tutor
request uses the new policy.

**Acceptance Scenarios**:

1. **Given** a new course, **When** its settings are read, **Then** they are level "intermediate",
   tone "friendly", policy "hints first, then solution".
2. **Given** the teacher updates the settings with valid values, **When** they save, **Then** the
   new values and the save time are returned and apply to every later tutor request in the course.
3. **Given** an invalid value, **When** it is saved, **Then** it is rejected with a validation error
   naming the field.

---

### User Story 6 — Teacher defines course topics and assigns material to them (Priority: P2)

**Role**: Teacher · **Covers**: T9

The teacher creates, renames, reorders and deletes the course's topics, and assigns each document
or section to topics. The system may suggest assignments; suggestions stay marked as suggested
until the teacher confirms them.

**Why this priority**: Required by M; feedback classification (Story 7) needs topics.

**Independent Test**: Create two topics, assign a document section to one, confirm a suggestion,
and list unassigned sections.

**Acceptance Scenarios**:

1. **Given** a teacher, **When** they create a topic with a name of 1–60 characters unique in the
   course, **Then** it is created in the next position; duplicates are rejected.
2. **Given** a document section, **When** the teacher assigns it to a topic, **Then** the
   assignment is "confirmed"; **When** the system suggests an assignment, **Then** it is
   "suggested" until the teacher confirms, changes or removes it.
3. **Given** a topic with assignments, **When** it is deleted, **Then** its assignments are removed
   and past learning-record entries keep the topic name marked as deleted.
4. **Given** a course, **When** the teacher asks for unassigned material, **Then** they get every
   validated document or section without a confirmed topic.

---

### User Story 7 — Student submits a worked exercise and gets feedback on the mistake (Priority: P2)

**Role**: Student · **Covers**: S4, S2, P2

A student submits a problem statement and their worked answer. They receive feedback: a verdict,
where the mistake is, its error type and topic, an explanation grounded in the material with
citations (or a not-covered notice), and confirmation that the mistake was saved to their learning
record.

**Why this priority**: Required by M; it builds on the same grounding and logging as Story 4.

**Delivery in this feature**: contract-honoring deterministic stub (FR-100). The acceptance
scenarios below are verified against the stub's fixed feedback; real feedback follows in a later
feature once the error taxonomy exists.

**Independent Test**: Submit an exercise with a known mistake using the fake model and confirm the
feedback fields and the new learning-record entry.

**Acceptance Scenarios**:

1. **Given** an enrolled student within their daily limit, **When** they submit an exercise,
   **Then** the submission is stored and they receive feedback with verdict (correct / partially
   correct / incorrect), mistake location, error type, topic and an explanation with citations or a
   not-covered notice.
2. **Given** feedback that identifies a mistake, **When** it is produced, **Then** a learning-record
   entry is stored with error type, topic, student, course and date, and the feedback says it was
   saved.
3. **Given** the student or their teacher, **When** they list the student's learning record for a
   course, **Then** they get its entries; no other user can.
4. **Given** a submission, **When** it is processed, **Then** it counts toward the daily limit and
   is logged like a chat interaction.

---

### User Story 8 — Teacher reviews conversations and corrects poor answers (Priority: P2)

**Role**: Teacher, Student · **Covers**: T4, T6

A teacher browses their students' conversations and exercise feedback, filters them, flags a tutor
answer or feedback as wrong or poor, and writes a correction. The student sees the correction on
the original message, marked as reviewed by the teacher.

**Why this priority**: Required by M; depends on Stories 4 and 7 producing messages.

**Independent Test**: As a teacher, list a course's conversations, flag a tutor message with a
correction, then read the conversation as the student and see the correction.

**Acceptance Scenarios**:

1. **Given** a teacher, **When** they list a course's conversations, **Then** they get, per
   conversation, the student's display name, start and last-message times, message count and
   whether it contains no-source answers; filterable by student, date range and no-source.
2. **Given** a tutor message or feedback, **When** the teacher flags it with a category (incorrect /
   poor) and a correction text, **Then** the flag is stored with author and time and is also
   available for the evaluation set.
3. **Given** a flagged message, **When** the student reads the conversation, **Then** the message
   carries the correction text and a "reviewed by teacher" marker, but not the flag category.
4. **Given** a teacher edits or removes their correction, **When** the student reads it again,
   **Then** they see the current state.

---

### Edge Cases

- A document finishes processing after the teacher deleted it: processing results are discarded.
- A document or fragment cited in an old answer is later excluded: the citation is still returned,
  marked "no longer available", and its passage is withheld.
- A course has no validated material: every question returns "no-source" without calling the
  model.
- A student's enrolment is revoked: they lose access to the course's chat and settings, while their
  own past messages remain readable to them only if a spec later allows it (out of scope; access is
  denied in v1).
- Two messages from the same student arrive at the same time with one message left: at most one is
  accepted.
- The daily allowance resets at midnight in the configured time zone of the deployment.
- A question or uploaded text contains instructions aimed at the tutor ("ignore your rules…"): it
  is treated as data and cannot change the tutor's settings or policy.
- The model returns an answer that cites no retrieved fragment: the API returns it as "no-source"
  rather than an uncited answer.
- An exercise submission with an empty worked answer is rejected by validation.

## Requirements *(mandatory)*

### Functional Requirements

**Contract & errors**

- **FR-001**: The API MUST publish a machine-readable contract describing every endpoint, request
  and response in this spec, so the frontend can generate its types from it.
- **FR-002**: Every error MUST be returned in one consistent shape with a stable, machine-readable
  code; the API MUST NOT return user-facing copy (the frontend translates codes).
- **FR-003**: List endpoints MUST be paginated with a consistent scheme.
- **FR-004**: The API MUST expose an unauthenticated health check that reports service status and
  version, and whether its database and model provider are reachable.

**Identity & access (P1)**

- **FR-010**: The API MUST authenticate every non-public request with the platform's
  authentication service and resolve the caller's role (admin, teacher, student).
- **FR-011**: Every endpoint MUST enforce role and ownership rules: students only their own data in
  courses they are enrolled in; teachers only their own courses; admins only account and course
  management.
- **FR-012**: Access to another user's resource MUST be indistinguishable from a missing resource.
- **FR-013**: Admins MUST be able to list users (role, status), create teacher accounts, create
  pseudonymous student accounts in bulk (generated code + initial password, no email), and list
  courses; nothing else.
- **FR-014**: Students MUST be able to appear under a pseudonym or code instead of their real name;
  teachers MUST only ever receive a student's display name. Student accounts are provisioned in
  two ways: self-registration (email + password, always with the student role) followed by joining
  with a class code, or bulk creation of pseudonymous accounts by an admin (FR-013).
- **FR-015**: Users MUST be able to read and update their own preferred language (es / en).

**Courses & enrolment (T1)**

- **FR-020**: Teachers MUST be able to create, list, read and update their courses (name 1–80
  characters, optional description).
- **FR-021**: Each course MUST have a class code and invitation link that the teacher can read,
  regenerate (invalidating the previous code) and disable or enable.
- **FR-022**: Students MUST be able to join a course with a valid active code, idempotently, and
  list their courses with name, description and teacher name.
- **FR-023**: Teachers MUST be able to list a course's enrolled students (display name, join date,
  status) and revoke an enrolment.

**Material (T2)**

- **FR-030**: Teachers MUST be able to upload PDF, DOCX and Markdown files up to a configurable size
  limit (default 20 MB); other types MUST be rejected.
- **FR-031**: Uploaded files MUST be stored privately and processed asynchronously into ordered
  fragments, each with a page or section location label.
- **FR-032**: Each document MUST expose: file name, type, size, page count, processing status
  (processing / ready / error) with error reason, validation status (pending validation /
  validated / excluded), validated by and at, fragment count, excluded fragment count, upload time
  and its confirmed topics.
- **FR-033**: Teachers MUST be able to list a document's fragments, exclude or include each
  fragment, validate a document, exclude a document, and delete a document.
- **FR-034**: Only non-excluded fragments of validated documents MUST ever be retrieved, sent to
  the model or cited.
- **FR-035**: Teachers MUST be able to obtain a short-lived link to a document's original file.

**Tutor settings (T3)**

- **FR-040**: Each course MUST have tutor settings — level (basic / intermediate / advanced), tone
  (friendly / neutral / formal), solution policy (direct allowed / hints first then solution /
  hints only) — with defaults intermediate / friendly / hints first, and a last-saved time.
- **FR-041**: Teachers MUST be able to update them; enrolled students MUST be able to read them.
- **FR-042**: The settings MUST be applied server-side to every tutor reply and exercise feedback.

**Tutor chat (S1, S2, S3)**

- **FR-050**: Students MUST acknowledge an AI disclosure (AI tutor, validated material only,
  teacher may review conversations) once per course before sending messages; the acknowledgement
  and its time MUST be stored.
- **FR-051**: Students MUST be able to start conversations in a course, send messages, and list and
  read their conversations.
- **FR-052**: Each tutor message MUST have a kind (answer / hint / no-source / failed), its text,
  citations (document name, location label, passage, availability), sent time, whether it counts
  toward the limit, hint number where applicable, and the teacher correction if any.
- **FR-053**: When no validated fragment is relevant enough (configurable threshold), the reply
  MUST be "no-source" with no citations, and the model MUST NOT be called.
- **FR-054**: In guided mode (policy "hints first" or "hints only"), replies to problem questions
  MUST be hints; a solution MUST be given only when the policy allows it and the student requests
  it.
- **FR-055**: Tutor replies MUST be in Spanish for the MVP; prompts MUST be stored outside code so
  other languages can be added.
- **FR-056**: User input and document text MUST be treated as data and MUST NOT be able to change
  the tutor's instructions or settings.
- **FR-057**: Tutor replies MAY be returned in a single response; incremental delivery is not
  required in v1.

**Daily allowance & cost (§4.3, P2)**

- **FR-060**: Each student MUST have one daily message allowance shared across all their courses,
  with a configurable limit (OQ13 open) and reset time; the API MUST expose limit, remaining and
  reset time.
- **FR-061**: Chat messages and exercise submissions MUST count toward the allowance; failed
  requests MUST NOT; the check MUST happen before the model is called and be safe under concurrent
  requests.
- **FR-062**: Every model interaction MUST be stored with question, retrieved fragment IDs, answer,
  model name, input and output tokens, latency, estimated cost, course and a pseudonymous student
  reference.
- **FR-063**: No identifying data of a student (name, email, account ID) MUST be sent to the model
  provider.
- **FR-064**: The model provider, base URL, chat model, embedding model, credentials and per-token
  prices MUST be set by configuration only; the local default MUST be a locally running model
  server with no cost.

**Topics (T9)**

- **FR-070**: Teachers MUST be able to create, rename, reorder and delete course topics (name 1–60
  characters, unique within the course).
- **FR-071**: Teachers MUST be able to assign documents or sections to topics; assignments have
  status suggested or confirmed, and suggested ones MUST be confirmed, changed or removed by the
  teacher before they count.
- **FR-072**: Teachers MUST be able to list validated material that has no confirmed topic.
- **FR-073**: The system MAY create suggested assignments after a document is processed.

**Exercises & learning record (S4)**

- **FR-080**: Students MUST be able to submit an exercise (problem statement and worked answer as
  text) in a course and receive feedback: verdict, mistake location, error type, topic, explanation
  with citations or not-covered notice, and whether it was saved to the learning record.
- **FR-081**: Error types MUST come from a configurable taxonomy (requirements §5, not yet
  defined); the API MUST accept a placeholder taxonomy until it is agreed.
- **FR-082**: Each identified mistake MUST create a learning-record entry (error type, topic,
  student, course, date, link to the submission) visible to the student and their teacher only.

**Review & corrections (T4, T6)**

- **FR-090**: Teachers MUST be able to list and filter their courses' conversations and exercise
  feedback (by student, date range, no-source) and read them in full.
- **FR-091**: Teachers MUST be able to flag a tutor message or feedback with a category (incorrect /
  poor) and a correction text, and edit or remove it.
- **FR-092**: Students MUST receive the correction text and a "reviewed by teacher" marker on the
  original message; they MUST NOT receive the flag category.
- **FR-093**: Flags and corrections MUST be retrievable as an evaluation-set export for the team
  (requirements §4.4).

**Implementation depth**

- **FR-100**: Every endpoint in this spec MUST exist in the contract. Stories 1–6 and 8 MUST be
  fully working. Story 7 MAY ship as a deterministic stub: it MUST honor the contract (same
  models, status codes, allowance and logging behavior) and MUST store submissions and
  learning-record entries, but its feedback content is fixed. The contract MUST mark stub endpoints
  as such.

### Key Entities *(include if feature involves data)*

- **User**: a person with one role (admin, teacher, student), display name (pseudonym allowed),
  email (optional for pseudonymous students), account status, preferred language.
- **Course**: owned by one teacher; name, description, class code, code status, creation time.
- **Enrolment**: links a student to a course; join time, status (active / revoked), disclosure
  acknowledgement time.
- **MaterialDocument**: a file uploaded to a course; type, size, page count, processing status,
  validation status, validated by/at, upload time.
- **Fragment**: an ordered piece of a document with location label, text, excluded flag, and a
  vector representation used for retrieval.
- **Topic**: a learning objective of a course; name, order.
- **TopicAssignment**: links a document or section to a topic; status suggested / confirmed.
- **TutorSettings**: per course; level, tone, solution policy, last saved time.
- **Conversation**: a student's chat thread in a course.
- **Message**: a student or tutor message; kind, text, citations, hint number, counts-toward-limit.
- **Citation**: a reference from a tutor message or feedback to a fragment; availability.
- **ExerciseSubmission / Feedback**: problem statement, worked answer, verdict, mistake location,
  error type, topic, explanation, citations.
- **LearningRecordEntry**: an identified mistake; error type, topic, student, course, date,
  source submission.
- **TeacherFlag**: a teacher's flag on a tutor message or feedback; category, correction text,
  author, time.
- **InteractionLog**: one model call; question, retrieved fragment IDs, answer, model, tokens,
  latency, estimated cost, pseudonymous student reference, course.
- **DailyAllowance**: per student per day; limit, used count, reset time.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The frontend can generate types for 100% of the data its MVP prototype shows for M
  stories from the published contract, with no hand-written API types.
- **SC-002**: In the automated access test matrix (each endpoint × each role × own/other's data),
  100% of cross-user and cross-role requests are rejected.
- **SC-003**: With a seeded validated document, 100% of questions it covers return at least one
  citation, and 100% of questions with no relevant material return "no-source" without a model
  call, using the deterministic test model.
- **SC-004**: 100% of model calls produce an interaction record with tokens, latency and estimated
  cost; 0 records or outbound prompts contain a student's name or email.
- **SC-005**: A developer can start the full local stack and get a cited answer to a question
  about a sample document in under 15 minutes from a fresh clone, following the quickstart, at
  zero cost.
- **SC-006**: Switching between a local model and a hosted provider requires only configuration
  changes and passes the same automated test suite.
- **SC-007**: A student never exceeds their daily allowance, including under 10 concurrent
  requests.
- **SC-008**: A tutor reply on local hardware returns in under 10 seconds for 95% of requests in
  the sample course (excluding first model load).

## Assumptions

- Participants are adults (requirements §2); no parental consent flows.
- Authentication is provided by the platform's authentication service (Supabase Auth, per
  architecture.md); the API verifies sessions but does not implement password flows itself.
- The daily message limit default is 30 per student (frontend data model's illustrative value)
  until OQ13 is decided; the limit is configurable.
- Error types use a small placeholder taxonomy until the educational stream defines it (§5).
- Exercise photos (frontend FR-033 "optionally a photo") are out of scope for v1; only text.
- Topic suggestions (FR-073) may be absent in v1; manual assignment is enough to satisfy T9.
- Should/Could requirements are out of scope; data written by M stories (learning record,
  interaction log, flags) is stored so they can be built later.
- Tutor replies are returned as a whole response; streaming may be added later without changing the
  stored data.
- The existing `/health` and `/chat` endpoints are replaced by the versioned contract; `/chat` was a
  placeholder with no consumers.
- Deployment (Railway, Supabase Pro, Sentry) is out of scope; this feature targets the local stack.
