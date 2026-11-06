# Partial comparison (2026-11-06, stopped)

Copied from `tests/eval/results/` to continue on another machine. Complete: `qwen2.5:7b`.
Partial: `qwen3:8b@none` (no quiz drafts: generation timed out at 60 s),
`qwen3.5:4b@none` (no quiz drafts), `gemma4:e4b-it-qat@none` (quiz drafts only; feedback
and tutor hit Ollama 500 errors). Not run: `granite4.2:8b`, `ministral-3:8b`, `llama3.1:8b`.

To resume, copy this folder back to `tests/eval/results/` and run the missing models; then
fold the results into `../evaluation.md` and remove this folder before the PR.

## Point 2 findings (2026-11-06, stopped mid-way)

- **gemma4 Ollama 500s**: `prediction aborted, token repeat limit reached`. At temperature 0
  the model loops on spaces inside a JSON string. Replaying the failing feedback request:
  temperature 0.2, `frequency_penalty=0.3` or `presence_penalty=0.3` each fix it. Not decided
  yet: a penalty for OpenAI-compatible providers, or a retry at 0.2 after a provider error
  (keeps spec 009's temperature 0 otherwise). Either needs re-running the feedback eval.
- **qwen3:8b quiz-draft timeouts**: not systematic. Re-run: 1 timeout in 9 generations
  (estadistica), median 22–30 s per generation. The failing request was not replayed without
  a limit yet (is it long output or a repetition loop?). Re-run quiz drafts for qwen3:
  lengua 80 %, quimica 83 %, historia 100 %, matematicas 100 %, estadistica 67 % keys
  confirmed.
- The eval now records `error_samples`, and `EVAL_DUMP_FAILED=<file>` saves failing requests
  to replay against Ollama.
