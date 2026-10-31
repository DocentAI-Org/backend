# Feature Specification: Model Providers per Task

**Feature Branch**: `014-llm-providers`

**Created**: 2026-10-31

**Status**: Draft

**Input**: User description: "Models from different providers, such as OpenAI and Anthropic, and of
course open-source models through Ollama, must be easy to use." Requirements §4.3: the model
and provider change through configuration without code changes; a cheap model for the student
chat and a stronger one for occasional tasks. Choosing the production model (next step) needs
the evaluation to run against several providers.

## Decisions

- Configuration lives in environment variables (requirements §4.2: secrets only there). No
  admin screen: API keys never reach the database.
- One default provider and model; each **task** can override them: `chat` (tutor), `feedback`
  (exercise feedback), `review` (mistake review), `questions` (quiz question drafts).
- Providers: `ollama` (local, OpenAI-compatible endpoint), `openai` (OpenAI or any compatible
  API through `OPENAI_BASE_URL`), `anthropic` (native Messages API).
- Embeddings: `ollama` or `openai` only (Anthropic has no embeddings API). Changing the
  embedding model needs re-processing the material, as today.

## Provider differences the code absorbs

- **Anthropic** takes no `temperature` (the API rejects it since 2026-10-21) and no prefill;
  the reply is asked as JSON by the prompts (already the case) and parsed tolerantly (code
  fences, text around the object). Reasoning depth is set with an optional per-task `effort`
  (`low`…`max`). A refusal (`stop_reason: refusal`) is an `LLMError`, like a provider failure.
  With `LLM_ANTHROPIC_FALLBACKS=default` (the default), a refused request is re-run by the API
  on a fallback model, on the models that support it.
- **OpenAI-compatible** keeps `response_format: json_object` and the temperature.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — The team switches provider or model by configuration (Priority: P1) 🎯

1. **Given** `LLM_PROVIDER=anthropic` and `LLM_MODEL=claude-haiku-5-5`, **When** the tutor
   answers, **Then** the Anthropic Messages API is called with that model, the system prompt and
   no temperature, and the JSON reply is used as today.
2. **Given** `LLM_FEEDBACK_PROVIDER=openai` and `LLM_FEEDBACK_MODEL=…`, **Then** exercise
   feedback uses OpenAI while the other tasks keep the default.
3. **Given** the defaults, **Then** everything runs on local Ollama as before; the old variable
   names (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_CHAT_MODEL`) keep working.
4. **Given** `LLM_EMBEDDING_PROVIDER=anthropic`, **Then** the app refuses to start with a clear
   message.

### User Story 2 — Costs follow the model used (Priority: P2)

1. **Given** a price for a model in `LLM_PRICES` (or the built-in table for current Claude
   models), **When** an interaction is logged, **Then** its estimated cost uses that model's
   price; models without a price fall back to `LLM_PRICE_INPUT/OUTPUT_PER_MTOK`.

## Requirements *(mandatory)*

- **FR-001**: `chat_json(system, messages, temperature, task)`; the four call sites pass their
  task. The interaction log keeps the model that answered.
- **FR-002**: Provider errors, timeouts, refusals and empty replies raise `LLMError`.
- **FR-003**: The health check reports the default chat provider.
- **FR-004**: No API or database change.

## Success Criteria *(mandatory)*

- **SC-001**: Unit tests cover routing, both adapters (with fake SDK clients) and the settings;
  the full suite passes; the evaluation runs with any provider (`LLM_FEEDBACK_*`).
