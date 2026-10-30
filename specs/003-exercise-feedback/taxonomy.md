# Error taxonomy — provisional v0

**Status**: provisional draft by the technical team (2026-10-30), to be reviewed and replaced by
the educational stream (Laura M. Ezama and Génesis M. De León, `knowledge-base/docs/responsibilities.md`).
The pilot topic is not chosen yet, so every type is **subject-independent**: the *topic* of a
mistake comes from the course's own topics (T9), the *type* says what kind of mistake it is.

The taxonomy is data (table `error_types`, seeded by a migration), not code: changing a label,
a description or adding a type needs a new migration, no code change. Codes are stable
identifiers kept in the learning record; they are never shown to users.

| Code | Spanish label | English label | What it means | Mathematics example | Language-learning example |
|---|---|---|---|---|---|
| `comprehension` | Comprensión del enunciado | Understanding the task | Misreads what is asked, the data or the conditions | Solves for *y* when the task asks for *x* | Answers in the present when the task asks for the past |
| `conceptual` | Error conceptual | Conceptual error | Misunderstands a concept, rule or definition | Believes that (a + b)² = a² + b² | Uses *ser* where the rule requires *estar* |
| `procedural` | Error de procedimiento | Procedural error | Knows the concepts but applies a wrong method, skips a step or uses the wrong order | Divides before removing the brackets | Conjugates before agreeing subject and verb |
| `execution` | Error de ejecución | Slip | A slip while carrying out a correct method: calculation, copying, spelling | 3 · 4 = 7 | "tenía" written as "tenia" |
| `incomplete` | Respuesta incompleta | Incomplete answer | Stops before the end or leaves part of the task unanswered | Finds *x* but not *y* in a system | Translates only the first sentence |
| `expression` | Expresión o notación | Expression or notation | The idea is right but it is stated, written or justified poorly (notation, units, register, missing justification) | Gives 5 instead of 5 m | Correct sentence in an inappropriate register |

## Rules for the classifier

- One type per submission: the first mistake that makes the answer wrong (the earliest step).
- `correct` answers get no type and no learning-record entry.
- When unsure between two types, the one earlier in the table wins (a conceptual error usually
  causes procedural ones).
- If the model returns a code that is not in the table, the submission is still stored with the
  verdict and explanation, but without a type and without a learning-record entry, and the event
  is logged (`outcome = unclassified`), so the taxonomy can be reviewed.

## Questions for the educational stream

1. Are six types the right granularity for the KPI "fewer recurring errors"?
2. Should `expression` count as an error in the learning record, or only as advice?
3. Once the topic is chosen, are subject-specific subtypes needed (e.g. under `conceptual`)?
4. Should the teacher be able to re-classify a submission (today they can only correct the text)?
