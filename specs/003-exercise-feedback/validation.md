# Validation: real feedback against the local model (T008, SC-002)

**Date**: 2026-10-30 · **Branch**: `003-exercise-feedback` · **Model**: `qwen2.5:7b` (Ollama),
embeddings `bge-m3`

A course with `tests/fixtures/ecuaciones.md` validated and three topics ("Transponer términos",
"Despejar la incógnita", "Paréntesis"), checked through the API with the seeded student.

| Exercise | Expected | Result over 5 runs |
|---|---|---|
| `2(x - 3) = 4x + 2` answered `2x - 3 = 4x + 2 …` (bracket not distributed) | mistake | ✅ 5/5 detected: `incorrect` ×4, `partially_correct` ×1; type `procedural` ×3, `execution` ×2; topic "Paréntesis" ×4, "Despejar la incógnita" ×1; always cited |
| `2x + 3 = 7` answered correctly | `correct` | ✅ 5/5 with the final prompt (2/2 wrong with the first prompt, see below) |
| "¿Quién ganó el mundial de 2010?" | `not_assessed`, model not asked | ✅ 5/5, ~0.2 s |

Latency: 5–14 s per graded exercise on this machine.

## Changes made because of this run

- **False mistakes on correct answers.** The first prompt let the model grade before checking, and
  it called a correct answer `partially_correct`. The prompt now asks for a step-by-step
  `analysis` first (not shown to the student) and says not to invent mistakes.
- **"Según F1" in the explanation.** The model names fragment ids despite the prompt; the service
  now rewrites them ("Según el material") before storing the explanation (unit-tested).

## Open points for the educational stream

- The same mistake (not multiplying the 2 into the bracket) is typed `procedural` or `execution`
  depending on the run: the boundary between these two types needs a clearer definition or an
  example in the taxonomy (taxonomy.md, question 1).
- The citation points to § 3.1/§ 3.2 rather than § 3.3 "Quitar paréntesis": retrieval, not
  feedback; worth checking when the real course material arrives.
- A 7B local model explains correctly but plainly; quality should be re-checked with the pilot's
  model.
