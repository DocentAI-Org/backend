# Feature Specification: AI Settings per Course

**Feature Branch**: `019-course-ai-settings`

**Created**: 2026-11-07

**Status**: Draft

**Input**: User description: "A better configuration of the LLMs. The teacher configures them for
each course: the number of messages each student may use in the course (or no limit), the model
for each task, seeing the local models available, entering API keys to use commercial models,
and a wide range of options to improve these systems, such as custom instructions. As
configurable as possible, and easy to use."

**Frontend**: `frontend/specs/019-course-ai-settings`.

## Today

| Setting | Where | Scope |
|---|---|---|
| Provider, model, effort per task (spec 014) | `LLM_*` env | global, needs a restart |
| API keys | `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` env | global |
| Messages per student | `DAILY_MESSAGE_LIMIT` env (30) | per day, shared by all courses |
| Feedback temperature, max tokens | `LLM_FEEDBACK_TEMPERATURE`, `LLM_MAX_TOKENS` env | global |
| Retrieval, history | `RETRIEVAL_*`, `HISTORY_MAX_MESSAGES` env | global |
| Level, tone, solution policy | `tutor_settings` table | per course |

## Decisions (2026-11-07)

- **Three layers, like spec 015 plus the server**: each group comes from the **course** (the
  teacher), else the **study** (the admin), else the **server's environment** (today's `LLM_*`,
  `RETRIEVAL_*`, `HISTORY_MAX_MESSAGES`, `DAILY_MESSAGE_LIMIT`). Groups are overridden whole:
  `limits`, `retrieval`, `instructions`; `models` is overridden **per task**. Easy path: a course
  follows the study until the teacher chooses "Personalizar". The env settings stay as the
  server's values (the evaluation and local development keep using them), so nothing changes
  until someone edits the settings (SC-002).
- **API keys, both ways**: the admin registers **study credentials** that every course may use;
  the env keys keep working as a read-only "server" credential. If the admin allows it
  (`allow_teacher_keys`, off by default), a teacher may add **their own credential** to a course.
  Keys are encrypted at rest (Fernet, master key `LLM_CREDENTIALS_KEY` in the env, so the only
  secret in the env is the one that opens the others) and never returned: the API shows the
  provider, a label and the last four characters. The admin decides which models of a study
  credential courses may pick; a teacher's own credential offers all its models.
- **Message limit per course, with a period**: the teacher sets messages per student and a
  period — `day`, `week` (Monday to Sunday) or `course` (in total) — or no limit, and **which
  tasks count** (by default the tutor, exercise feedback and mistake review, as today). The
  **daily ceiling** per student across all courses stays as a cost safety net (§4.3): it counts
  every message, whatever the course counts; the server's value is `DAILY_MESSAGE_LIMIT` and the
  admin may change it or remove it. With the server's values (no course limit, ceiling 30) the
  behaviour is today's. Resets follow `DAILY_RESET_TIMEZONE`.
- The student sees one allowance per course: the course's limit or the ceiling, whichever has
  fewer messages left. `429 course_limit_reached` for the course, `daily_limit_reached` (today's
  code) for the ceiling.
- **Embeddings stay global** (changing the model needs re-processing all material).
- A provider failure is a 503 as today: no silent switch to another model (cost and
  reproducibility of the study).

## Options per group

| Group | Options |
|---|---|
| `models` | per task (`tutor`, `feedback`, `review`, `questions`): credential (server, study or own), model, temperature (where the provider takes it), effort (`none`…`max`), max reply tokens |
| `limits` | `messages` (≥1 or null = no limit), `period`, `counted_tasks` |
| `instructions` | free text per task, up to 2000 characters each |
| `retrieval` | fragments retrieved (1–10), minimum similarity (0–1, also for exercises), history messages kept (0–20) |

**Custom instructions** go after the system policies, inside a delimited block titled as the
teacher's instructions, with a line saying they cannot change the rules above (§4.2,
prompt-injection hygiene). They complement `tutor_settings` (level, tone, solution policy),
which stay where they are.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — The teacher limits the messages of their course (Priority: P1) 🎯

1. **Given** a course with `messages = 20, period = week`, **When** a student sends their 21st
   counted message that week, **Then** 429 with when it resets; the next Monday they can write
   again. Another course of the same student is not affected.
2. **Given** `messages = null`, **Then** the course has no limit, but the admin's global ceiling
   (if set) still applies, and its 429 says so.
3. **Given** `counted_tasks = ["tutor"]`, **Then** exercise feedback no longer uses messages.
4. **When** the student reads their allowance for the course, **Then** they get used, limit (or
   none), period and reset time.
5. **Given** a provider failure, **Then** the message is given back, as today.

### User Story 2 — The teacher chooses the model for each task (Priority: P1)

1. **When** the teacher lists the models available to the course, **Then** they get the local
   Ollama models installed (name, size, family) and, for each usable credential, its models;
   a source that does not answer is listed as unreachable, not as an error.
2. **When** they save `feedback` → study credential "OpenAI UNI" + a model it allows, **Then**
   exercise feedback in that course uses it and the interaction log keeps the model and the
   credential label; the other tasks and courses are unchanged.
3. **Given** a model the credential does not offer, or a temperature for Anthropic, **Then** 422.
4. **When** the admin removes a credential or stops offering a model a course uses, **Then**
   each task using it goes back to the inherited model and the course keeps a notice (task,
   model, reason) until its settings are saved again. The same happens to the study's own
   tasks.

### User Story 3 — Credentials (Priority: P1)

1. **Given** an admin, **When** they add a credential (provider `openai`, `anthropic` or
   `openai_compatible` with its base URL, label, key), **Then** the key is checked against the
   provider, stored encrypted, and only `…last4` is ever returned. A key the provider rejects is
   422 and is not stored.
2. **Given** `allow_teacher_keys = false`, **When** a teacher adds a credential to their course,
   **Then** 403 `teacher_keys_disabled`; with `true`, it is stored for that course only and its
   models are offered only there (the page reminds that requests then go to that provider
   under the teacher's account). Turning it off again resets the tasks using teachers' keys,
   with a notice; the keys stay and come back if it is turned on again.
3. **When** a credential is deleted, **Then** its key is erased, not just hidden.
5. **Given** no `LLM_CREDENTIALS_KEY` on the server, **When** a key is added, **Then** 409
   `credentials_not_configured`. The server's own env keys keep working.
4. **Given** a teacher or a student on the admin routes, **Then** 403; another teacher's course,
   404.

### User Story 4 — Custom instructions and advanced options (Priority: P2)

1. **Given** tutor instructions "Responde siempre con un ejemplo de la vida cotidiana", **Then**
   the tutor system prompt contains them in the teacher block, after the policies.
2. **Given** instructions longer than 2000 characters, **Then** 422.
3. **Given** `retrieval.top_k = 6` in a course, **Then** the tutor of that course retrieves up to
   six fragments.

### User Story 5 — The teacher tries the settings and sees the usage (Priority: P2)

1. **When** the teacher sends a test message for a task with settings not yet saved, **Then**
   they get the reply, the model, the latency, the tokens and the estimated cost; it is not
   logged as a student interaction and uses no allowance. At most 20 tests per teacher and hour.
2. **When** they read the course usage, **Then** they get, per task and for the last 7 and 30
   days, messages, tokens and estimated cost, and the students closest to the limit.

### User Story 6 — The admin sets the study defaults (Priority: P1)

1. **When** the admin reads and saves the study AI settings (every group, the global ceiling and
   `allow_teacher_keys`), **Then** every course without its own values uses them at once.
2. **Given** invalid values, **Then** 422 and nothing changes.

## Requirements *(mandatory)*

- **FR-001**: Routes:
  - Admin: `GET/PUT /v1/admin/ai-settings`; `GET/POST /v1/admin/llm-credentials`,
    `PATCH/DELETE /v1/admin/llm-credentials/{id}` (label, offered models).
  - Teacher: `GET/PUT /v1/teacher/courses/{id}/ai-settings`;
    `GET /v1/teacher/courses/{id}/ai-models`; `GET/POST/DELETE
    /v1/teacher/courses/{id}/llm-credentials[/{id}]`; `POST /v1/teacher/courses/{id}/ai-test`;
    `GET /v1/teacher/courses/{id}/ai-usage`.
  - Student: `GET /v1/student/courses/{id}/allowance` (the global `GET /allowance` stays, with
    the ceiling, until the frontend moves).
- **FR-002**: Migration: `ai_settings` (study row + course rows), `course_usage` keyed by
  student, course, period and period start (today's `daily_usage` kept for the ceiling);
  `llm_credentials` in PR 2. RLS on, no client access.
- **FR-003**: The LLM client takes the course's effective settings: `chat_json(..., task,
  settings)` routes by them; providers for study and own credentials are built on demand and
  cached by credential id.
- **FR-004**: Model catalogue: Ollama `GET /api/tags`, OpenAI-compatible `GET /models`,
  Anthropic models list; each cached 5 minutes; timeout 5 s per source.
- **FR-005**: Keys never appear in logs, errors, API responses or the study export.
- **FR-006**: Requirements §4.1 and §4.2 updated in the knowledge base: keys in the database
  encrypted, own credentials only if the admin enables them, DPA note for each provider.

## Success Criteria *(mandatory)*

- **SC-001**: API tests cover every scenario with fake providers; the full suite passes.
- **SC-002**: With no course overrides, behaviour and evaluation results are as before.
- **SC-003**: Validated on the real stack: a course with a weekly limit and a local model per
  task, another with the study defaults.
