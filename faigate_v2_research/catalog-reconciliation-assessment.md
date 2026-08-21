# Catalog Reconciliation Assessment — faigate curated model catalog vs. binding table

> Scope: align the faigate curated provider/model catalog with the model binding table
> (23 official model IDs) before the `faigate-fix` release. This document is the
> source-of-truth reconcile map; the catalog edits and the profile-overhaul Epic both
> consume it.

- date: 2026-08-21
- binding table: `/Users/andrelange/workspaces/skillweave-temp/research/2026-08-llm-models.md`
- surfaces touched: `faigate/assets/metadata/catalog.v1.json`,
  `faigate/provider_catalog.py` (`_CATALOG` built-in fallback),
  `faigate/lane_registry.py` (`_ACTIVE_MODEL_VERSIONS`, `_MODEL_VERSION_LABELS`,
  `_CANONICAL_MODEL_LANES`, `_PROVIDER_LANE_BINDINGS`).

## 1. Architecture recap (how these surfaces relate)

- `catalog.v1.json` is the **external live catalog** (47 providers), loaded at runtime
  and merged over `_CATALOG` in `provider_catalog.py::_get_catalog_source()`.
  It carries `recommended_model` + `aliases` per provider key.
- `provider_catalog.py::_CATALOG` is the **built-in fallback** (same 47 providers).
- `lane_registry.py` holds the **canonical lane model**:
  - `_ACTIVE_MODEL_VERSIONS` — `canonical_model -> concrete model ID` (the routing map).
  - `_MODEL_VERSION_LABELS` — `canonical_model -> human label`.
  - `_CANONICAL_MODEL_LANES` — deep lane metadata keyed by `canonical_model`
    (family/cluster/quality_tier/reasoning_strength/preferred_degrades/...).
  - `_PROVIDER_LANE_BINDINGS` — `provider_name -> { canonical_model, ... }`.
- The canonical IDs are **internal** keys like `anthropic/opus-4.6`, `openai/gpt-4o`,
  `deepseek/reasoner`, `deepseek/chat`; the concrete model IDs inside
  `_ACTIVE_MODEL_VERSIONS` are what actually route.

## 2. Binding table (23 official IDs) — presence check in catalog.v1.json

Verified `PRESENT` means the ID appears as a `recommended_model` or `alias` value already.

| # | binding ID | status in catalog.v1.json |
|---|------------------------|---------------------------|
| 1 | deepseek-v4-pro | PRESENT (deepseek-reasoner) |
| 2 | deepseek-v4-flash | PRESENT (deepseek-chat) |
| 3 | gpt-5.6-sol | MISSING |
| 4 | gpt-5.6-terra | MISSING |
| 5 | gpt-5.6-luna | MISSING |
| 6 | gpt-5.5 | MISSING |
| 7 | gpt-5.5-pro | MISSING |
| 8 | o3 | MISSING |
| 9 | o3-mini | MISSING |
| 10 | o4-mini | PRESENT (openai-codex/o4-mini in lane_registry) |
| 11 | claude-opus-5 | MISSING |
| 12 | claude-sonnet-5 | MISSING |
| 13 | claude-haiku-4-5 | PRESENT (anthropic, anthropic-haiku) |
| 14 | claude-code | MISSING |
| 15 | gemini-3.1-pro | PRESENT (google, gemini-pro-high/-low) |
| 16 | gemini-3.1-flash | MISSING |
| 17 | gemini-3-flash-lite | PRESENT (google, gemini-flash-lite) |
| 18 | llama-4-maverick | MISSING |
| 19 | llama-4-scout | MISSING |
| 20 | qwen-3.6-27b | MISSING |
| 21 | qwen3-coder | MISSING |
| 22 | glm-5.3 | MISSING |
| 23 | kimi-k2.6 | MISSING |

## 3. Divergent entries (recommended_model stale) — update map

| provider key | current recommended_model | target (official) |
|---|---|---|
| anthropic | claude-opus-4-6 | claude-opus-5 |
| anthropic-claude | claude-opus-4-6 | claude-opus-5 |
| anthropic-sonnet | claude-sonnet-4-6 | claude-sonnet-5 |
| openai | gpt-4o | gpt-5.6-sol |
| openai-gpt4o | gpt-4o | gpt-5.6-sol |
| github-copilot | gpt-4o | gpt-5.5 |
| opencode | opencode/claude-opus-4-6 | claude-code |
| google-vertex | google-vertex/gemini-2.5-pro | gemini-3.1-pro |
| zai | z-ai/glm-5 | glm-5.3 |
| groq | groq/llama-3.3-70b | llama-4-maverick |
| moonshot | moonshot-v1-8k | kimi-k2.6 |
| vercel-ai-gateway | vercel-ai-gateway/anthropic/claude-opus-4.6 | claude-opus-5 |

## 4. Internal drift — lane_registry canonical model map

`_ACTIVE_MODEL_VERSIONS` currently routes these canonical keys to stale concrete IDs:

| canonical key | current active | target active | notes |
|---|---|---|---|
| anthropic/opus-4.6 | claude-opus-4-6 | claude-opus-5 | opus family moves to 5 |
| anthropic/sonnet-4.6 | claude-sonnet-4-6 | claude-sonnet-5 | sonnet family moves to 5 |
| openai/gpt-4o | gpt-4o | gpt-5.6-sol | gpt-4o canonical superseded |
| deepseek/reasoner | deepseek-reasoner | deepseek-v4-pro | keep `deepseek-reasoner` as alias (deepseek precedence) |
| deepseek/chat | deepseek-chat | deepseek-v4-flash | keep `deepseek-chat` as alias |
| google/gemini-flash | gemini-3-flash | gemini-3.1-flash | flash family moves to 3.1 |
| google/gemini-pro-high | gemini-3.1-pro | gemini-3.1-pro | already correct |
| google/gemini-pro-low | gemini-3.1-pro | gemini-3.1-pro | already correct |
| moonshot/kimi-k2.5 (canonical) | kimi-k2.5 | kimi-k2.6 | grace alias kimi-k2.5 |
| zai/glm-4.7 (canonical) | glm-4.7 | glm-5.3 | grace alias glm-4.7 |
| groq/llama-3.3-70b (canonical) | llama-3.3-70b | llama-4-maverick | grace alias llama-3.3-70b |

## 5. Missing IDs — home-lane assignment

| binding ID | family | home lane (canonical key) | action |
|---|---|---|---|
| gpt-5.6-terra | openai | openai/gpt-5.6-terra | new canonical lane + provider alias |
| gpt-5.6-luna | openai | openai/gpt-5.6-luna | new canonical lane + provider alias |
| gpt-5.5-pro | openai | openai/gpt-5.5-pro | new canonical lane + alias (gpt-5.5 pair) |
| o3 | openai | openai/o3 | new canonical lane + alias |
| gemini-3.1-flash | google | google/gemini-flash | alias on existing flash lane; update active |
| llama-4-scout | meta | groq/llama-4-scout | new canonical lane + alias |
| qwen-3.6-27b | qwen | qw/qwen-3.6-27b | new canonical lane + alias |
| qwen3-coder | qwen | qw/qwen3-coder-plus | alias on existing qwen-coder lane |

## 6. Grace-window routing (3–6 months)

Deepseek-style: old names stay valid as **aliases** that forward to the newest/canonical
concrete ID, removed only after a 3–6 month deprecation window.

- `deepseek-chat` -> `deepseek-v4-flash` (already an alias, keep for window)
- `deepseek-reasoner` -> `deepseek-v4-pro` (already an alias, keep)
- `claude-opus-4-6` -> `claude-opus-5` (add alias)
- `claude-sonnet-4-6` -> `claude-sonnet-5` (add alias)
- `gpt-4o` -> `gpt-5.6-sol` (add alias; note `gpt-4o-mini` remains a distinct lane)
- `gemini-3-flash` -> `gemini-3.1-flash` (add alias)
- `kimi-k2.5` -> `kimi-k2.6`, `glm-4.7` -> `glm-5.3`, `llama-3.3-70b` -> `llama-4-maverick` (add aliases)

## 7. Profile/system overhaul — out of scope here (Epic)

Per directive, the profile/system plumbing (preferred_degrades chains, benchmark_cluster
assignment, quality_tier/reasoning_strength per new model, pricing metadata) is a
**separate assessment + pivot**, tracked as a backlog Epic. The catalog/lane rename here
only canonicalizes IDs and wires grace aliases; it does not re-tune profiles.

## 8. Open product questions (blocking full edit)

1. Does `openai/gpt-4o` canonical collapse into the new `gpt-5.6-sol` lane, or become a
   distinct `gpt-5.5`/`gpt-5.6-sol` split with `gpt-4o` retired to alias?
2. Which old IDs keep a 3-month vs. 6-month grace window (recency-sensitive)?
3. `claude-code` home: is it a distinct `anthropic/claude-code` lane or an alias of
   `claude-opus-5`?
