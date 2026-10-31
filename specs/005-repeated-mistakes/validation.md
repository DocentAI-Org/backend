# Validation: repeated mistakes and the review against the local model (T007, SC-002)

**Date**: 2026-10-31 · **Branch**: `005-repeated-mistakes` · **Model**: `qwen2.5:7b` (Ollama),
embeddings `bge-m3`, `RETRIEVAL_MIN_SIMILARITY=0.55`

A course with `tests/fixtures/ecuaciones.md` validated and three topics ("Transponer términos",
"Despejar la incógnita", "Paréntesis"), checked through the API in a rolled-back transaction.
The student sends the "bracket not distributed" exercise until a submission carries
`repeated_mistake`, then asks for its review. Three runs per prompt version.

| Check | Result |
|---|---|
| Pattern | ✅ 3/3: `repeated_mistake` on the third mistake of the same type and topic (after 4–5 submissions, see below) |
| Review grounded | ✅ 3/3 `answer`, citing § 3.3 "Quitar paréntesis" |
| Explanation | ✅ correct and plain in 3/3 ("quita los paréntesis multiplicando cada término…") |
| Practice | ⚠️ two statements every time, but often equations with no solution or identities, e.g. `5(2x - 1) = 10x - 5` |
| Worked example | ⚠️ present in 2/3 with the final prompt, but mathematically wrong (it reaches `0 = 6`) |

Latency: 7–14 s per review on this machine; asking again is instant and free.

## Changes made because of this run

- **The worked example was always null.** The prompt allowed it; it is now required unless the
  material has no rule to apply.
- **The worked example solved the student's own exercise** (`2(x - 3) = 4x + 2 → 2x - 6 = …`).
  The prompt now forbids it, and the service drops any example or practice item that contains
  the student's equation (unit-tested), so it holds even when the model ignores the prompt.
- **"de el material".** Replacing fragment ids left "de el material"; it is now contracted to
  "del material" (also in exercise feedback; unit-tested).

## Open points

- **Generated maths is unreliable with a 7B model.** Agreed with the product owner to keep the
  worked example and practice and re-evaluate them with the pilot's model before students use
  them. The teacher sees the same review.
- **The topic of a mistake is unstable** (exercise feedback, spec 003): the same bracket mistake
  is filed under "Despejar la incógnita" or "Paréntesis", which splits the pattern and delays it.
  Worth fixing in the feedback prompt or the taxonomy guidance.
- Copy detection only finds equations (`=`); a statement without one is not protected.
