# Evaluation: classification of exercise mistakes

Run with `uv run pytest -m eval -s` (Supabase + Ollama). Cases: `tests/eval/feedback_cases.json`.

## Baseline (2026-10-31, before any change, on main before specs 006–008 merged)

Model `qwen2.5:7b`, 3 runs per case, 12 cases.

| Metric | Result |
|---|---|
| Verdict | 13/36 (36 %) |
| Type (mistakes) | 13/27 (48 %) |
| Topic (mistakes) | 7/27 (26 %) |
| Consistent cases | 10/12 (83 %) |

| Case | Seen (verdict, type, topic) × runs |
|---|---|
| `brackets-not-distributed` | incorrect, procedural, Despejar la incógnita ×3 |
| `minus-before-brackets` | not_assessed, —, — ×2; partially_correct, procedural, Paréntesis ×1 |
| `brackets-correct` | not_assessed, —, — ×3 |
| `transpose-keeps-sign` | incorrect, procedural, Transponer términos ×3 |
| `transpose-negative-term` | correct, —, — ×3 |
| `transpose-correct` | not_assessed, —, — ×3 |
| `subtract-instead-of-divide` | not_assessed, —, — ×3 |
| `division-inverted` | incorrect, procedural, Despejar la incógnita ×3 |
| `divide-correct` | not_assessed, —, — ×3 |
| `slip-when-transposing` | incorrect, execution, Despejar la incógnita ×3 |
| `slip-when-dividing` | not_assessed, —, — ×3 |
| `stops-halfway` | correct, —, — ×2; not_assessed, —, — ×1 |

## Reading of the baseline

- **The main problem is retrieval, not classification.** 16 of 36 answers are `not_assessed`:
  short statements ("Despeja la incógnita: 3x = 12") stay under `RETRIEVAL_MIN_SIMILARITY=0.55`,
  so the model is never asked. Fix this first (e.g. a lower threshold or a query built from the
  statement and the answer for exercises), then measure type and topic again.
- When the model is asked, it is consistent across runs (temperature 0.2 already), but the topic
  follows the last step rather than the wrong one (`brackets-not-distributed` →
  "Despejar la incógnita"; `slip-when-transposing` → "Despejar la incógnita").
- Two wrong verdicts: `transpose-negative-term` and `stops-halfway` graded `correct`.

## Next steps (tasks T002–T005)

1. Retrieval for exercises (new finding; add to the spec as US3 before coding).
2. Topic per fragment from confirmed assignments + "topic of the wrong step" rule.
3. Feedback temperature 0 and decision rules between types.
4. Re-run and record here.

## Baseline again after rebasing on main (2026-10-31)

Main changed the prompt (spec 007 T006: topic first, also for correct answers). `qwen2.5:7b`:

| Metric | Result |
|---|---|
| Verdict | 10/36 (28 %) |
| Type (mistakes) | 8/27 (30 %) |
| Topic (mistakes) | 7/27 (26 %) |
| Consistent cases | 7/12 (58 %) |

Still 12/36 `not_assessed`. Similarities of each case against the four sections of
`ecuaciones.md` (bge-m3, statement + answer) are 0.47–0.68 for the top section, and
"3.3 Quitar paréntesis" scores 0.40–0.47 even on bracket exercises.

## After T002–T004 and T006 (2026-10-31)

Exercise threshold 0.40 (US3), topic per fragment, temperature 0, topic chosen after the wrong
step, ordered type rules.

| Metric | Baseline (7b) | `qwen2.5:7b` | `qwen2.5:3b` | Target |
|---|---|---|---|---|
| Verdict | 28 % | 27/36 (75 %) | 30/36 (83 %) | ≥ baseline ✅ |
| Type (mistakes) | 30 % | 12/27 (44 %) | 12/27 (44 %) | ≥ 80 % ❌ |
| Topic (mistakes) | 26 % | 21/27 (78 %) | 21/27 (78 %) | ≥ 90 % ❌ |
| Consistent cases | 58 % | 12/12 (100 %) | 12/12 (100 %) | ≥ 80 % ✅ |

| Case | `qwen2.5:7b` | `qwen2.5:3b` |
|---|---|---|
| `brackets-not-distributed` | incorrect, procedural, Despejar la incógnita | incorrect, procedural, Paréntesis |
| `minus-before-brackets` | incorrect, execution, Paréntesis | incorrect, procedural, Paréntesis |
| `brackets-correct` | correct | correct |
| `transpose-keeps-sign` | partially_correct, procedural, Transponer términos | incorrect, procedural, Transponer términos |
| `transpose-negative-term` | correct ❌ | correct ❌ |
| `transpose-correct` | not_assessed ❌ | correct |
| `subtract-instead-of-divide` | incorrect, comprehension, Despejar la incógnita | incorrect, procedural, Transponer términos |
| `division-inverted` | incorrect, comprehension, Despejar la incógnita | incorrect, execution, Despejar la incógnita |
| `divide-correct` | correct | correct |
| `slip-when-transposing` | incorrect, execution, Despejar la incógnita | partially_correct, incomplete, Transponer términos |
| `slip-when-dividing` | incorrect, execution, Despejar la incógnita | correct ❌ |
| `stops-halfway` | correct ❌ | incorrect, procedural, Paréntesis |

All runs of a case agree in both models (shown once).

### Reading

- Retrieval and temperature fixed the noise: every case is stable, and verdicts went from 28 % to
  75–83 %.
- Type is the open gap. 7b reads a wrong operation ("subtract instead of divide", "divide the
  wrong way round") as `comprehension`; 3b sees slips as `incomplete` or misses them. The errors
  are wrong verdicts at least as much as wrong types (`transpose-negative-term`,
  `slip-when-dividing`, `stops-halfway` graded `correct`).
- `qwen2.5:3b` scores like 7b on this set and is faster; it is the local development model for
  now (`.env` only; the default stays 7b).

### Next steps

1. Type: examples per type in the prompt (subject-independent) or one short worked example per
   type; re-measure.
2. Wrong `correct` verdicts: make the analysis check the final result by substitution explicitly.
3. Grow the case set (only 12 cases; one case is 3 of 27 mistakes, about 11 points).

## End-to-end review (2026-10-31)

`qwen2.5:3b`, on top of the adaptation fix (backend PR #20; before it, adapted exercises came
back `not_assessed`). The runner uses one student for every case, so after three mistakes of a
type the adaptation note of spec 013 is in the prompt for the rest of the run.

| Variant | Verdict | Type | Topic | Consistent |
|---|---|---|---|---|
| Adaptation fix only | 31/36 (86 %) | 13/27 (48 %) | 21/27 (78 %) | 9/12 (75 %) |
| + analysis and explanation in "tú" | 23/36 (64 %) | 14/27 (52 %) | 21/27 (78 %) | 11/12 (92 %) |
| + explanation in "tú" only (kept) | 30/36 (83 %) | 16/27 (59 %) | 23/27 (85 %) | 10/12 (83 %) |

Asking the hidden analysis in the second person made the model grade correct answers as
mistakes; only the explanation rule is kept. `qwen2.5:3b` still often writes "el estudiante";
a stronger model is expected to follow the rule.

Follow-up done: each case now has its own student, so the adaptation note never enters the
evaluation (`EVAL_RUNS` must stay ≤ `REPEATED_MISTAKE_COUNT`).

## One student per case (2026-10-31)

`qwen2.5:3b`, `main` with the feedback fixes; no adaptation note in any run.

| Metric | Result |
|---|---|
| Verdict | 33/36 (92 %) |
| Type (mistakes) | 18/27 (67 %) |
| Topic (mistakes) | 21/27 (78 %) |
| Consistent cases | 12/12 (100 %) |

Compared with the runs above, the adaptation note costs this model accuracy even in its right
place (verdict 86 % with it, 92 % without). Measure it again when choosing the production model;
if it still costs accuracy, the note could go to the chat only, or be shortened.
