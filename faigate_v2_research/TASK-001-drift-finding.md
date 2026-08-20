# TASK-001 — substitution table re-measured (live faigate 2.6.0)

Measured 2026-08-20 against running Homebrew faigate 2.6.0 @ 127.0.0.1:8090,
method `max_tokens: 1`, top-level response `model` field (per FAI-206 §probe).

## Result vs 2026-08-19 baseline

- 33 requested IDs (32 distinct, `auto` twice) → **7 distinct answerers** (unchanged).
- answered-as-self = 2 (`deepseek-v4-flash`, `deepseek-v4-pro`) — unchanged.
- Distribution DRIFTED:
  - `deepseek-v4-flash`: 21 → **19** IDs
  - `gemini-2.5-flash-lite`: 7 → **9** IDs (now carries `auto`, `coding-auto`,
    `coding-fast`, `coding-premium`, `eco`, `free`, `premium` = the auto-route
    aliases that used to land on deepseek-v4-flash)
- **Five-seat target already resolves to 5 DISTINCT models** (the premise that
  "collapses to 2" applies to the *auto-aliases*, NOT the five named seats):
  - kilo-opus → anthropic/claude-opus-4.6
  - kilo-sonnet → anthropic/claude-sonnet-4.6
  - deepseek-v4-pro → deepseek-v4-pro
  - gemini-flash → gemini-2.5-flash
  - openrouter-fallback → google/gemini-3-flash-preview

## Consequence for downstream tasks

- TASK-002 premise REFRAMED: named five seats already distinct; collapse-to-2 is
  the auto-route/alias namespace (`auto`/`coding-*`/`eco`/`free`/`premium` →
  gemini-2.5-flash-lite). "9 ROUTER_PROFILES collapse to 2" = the alias tier.
- TASK-005 (answering-model identity): top-level `model` field ALREADY carries the
  true answerer (verified: `auto`→gemini-2.5-flash-lite, kilo-opus→claude-opus-4.6).
  SW-CN-001 is thus ALREADY satisfiable via the `model` field for the named seats.
- Build note: running service is installed 2.6.0; git main is 2.6.1.
  provider_catalog.py drifts (additive Cohere entry + last_reviewed stamp, 16 lines);
  lane_registry.py + router.py are byte-identical between 2.6.0 and 2.6.1.
