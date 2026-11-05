# Feature Specification: Search, Sort and Favourites in Lists

**Feature Branch**: `016-list-tools`

**Created**: 2026-11-05

**Status**: Draft

**Input**: User description: "Make the lists more manageable; right now they are endless lists.
Maybe filters, a search box, something to organise them like favourites." Decided 2026-11-05:
every list, search and favourites on the server, a "Show more" button for long lists.

**Frontend**: `frontend/specs/016-list-tools`.

## Today

Nine list endpoints page with `limit`/`offset` and return `total`, but none can search or
sort, and nothing can be marked as a favourite. The frontend asks for the first 100 items and
shows them all, so a list longer than that is cut without notice.

| Endpoint | Order today |
|---|---|
| `GET /v1/teacher/courses` | newest first |
| `GET /v1/student/courses` | last joined first |
| `GET /v1/teacher/courses/{id}/students` | first joined first |
| `GET /v1/teacher/courses/{id}/conversations` | last message first |
| `GET /v1/teacher/courses/{id}/submissions` | newest first |
| `GET /v1/teacher/courses/{id}/documents` | last uploaded first |
| `GET /v1/teacher/courses/{id}/questions` | pending first, then newest |
| `GET /v1/admin/users` | newest first |
| `GET /v1/admin/courses` | newest first |

## Decisions

- **Search** (`q`): every list above takes an optional `q`. It matches when every word of `q`
  appears in one of the list's text fields, ignoring case and accents ("garcia" finds
  "García"). Blank `q` is no search.
- **Sort** (`sort`): an optional value per list; the default keeps today's order, so current
  clients see no change.
- **Favourites**: a teacher can star the courses they teach and a student the courses they are
  in. A user's favourites come first in their course list, whatever the sort; each course
  says whether it is one. Stored per user and course; nothing else is a favourite for now.
- `total` counts the items that match, so "Showing 20 of 143" stays true while searching.

| List | `q` searches | `sort` values (first is the default) |
|---|---|---|
| Teacher courses | name, description | `recent`, `name` |
| Student courses | name, description, teacher's name | `recent`, `name` |
| Course students | display name | `joined`, `name` |
| Conversations | student's name, message text | `recent`, `oldest` |
| Exercise submissions | student's name, statement, answer, topic | `recent`, `oldest` |
| Documents | file name | `recent`, `name` |
| Questions | statement, topic name | `default` (pending first), `recent` |
| Admin users | display name, email | `recent`, `name` |
| Admin courses | name, teacher's name | `recent`, `name` |

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Find something in a long list (Priority: P1) 🎯

1. **Given** a teacher with courses "Álgebra 3º" and "Geometría", **When** they list their
   courses with `q=algebra`, **Then** only "Álgebra 3º" comes back and `total` is 1.
2. **Given** students "Ana García" and "Luis Pérez", **When** the teacher lists the course's
   students with `q=garcia ana`, **Then** only Ana comes back.
3. **Given** a conversation where a student wrote "paréntesis", **When** the teacher lists the
   conversations with `q=parentesis`, **Then** that conversation comes back, together with the
   existing filters (student, dates, no source, corrected).
4. **Given** questions about two topics, **When** the teacher searches a word of a statement or
   a topic name, **Then** only the matching questions come back and the status counts follow
   the search.
5. **Given** an admin, **When** they list users with `q` set to part of an email, **Then** that
   user comes back, with the role and status filters still applying.
6. **Given** `q` with only spaces, **Then** the list is the same as without `q`.

### User Story 2 — Sort a list (Priority: P2)

1. **Given** courses created in the order "B", "A", **When** the teacher lists them with
   `sort=name`, **Then** they come back "A", "B"; with no `sort`, "A", "B" (newest first).
2. **Given** an unknown `sort` value, **Then** 422.

### User Story 3 — Star the courses I use most (Priority: P1)

1. **Given** a teacher with three courses, **When** they star the oldest one
   (`PUT /v1/me/favorite-courses/{course_id}`), **Then** it comes first in their list, marked
   `is_favorite`, before the newest.
2. **When** they unstar it (`DELETE`), **Then** it goes back to its place.
3. **Given** a student, **Then** the same works for the courses they are in.
4. **Given** a course the user does not teach or is not in, **Then** 404, and starring the same
   course twice is not an error.
5. **Given** a student who stars a course and is then removed by the teacher, **Then** the
   course is no longer listed and starring it is 404.
6. **Given** another user, **Then** they do not see the first user's favourites.

## Requirements *(mandatory)*

- **FR-001**: `q` and `sort` on the nine list endpoints; the response shape does not change
  except for `is_favorite` on teacher and student courses. No breaking change.
- **FR-002**: `PUT` and `DELETE /v1/me/favorite-courses/{course_id}` (204), for teachers and
  students; 404 when the course is not theirs.
- **FR-003**: Migration: `course_favorites (user_id, course_id, created_at)`, primary key on both,
  deleted with the user or the course; RLS on, no client access. The `unaccent` extension for
  accent-insensitive search.
- **FR-004**: One helper builds the search condition for every list.

## Success Criteria *(mandatory)*

- **SC-001**: API tests cover every scenario; the full suite passes.
- **SC-002**: A list of 500 conversations answers a search in under 300 ms on the local stack.
