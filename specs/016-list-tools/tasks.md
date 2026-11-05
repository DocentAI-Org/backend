# Tasks: Search, Sort and Favourites in Lists

**Spec**: [spec.md](spec.md)

- [x] T001 Tests first: search (accents, several words, blank), sort and 422, favourites (star,
  unstar, order, 404, idempotent, per user, removed student) on the nine lists
  (`tests/api/test_list_tools.py`)
- [x] T002 Migration (`course_favorites`, `unaccent`), model, search helper
- [x] T003 [US1] [US2] `q` and `sort` on the nine lists
- [x] T004 [US3] Favourite endpoints; `is_favorite` and favourites first in both course lists
- [x] T005 Contract note and `openapi.json`
- [x] T006 [US1] [US2] Exercise submissions too: the teacher's review page lists them with the
  conversations, so a search must reach both
- [x] T007 [US3] `favorite=true|false` on both course lists, for the "Favoritos" filter
- [x] T008 [US4] Tests first: tag CRUD, validation, assigning, `tags` on courses, `tag=` filter,
  counts, isolation and roles (`tests/api/test_course_tags.py`)
- [x] T009 [US4] Migration, models, `app/services/course_tags.py`, routes, `tags` and `tag=` on
  both course lists; contract note and `openapi.json`
