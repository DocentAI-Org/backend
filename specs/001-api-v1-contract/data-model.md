# Data Model: DocentAI API v1

**Feature**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md) · **Date**: 2026-10-24

Physical schema in PostgreSQL (Supabase), owned by `supabase/migrations/`. All IDs are `uuid`
(`gen_random_uuid()`), all times `timestamptz` (`now()`). Every table has RLS enabled with no
client policies (research R16). "→" marks a foreign key.

## profiles

One row per auth user; created by trigger on `auth.users` insert (role always `student`).

| Column | Type | Rules |
|---|---|---|
| id | uuid PK → auth.users(id) ON DELETE CASCADE | |
| role | text | `admin` \| `teacher` \| `student` |
| display_name | text | 1–80 chars; pseudonym code for pseudonymous students |
| email | text NULL | NULL for pseudonymous students (synthetic auth email is not copied) |
| pseudonym_code | text NULL UNIQUE | set only for pseudonymous accounts |
| status | text | `active` \| `disabled` |
| preferred_language | text | `es` \| `en`, default `es` |
| created_at | timestamptz | |

## courses

| Column | Type | Rules |
|---|---|---|
| id | uuid PK | |
| teacher_id | uuid → profiles(id) | must have role teacher |
| name | text | 1–80 chars |
| description | text NULL | ≤ 500 chars |
| class_code | text UNIQUE | 8 chars `AAA-9999`-style, uppercase, regenerate replaces it |
| class_code_active | boolean | default true |
| created_at, updated_at | timestamptz | |

## enrolments

| Column | Type | Rules |
|---|---|---|
| id | uuid PK | |
| course_id | uuid → courses ON DELETE CASCADE | |
| student_id | uuid → profiles ON DELETE CASCADE | role student |
| status | text | `active` \| `revoked` |
| joined_at | timestamptz | |
| disclosure_acknowledged_at | timestamptz NULL | required before messaging (FR-050) |

Unique `(course_id, student_id)`. Joining again reactivates nothing: a revoked student gets
`enrolment_revoked`; an active one gets the existing row (idempotent).

## tutor_settings

| Column | Type | Rules |
|---|---|---|
| course_id | uuid PK → courses ON DELETE CASCADE | created with the course |
| level | text | `basic` \| `intermediate` (default) \| `advanced` |
| tone | text | `friendly` (default) \| `neutral` \| `formal` |
| solution_policy | text | `direct` \| `hints_first` (default) \| `hints_only` |
| updated_at | timestamptz | "last saved" |

## documents

| Column | Type | Rules |
|---|---|---|
| id | uuid PK | |
| course_id | uuid → courses ON DELETE CASCADE | |
| file_name | text | original name, ≤ 255 chars |
| file_type | text | `pdf` \| `docx` \| `markdown` |
| size_bytes | bigint | ≤ `MAX_UPLOAD_MB` |
| storage_path | text | `<course_id>/<document_id>.<ext>` in bucket `course-material` |
| page_count | int NULL | PDFs: pages; others: number of sections |
| processing_status | text | `processing` \| `ready` \| `error` |
| error_reason | text NULL | `unsupported_format` \| `no_readable_text` \| `processing_failed` \| `processing_interrupted` |
| validation_status | text | `pending_validation` \| `validated` \| `excluded` |
| validated_by | uuid NULL → profiles | |
| validated_at | timestamptz NULL | |
| uploaded_by | uuid → profiles | |
| uploaded_at | timestamptz | |

Transitions: `processing → ready | error`. Validation (only when `ready`):
`pending_validation → validated | excluded`, `validated → excluded`, `excluded → validated`.
Validating sets `validated_by/at`.

## fragments

| Column | Type | Rules |
|---|---|---|
| id | uuid PK | |
| document_id | uuid → documents ON DELETE CASCADE | |
| course_id | uuid → courses ON DELETE CASCADE | denormalised for retrieval |
| position | int | order within document, from 1 |
| section | text | page number or heading; target for topic assignment |
| location_label | text | `p. 12` or `§ 3.2 Despejar la incógnita` |
| text | text | |
| excluded | boolean | default false |
| embedding | vector(1024) NULL | HNSW index, cosine ops |

Retrievable ⇔ `NOT excluded AND document.processing_status='ready' AND
document.validation_status='validated'`.

## topics

| Column | Type | Rules |
|---|---|---|
| id | uuid PK | |
| course_id | uuid → courses ON DELETE CASCADE | |
| name | text | 1–60 chars; unique per course, case-insensitive |
| position | int | |
| created_at | timestamptz | |

## topic_assignments

| Column | Type | Rules |
|---|---|---|
| id | uuid PK | |
| course_id | uuid → courses ON DELETE CASCADE | |
| topic_id | uuid → topics ON DELETE CASCADE | |
| document_id | uuid → documents ON DELETE CASCADE | |
| section | text NULL | NULL = whole document |
| status | text | `suggested` \| `confirmed` |
| confirmed_by | uuid NULL → profiles | |
| confirmed_at | timestamptz NULL | |
| created_at | timestamptz | |

Unique `(topic_id, document_id, coalesce(section, ''))`. Unassigned material: validated documents
without a confirmed whole-document assignment, listed with their sections that have no confirmed
section assignment.

## conversations

| Column | Type | Rules |
|---|---|---|
| id | uuid PK | |
| course_id | uuid → courses ON DELETE CASCADE | |
| student_id | uuid → profiles ON DELETE CASCADE | |
| started_at, last_message_at | timestamptz | |

## messages

| Column | Type | Rules |
|---|---|---|
| id | uuid PK | |
| conversation_id | uuid → conversations ON DELETE CASCADE | |
| author | text | `student` \| `tutor` |
| kind | text | student: `question`; tutor: `answer` \| `hint` \| `no_source` |
| status | text | `sent` \| `failed` (failed only for student messages whose reply failed) |
| text | text | student text ≤ 4,000 chars |
| request_solution | boolean | student messages only |
| hint_number | int NULL | tutor `hint` messages |
| counts_toward_limit | boolean | true for sent student messages; false for failed |
| created_at | timestamptz | |

## citations

| Column | Type | Rules |
|---|---|---|
| id | uuid PK | |
| message_id | uuid NULL → messages ON DELETE CASCADE | exactly one of message_id / submission_id |
| submission_id | uuid NULL → exercise_submissions ON DELETE CASCADE | |
| fragment_id | uuid NULL → fragments ON DELETE SET NULL | |
| document_name | text | snapshot |
| location_label | text | snapshot |
| position | int | order in the reply |

API view adds `available` (fragment exists, not excluded, document validated) and `passage`
(fragment text when available, otherwise null).

## exercise_submissions

| Column | Type | Rules |
|---|---|---|
| id | uuid PK | |
| course_id, student_id | uuid FKs, CASCADE | |
| problem_statement | text | 1–2,000 chars |
| worked_answer | text | 1–4,000 chars |
| verdict | text | `correct` \| `partially_correct` \| `incorrect` |
| mistake_location | text NULL | |
| error_type | text NULL | from configured taxonomy |
| topic_id | uuid NULL → topics ON DELETE SET NULL | |
| topic_name | text NULL | snapshot |
| explanation | text | |
| explanation_kind | text | `answer` \| `no_source` |
| saved_to_record | boolean | |
| is_stub | boolean | true in v1 (Story 7) |
| created_at | timestamptz | |

## learning_record_entries

| Column | Type | Rules |
|---|---|---|
| id | uuid PK | |
| course_id, student_id | uuid FKs, CASCADE | |
| submission_id | uuid → exercise_submissions ON DELETE CASCADE | |
| error_type | text | |
| topic_id | uuid NULL → topics ON DELETE SET NULL | |
| topic_name | text NULL | snapshot; API adds `topic_deleted = topic_id IS NULL AND topic_name IS NOT NULL` |
| created_at | timestamptz | |

## teacher_flags

| Column | Type | Rules |
|---|---|---|
| id | uuid PK | |
| course_id | uuid → courses ON DELETE CASCADE | |
| message_id | uuid NULL UNIQUE → messages ON DELETE CASCADE | tutor messages only |
| submission_id | uuid NULL UNIQUE → exercise_submissions ON DELETE CASCADE | |
| category | text | `incorrect` \| `poor` |
| correction | text | 1–4,000 chars |
| author_id | uuid → profiles | |
| created_at, updated_at | timestamptz | |

Exactly one target. Students see `correction` and `reviewed_at` only.

## interaction_logs

| Column | Type | Rules |
|---|---|---|
| id | uuid PK | |
| course_id | uuid → courses ON DELETE CASCADE | |
| student_ref | text | HMAC of student id (research R12) |
| kind | text | `chat` \| `exercise` |
| question | text | |
| retrieved_fragment_ids | uuid[] | |
| answer | text NULL | |
| model | text NULL | NULL when the model was not called (`no_source`, stub) |
| input_tokens, output_tokens | int | 0 when not called |
| latency_ms | int | |
| estimated_cost_usd | numeric(12,6) | |
| outcome | text | `answer` \| `hint` \| `no_source` \| `error` \| `stub` |
| error_code | text NULL | |
| created_at | timestamptz | |

## daily_usage

| Column | Type | Rules |
|---|---|---|
| student_id | uuid → profiles ON DELETE CASCADE | PK part |
| usage_date | date | PK part; date in `DAILY_RESET_TIMEZONE` |
| used | int | ≤ `DAILY_MESSAGE_LIMIT` |
