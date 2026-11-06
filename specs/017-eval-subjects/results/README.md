# Partial comparison (2026-11-06, stopped)

Copied from `tests/eval/results/` to continue on another machine. Complete: `qwen2.5:7b`.
Partial: `qwen3:8b@none` (no quiz drafts: generation timed out at 60 s),
`qwen3.5:4b@none` (no quiz drafts), `gemma4:e4b-it-qat@none` (quiz drafts only; feedback
and tutor hit Ollama 500 errors). Not run: `granite4.2:8b`, `ministral-3:8b`, `llama3.1:8b`.

To resume, copy this folder back to `tests/eval/results/` and run the missing models; then
fold the results into `../evaluation.md` and remove this folder before the PR.
