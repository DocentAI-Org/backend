# Feature Specification: Math Notation in Model Replies

**Feature Branch**: `010-math-notation`

**Created**: 2026-10-31

**Status**: Draft

**Input**: Requirement §4.4 "Math notation support (LaTeX rendered with KaTeX) if the subject is
STEM". DocentAI is not only for maths: any subject may use it, and most text has no formulas.

**Frontend**: rendering is `frontend/specs/011-math-notation`. This spec covers the backend.

## Problem

Measured on 2026-10-31 with `qwen2.5:3b` and `qwen2.5:7b` (JSON mode, 5 questions × 2 runs:
algebra, arithmetic, physics, prices in dollars, history):

- When the model writes LaTeX, it often leaves `\frac` unescaped in the JSON string; `\f` is a
  valid JSON escape (form feed), so the formula is silently corrupted (`\x0crac{1}{3}`).
- Other commands (`\(`, `\sqrt`, `\cdot`) are invalid JSON escapes: the whole reply fails to
  parse, and the student sees "the tutor is not available".
- Asked to write formulas as `\( … \)`, both models broke about half of the replies with
  formulas (over-escaped, nested JSON, dropped delimiters). Replies without formulas were fine,
  and `$` in prices was never taken as math.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — A reply with LaTeX is not lost (Priority: P1)

1. **Given** a model reply whose JSON has an invalid escape such as `\(` or `\sqrt`, **When** it
   is parsed, **Then** the text keeps the backslash and the reply is used.
2. **Given** a reply with `\frac`, `\times`, `\neq`, `\rightarrow` or `\beta` unescaped inside
   `\( … \)` or `\[ … \]`, **Then** the command is restored, not turned into a control character.
3. **Given** a reply with real line breaks or tabs outside math delimiters, **Then** they are
   kept as they are.
4. **Given** a reply with `\frac` or `\beta` unescaped and without delimiters, **Then** the
   command is still restored: form feed and backspace never appear in real text.

## Requirements *(mandatory)*

- **FR-001**: `chat_json` MUST parse replies through one function that doubles backslashes that
  do not start a valid JSON escape, and restores `\b \f \n \r \t` followed by a letter inside
  math delimiters (`\b \f` also outside them). It applies to every subject and prompt.
- **FR-002**: Math delimiters are `\( … \)` (inline) and `\[ … \]` (display) only, never `$`,
  which is common in prices.
- **FR-003**: The prompts do **not** ask the model to write LaTeX yet. The rule is added when
  the production model is chosen and passes the probe in "Model check" below.
- **FR-004**: No API or database change.

## Model check (before adding the LaTeX rule to the prompts)

Ask the candidate model, in JSON mode, the five questions above with the rule "write formulas
in LaTeX between `\(` and `\)`"; every reply must parse, every formula must keep its delimiters,
and replies without formulas must have none.

## Success Criteria *(mandatory)*

- **SC-001**: Unit tests cover FR-001 and FR-002; the full suite passes.
