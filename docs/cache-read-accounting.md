# Cache-read accounting and the real input limit

## The rule

**`cache_read` does NOT count toward the input limit.** The input limit a
client must obey is the value of `limits.max_input_tokens` (uniformly
`262144` across the curated catalog), surfaced on the `413
payload_too_large` response and per-provider on `GET /v1/models`. `cache_read`
is a billing/consumption metric mined from the upstream response and is never
used in the input-limit gate.

## Why this was ambiguous (dead-run forensics)

The dead-run forensics recorded two numbers that looked contradictory:
`cache_read=262784` and `input=5641`. A client comparing them could not tell
which one bounded the request, so the true cap (`240k–275k`) was obscured.

The confusion comes from conflating three distinct things that happen to
share a word ("input" / "limit"):

| Surface | Meaning | Where it comes from |
| --- | --- | --- |
| `usage.prompt_tokens` (`input`) | Tokens in the *visible, non-cached* prompt | Upstream response `usage` |
| `usage.prompt_cache_hit_tokens` (`cache_read`) | Prompt tokens served from the provider cache, billed at a discount | Upstream response `usage` |
| `limits.max_input_tokens` | The token cap the gateway advertises as the real input limit | Curated catalog (`catalog.v1.json`) |

`cache_read` is close to the cap value (`262784` ≈ `262144`) purely because a
large cached prompt happens to be near the cap. It is a *consumption* number,
not a *limit*. Only the third row is a limit.

## How the gateway actually enforces the limit

There are two separate mechanisms, and they are orthogonal:

1. **Body size gate (bytes).** `_read_json_body`
   (`faigate/main.py:2118`) reads the raw request body and compares its length
   against `security.max_json_body_bytes` (default `1_048_576` bytes). If it
   exceeds that, it raises `PayloadTooLargeError`, which the completion
   endpoints translate into a `413`. This gate counts **bytes**, never tokens,
   and never looks at `cache_read`.

2. **Token cap in the 413 response.** When the `413` is produced,
   `_payload_too_large_response` (`faigate/main.py:347`) resolves the
   advertised token threshold from `_max_input_token_cap`
   (`faigate/main.py:327`), which reads `limits.max_input_tokens` off each
   live `ProviderBackend` and takes the max. It emits that value as both
   `body["limit"]` and the `x-faigate-request-limit` response header.

`cache_read` appears in neither mechanism. It is mined in
`faigate/providers.py:1258` (`prompt_cache_hit_tokens`), carried into the
response `_faigate.cache_hit_tokens` field (`faigate/providers.py:1265-1271`),
and reported for billing — it never reaches the gate.

## How a client derives the real input limit

A client can resolve the real input limit without guessing:

1. Call `GET /v1/models`. Each provider entry exposes `context_window`
   (native window) and `limits.max_input_tokens` (the cap)
   (`faigate/main.py:2826-2839`).
2. The real input limit is `limits.max_input_tokens`. The `context_window`
   is the provider's native window and may be larger; the cap is what the
   gateway advertises.
3. At enforcement time, a `413` response carries the same value in
   `x-faigate-request-limit` (and in the JSON `body["limit"]`), so a client
   that ignored step 1 can still read the exact threshold from the error.

There is no separate "cache budget" to reconcile: `cache_read` is a billing
bucket, refilled by the provider, not a limit the client manages.

## Code pointers

- `faigate/main.py:2118` — `_read_json_body`, the byte-based size gate behind `413`.
- `faigate/main.py:327` — `_max_input_token_cap`, reads `limits.max_input_tokens` from live providers.
- `faigate/main.py:347` — `_payload_too_large_response`, emits `x-faigate-request-limit` + `body["limit"]`.
- `faigate/main.py:2826` — `GET /v1/models`, per-provider `context_window` / `limits` / `cache`.
- `faigate/providers.py:190` — `_enrich_window_and_limits_from_catalog`, backfills the cap from the catalog.
- `faigate/providers.py:1258` — `cache_read` mined from `prompt_cache_hit_tokens` (billing only).
- `faigate/assets/metadata/catalog.v1.json:31` — `limits.max_input_tokens: 262144` (uniform across providers).
