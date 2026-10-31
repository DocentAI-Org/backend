# Evaluation: classification of exercise mistakes

Run with `uv run pytest -m eval -s` (Supabase + Ollama). Cases: `tests/eval/feedback_cases.json`.

## Baseline (2026-10-31, before any change)

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
