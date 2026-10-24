# API Contract additions (v1, additive)

## Student — study consent (`/v1/student`)

| Method | Path | Response |
|---|---|---|
| GET | `/consent` | `Consent {given, version?, given_at?, current_version}` |
| POST | `/consent` | `Consent` (gives consent for `current_version`) |
| DELETE | `/consent` | `Consent` (revokes) |
| GET | `/consent/history` | `list[ConsentEvent {action: given\|revoked, version, created_at}]` |

New error: `409 consent_required` on `POST …/messages`, `POST …/messages/{id}/retry` and
`POST …/submissions` when consent for the current version is not given. It is checked before
`disclosure_not_acknowledged`.

## Teacher (`/v1/teacher/courses/{course_id}`)

| Method | Path | Response |
|---|---|---|
| GET | `/flags` | `Page[CourseFlag {id, category, correction, author_name?, created_at, updated_at, student_id, student_name, original_text, target: message\|submission, conversation_id?, message_id?, submission_id?}]` |

`ConversationSummary` gains `has_correction: bool`; `GET /conversations` accepts
`has_correction=true|false`.
