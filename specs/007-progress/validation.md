# Validation: topics of correct exercises against the local model (FR-005)

**Date**: 2026-10-31 · **Branch**: `007-progress` · **Model**: `qwen2.5:7b` (Ollama), embeddings
`bge-m3`

Progress by topic counts correct exercises only if the feedback gives them a topic. A course with
`tests/fixtures/ecuaciones.md` validated and the topics "Transponer términos", "Despejar la
incógnita" and "Paréntesis"; four exercises, each sent twice through the API.

| Exercise | First prompt change | Final prompt (topic asked first) |
|---|---|---|
| `3x = 12` → `x = 4` (correct) | ⚠️ correct, no topic | ✅ correct · Despejar la incógnita (2/2) |
| `x + 5 = 9` → `x = 4` (correct) | ⚠️ correct, no topic | ✅ correct · Despejar la incógnita (2/2) |
| `2(x - 3) = 4x + 2`, bracket not distributed | — | ✅ incorrect · procedural · Paréntesis (2/2) |
| `2(x - 3) = 4x + 2` → `x = -4` (correct) | ⚠️ judged incorrect | ⚠️ judged incorrect (execution) · Paréntesis (2/2) |

## Changes made because of this run

- Only adding "también si es correcto" to the topic field was not enough: the model kept giving
  `null` to correct answers. The topic is now the first field, asked "before correcting", and
  described as depending on the statement, not on whether the answer is right.

## Open points

- **A correct worked answer judged incorrect** (`x = -4` is right). This is the exercise
  feedback of spec 003 with a 7B model, not this feature, but it lowers the mastery score of
  students who are right; worth re-evaluating with the pilot's model.
- "x + 5 = 9" was filed under "Despejar la incógnita" rather than "Transponer términos";
  debatable, and both runs agreed.
- The bracket mistake now lands in "Paréntesis" every time, which helps the repeated-mistake
  pattern of spec 005 (its validation saw it split across topics).
