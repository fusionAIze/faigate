# faigate `max_json_body_bytes` — payload-limit sizing

**Analyst session** on worktree `wt-payload-analysis`, branch `analysis/payload-limit-sizing`.
Live gateway at `http://127.0.0.1:8090` (untouched — not restarted, not reconfigured).
Live config `security.max_json_body_bytes = 1048576` (`/opt/homebrew/etc/faigate/config.yaml`).
All probes: model `deepseek-v4-flash`, endpoint `POST /v1/chat/completions`, `max_tokens: 1`.
Every probe was checked against the `X-faigate-Provider` response header — all returned `deepseek-v4-flash` (no silent substitution, i.e. no FAI-212 contamination).

## 1. Bytes per token for realistic content

Five genuinely different corpora were generated (not single-filler repeats) and sent through the gateway. Ratios are derived from a least-squares fit of wire `body_bytes` (what `_read_json_body` actually measures: `len(raw)`) against the reported `usage.prompt_tokens`.

| Corpus | bytes / token | body bytes needed for 262,144 tokens | reachable tokens at 1 MiB body |
|--------|--------------:|--------------------------------------:|-------------------------------:|
| English prose  | **6.59** | 1,728,228 (1.65 MiB) | ~157,400 |
| Chat transcript | **5.45** | 1,427,647 (1.36 MiB) | ~190,400 |
| Python source   | **4.64** | 1,215,442 (1.16 MiB) | ~225,200 |
| German prose    | **3.95** | 1,035,637 (0.99 MiB) | ~263,300 |
| JSON data       | **3.08** | 807,850 (0.77 MiB)  | ~337,300 |

The spread (3.08 → 6.59, a 2.1× range) matters far more than any single average. A single mean would mislead by overstating how far prose can reach.

### Raw measurements

| Id | Corpus | wire body_bytes | prompt_tokens | bytes/token | provider |
|----|--------|----------------:|--------------:|------------:|----------|
| r1 | EN prose | 100,787 | 15,330 | 6.57 | deepseek-v4-flash |
| r2 | EN prose | 201,460 | 30,542 | 6.60 | deepseek-v4-flash |
| r3 | EN prose | 1,040,056 | 157,409 | 6.61 | deepseek-v4-flash |
| r4 | DE prose | 101,742 | 25,746 | 3.95 | deepseek-v4-flash |
| r5 | DE prose | 1,040,001 | 263,323 | 3.95 | deepseek-v4-flash |
| r6 | Python | 104,631 | 22,572 | 4.64 | deepseek-v4-flash |
| r7 | Python | 209,146 | 44,913 | 4.66 | deepseek-v4-flash |
| r8 | Python | 1,040,001 | 225,230 | 4.62 | deepseek-v4-flash |
| r9 | JSON | 121,683 | 39,507 | 3.08 | deepseek-v4-flash |
| r10 | JSON | 1,040,021 | 337,300 | 3.08 | deepseek-v4-flash |
| r11 | Transcript | 102,486 | 18,856 | 5.44 | deepseek-v4-flash |
| r12 | Transcript | 204,854 | 37,653 | 5.44 | deepseek-v4-flash |
| r13 | Transcript | 1,039,819 | 190,361 | 5.46 | deepseek-v4-flash |

Ratios are stable across 100k → 1 MiB volumes (sub-1% drift), so the fit is trustworthy and not an artifact of repeating filler.

## 2. Reachable token ceiling under the current 1 MiB limit

Measured (not divided) with the largest body that still passes the gate (wire body ≈ 1.04 MiB, safely under the 1,048,576 byte cut):

| Corpus | largest `prompt_tokens` actually achieved |
|--------|-------------------------------------------:|
| JSON data | 337,300 |
| German prose | 263,323 |
| Python source | 225,230 |
| Chat transcript | 190,361 |
| English prose | 157,409 |

The earlier framing measured only ~125,071 tokens with a 1 MB filler probe — consistent with the single-repeated-char tokenizer collapsing tokens. Real content yields far more tokens per byte (JSON is 2.7× the filler figure; prose is still 1.3×).

## 3. What the provider catalog expects

faigate fills `/v1/chat/completions`'s payload-too-large response with a token cap from
`_max_input_token_cap()` (`faigate/main.py:368`). The catalog faigate ships
(`faigate/assets/metadata/catalog.v1.json`) advertises **`limits.max_input_tokens: 262144`**
for every provider. In the live snapshot
(`/opt/homebrew/var/faigate/provider-catalog.snapshot.v1.json`) the 41 catalogued providers
carry no `limits` block, so the operative token contract is the bundled catalog's **262,144**.

**Models whose advertised 262,144 input tokens cannot be reached under the current 1 MiB byte limit**, per measured bytes-per-token:

| Lane / advertised inputs | advertised input to reach | today's reach at 1 MiB | shortfall |
|--------------------------|--------------------------:|------------------------:|----------:|
| any prose/agent lane (deepseek-v4-flash, deepseek-v4-pro, anthropic-sonnet/*, gemini-pro-high, openai-gpt4o) | 262,144 | ~157,400 (EN prose) | **~104,700 tokens** |
| chat-transcript content, any lane | 262,144 | ~190,400 | ~71,700 |
| source code, any lane | 262,144 | ~225,200 | ~36,900 |

JSON-heavy loads (e.g. structured file dumps) and German prose do reach 262,144, but the
dominant realistic traffic — English/mixed prose in chat, transcripts, and code — cannot.

## 4. Where the wall actually is

Bracketed the accept/reject boundary (wire `body_bytes`), all served by deepseek-v4-flash:

| wire body_bytes | result |
|----------------:|:------:|
| 1,040,044 | 200 |
| 1,045,021 | 200 |
| 1,047,030 | 200 |
| **1,048,547** | **200** |
| **1,048,614** | **413** |
| 1,048,599 | 413 |
| 1,048,599–1,049,080 | 413 |

The threshold sits between 1,048,547 and 1,048,614 bytes — i.e. exactly at the configured
`1048576` (`1,048,576`). The rejection is faigate's own `PayloadTooLargeError` raised inside
`_read_json_body` (`faigate/main.py:2139`): the 413 is an `application/json`
`{"error": ..., "type": "payload_too_large"}` with the `server: uvicorn` trailer (uvicorn is the host faigate runs on — not a proxy sitting in front). No OS or reverse-proxy limit was encountered; because the boundary is byte-exact at the configured value and the error type is faigate's own, the wall is `security.max_json_body_bytes` itself.

Note on the client-facing `limit: 262144` in the 413 body: that field is the *token* cap from
`_max_input_token_cap()`, emitted for the client to react on (main.py:368-376). It is informational and does **not** describe the byte gate that rejected the request. Both my 1.04 MiB rejects and smaller rejects report `limit: 262144`.

## 5. Recommendation

Set `security.max_json_body_bytes` to **`2097152` (2 MiB)**.

Assumption: *"to reach the advertised 262,144 input tokens of faigate's routed models in the
sparsest realistic content measured — English and mixed prose at ~6.59 bytes per token —
requires ~1.73 MiB of wire body. 2 MiB leaves ~0.27 MiB of headroom over that bound while
roundly doubling the current cap."*

Supporting arithmetic (all from measurements, not guesses):

- 262,144 tokens × 6.59 B/tok (EN prose) = 1,728,228 bytes ≈ 1.65 MiB.
- 262,144 × 5.45 (transcript) = 1,427,647 bytes.
- 262,144 × 4.64 (code) = 1,215,442 bytes.
- The other corpora are already reachable at or below the current limit.

Everything the catalog advertises (262,144 input tokens) then becomes reachable for every
realistic corpus. Going beyond 2 MiB is only justified if one adopts the config lanes' own
"1M ctx" hints (e.g. deepseek-v4-flash, gemini) as the operative goal — that would need ~6.6 MiB
for prose and is a separate product decision, not a correction of a mis-sized default.

## 6. What a larger limit costs — the trade-off, argued

Raising to 2 MiB admits bodies up to ~2× the current cap to be parsed and held in memory
per request. Locally on at least one concurrent request it costs roughly the serialized
JSON string plus a decoded Python dict — a transient allocation, not a persistent pool. The
threat-model framing from the task ("binds to localhost by default") is not a dismissal, so
we state exactly what it does and does not cover:

- `_read_json_body` reads the entire body into memory with `await request.body()` before any
  limit comparison (main.py:2136-2138). The byte cap bounds the *parsing* cost — raising it
  raises worst-case peak memory per request, and increases the surface an untrusted caller
  could use to force larger in-memory allocations.
- faigate binds to `127.0.0.1` (`server.host`) and is not TLS-terminated here. A localhost-only
  listener means the only actors reaching the JSON parser are local processes and any local
  clients like OpenClaw, n8n, or shell agents. That genuinely shrinks the *remote* attacker
  surface, but it is not a guarantee: a compromised or misbehaving local process, or any local
  tool that forwards untrusted remote data into a chat request, can still drive large bodies.
  A later move to a networked listener (or an exposed tunnel) would restore the full memory-DoS
  exposure, at which point 2 MiB should be revisited.
- 2 MiB does not change max_upload_bytes (`10485760`) and does not affect streaming paths,
  which do not round-trip a full body.

Net: at localhost-only, 2 MiB is a modest, justifiable rise that buys the advertised input
capacity back. The same number deployed on a public listener would deserve a different review.

## 7. Contradictions with the framing supplied

- The framing's premise that the 1,000,000 B / 125,071 token filler probe's bytes-per-token is
  "NOT representative" is confirmed — but in both directions. Real content produces **more**
  tokens per byte than the filler (JSON ~2.7×, prose ~1.3×), so the prose reachable ceiling is
  **lower** than a naive filler extrapolation would suggest (~157K vs an extrapolated ~200K+),
  while dense content (JSON ~337K) exceeds the advertised 262,144 even today.
- The "few tokens, many bytes" frame is only true for the specific repeating-filler probe. For
  real German prose and JSON, bytes-per-byte is actually **more** crowded than the catalog
  expects, which is why JSON already reaches 262,144 and why the crown for unreachability is
  prose, not data.
- Nothing else in the framing was contradicted: the wall is byte-exact at 1,048,576, the reject
  is faigate's own, and `served_by` was deepseek-v4-flash on every probe.

## Honest gaps

- The provider snapshot used by the running gateway
  (`provider-catalog.snapshot.v1.json`) carries no per-provider `limits`, so "advertised input"
  is taken from the built-in catalog (`262144`), which faigate itself uses for the
  payload-too-large response. If a future snapshot starts advertising larger input windows
  (e.g. 1M for deepseek/gemini), the recommendation's target must be re-derived.
- Ratio stability was verified at 100k/200k/1 MiB for prose, code, transcript, and at 100k/1 MiB
  for German and JSON; tokenizers are sublinear in edge cases (many repeated tokens) that these
  corpora under-represent. Real-world documents with heavy duplication will tokenize denser
  still — which only *lowers* the bytes needed to hit a token target, so the recommendation is
  conservative on that axis.
