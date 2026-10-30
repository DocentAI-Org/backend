# At-risk criteria — provisional v0

**Status**: provisional draft by the technical team (2026-10-30), to be reviewed and replaced by
the educational stream (requirements OQ12: who defines the criteria, and whether they are fixed or
set by the teacher). Thresholds follow the prototype (#F12 dashboard, teacher/student risk copy).

The criteria are data (table `risk_criteria`, seeded by a migration), not code: changing a
threshold or a window needs a new migration, no code change. A student is **at risk** when at least
one enabled criterion holds. The flag is not a grade and is never stored: it is computed on every
request from the activity and the learning record.

| Code | Holds when | Default thresholds | Plain-language reason (es) |
|---|---|---|---|
| `inactive` | No activity in the course for `days` days, counted from the last activity, or from joining if there is none | `days` = 7 | "Sin actividad en 9 días (la última, el 21 oct)" / "Sin actividad desde que se unió, hace 9 días" |
| `error_rate` | In the last `window_days` days, at least `min_exercises` assessed exercises and at least `rate` of them with a mistake | `window_days` = 14, `min_exercises` = 5, `rate` = 0.6 | "6 de 10 ejercicios con errores en los últimos 14 días" |

**Activity** = a message the student sent to the tutor in the course, or an exercise submission.
**Assessed exercise** = a submission whose verdict is not `not_assessed` and that is not a stub; a
mistake is `incorrect` or `partially_correct`.

## Questions for the educational stream

1. Are 7 days of inactivity meaningful for the pilot's timetable (e.g. one class a week)?
2. Should the error rate look at recurring types (the same type in the same topic) instead of any
   mistake?
3. The intended direction is that teachers set the thresholds per course wherever possible
   (OQ12). Which ones should they control, and should there be limits (e.g. at least 3 days)?
4. The requirements say every decision about a student shows its basis to that student
   (transparency rule). Should students see that they were flagged, and how is it worded?
