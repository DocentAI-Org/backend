# Validation: question generation against the local model (T007, SC-002)

**Date**: 2026-10-31 · **Branch**: `006-adaptive-quizzes` · **Model**: `qwen2.5:7b` (Ollama),
embeddings `bge-m3`

A course with `tests/fixtures/ecuaciones.md` validated and a topic "Paréntesis" assigned to the
section "3.3 Quitar paréntesis", checked through the API in a rolled-back transaction. The
teacher asks for 5 questions. Three runs before and three after the changes below.

| Check | Result |
|---|---|
| Generated | ✅ 5/5 questions in every run, all `pending` |
| Grounded | ✅ every question cites § 3.3 "Quitar paréntesis" |
| Usable (one clearly right option, true to the material) | ✅ 4, 5 and 4 of 5 after the changes; ≥ 3 in every run (SC-002) |
| Calculations | ✅ the expansions with a single right answer are correct, e.g. `-2(4x - 5) + 3 → -8x + 10 + 3`, `-2(4 - x) → -8 + 2x` |
| Difficulty | ⚠️ 1 and 2 only, never 3, although the prompt asks to spread them |

Latency: 10–15 s per request of 5 questions on this machine (RTX 4080 Laptop), after the model
is loaded.

## Changes made because of this run

- **Options came with their letter** ("A) Quitar los paréntesis"). The interface shows its own
  letters, so a leading letter that matches the option's position is removed (unit-tested).
- **The right answer was almost always B** (11 of 15 questions). Each accepted draft is rotated
  so the right answer moves through A, B, C, D; the order of the distractors is kept
  (unit-tested). After the change the positions were spread evenly in all three runs.

## Defects the teacher review has to catch

- **More than one right option**: "Los signos cambian" and "Los signos se invierten" for the same
  question; in one run before the changes, a "which is correct" question where three of the four
  expansions were correct.
- **A question that makes no sense**: "¿Qué error se comete si se transpone -4(3x + 2) sin
  cambiar el signo…?" with "Se suma 4 a 3x + 2" as the right answer.
- **Rules not in the material**: "un signo más delante del paréntesis no cambia los signos" is
  true but the fixture does not say it.
- **Near duplicates** in the same batch (only exact repeats are dropped).

## Open points

- **Questions need the teacher's review**, as T7 intends: with a 7B model, about one question in
  five is unusable. Re-evaluate with the pilot's model.
- **No level 3 questions**: an adaptive quiz on this topic cannot go above level 2 until the
  teacher raises a question's difficulty; the quiz falls back to the nearest level, as specified.
  Worth a prompt change or asking for one level per request.

## Follow-up: levels per request (T009), 2026-10-31

The real-stack walkthrough of frontend 008 got five "Fácil" questions, so a quiz showed easy
questions while "at level 2". The request now says how many questions to write at each level
(5 → two at 1, two at 2, one at 3), and the prompt describes each level by what it asks of the
student. Same setup, three runs:

| Run | Levels | Notes |
|---|---|---|
| 1 | 1, 1, 2, 2, 3 | level 3 is a full equation, `2(3x - 4) + 5 = 11 → x = 7/3`, correct |
| 2 | 1, 1, 1, 2, 3 | the level 3 question ("qué error se comete…") has a confusing answer |
| 3 | 1, 1, 2, 2, 3 | level 2–3 questions ask to expand or find the error in an expansion |

Every run now has questions at all three levels (none had level 3 before). The quiz also changed
(T008): its level is the difficulty of the question shown, so with only easy questions it says
"Fácil" from the start and reports no change it cannot make.
