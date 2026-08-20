# TASK-006 — OAuth implementation status reconciliation (roadmap vs FJ-56-169)

Provenance check run 2026-08-21 against worktree HEAD 5133807
(`exec/faigate-v2-split`). Reconciles the contradiction between
`docs/FAIGATE-ROADMAP.md` (OAuth marked "implemented", v2.1.0) and ticket
FJ-56-169 (open). Method: map every roadmap claim to concrete `file:line`
evidence, READ ONLY on code.

## Ticket location

FJ-56-169 is NOT tracked in this repo. The only reference is the batch plan
(`.skillweave/tracking-log/batch-plan-faigate-v2-split.md:16`). Its canonical
body lives in the planning repo. Per the PRD description, the ticket asserts
the OAuth status is unresolved while the roadmap claims "implemented". This
reconciliation is therefore drawn against the roadmap claim + the live code
state, not a fabricated ticket body.

## Verdict: (a) implemented + observable

The roadmap "implemented" claim is NOT premature. The OAuth wrapper is present,
wired into the runtime, and each roadmap bullet maps to code.

## Evidence map (roadmap v2.1.0 line 319-324 → code)

1. "OAuth-based authentication for managed providers" — `faigate/oauth/backend.py`
   `OAuthBackend` (full `ProviderBackend` subclass, lines 28-298): `complete()`
   at :283, `_ensure_token()` at :122, `_inject_token()` at :269,
   `_refresh_token()` at :213, helper delegation `_run_helper()` at :159.

2. Runtime dispatch on `backend: oauth` — `faigate/providers.py:93-101`
   (`create_provider_backend()` branches `backend_type == "oauth"` → imports and
   returns `OAuthBackend`). `faigate/config.py:34`
   `_SUPPORTED_BACKENDS = {"openai-compat", "google-genai", "anthropic-compat", "oauth"}`.

3. "Token store and generic OAuth backend" — `faigate/oauth/token_store.py`
   `TokenStore` (:41-173): `get`/`set`/`delete`/`is_expired`/`refresh_if_needed`,
   token persisted to `~/.config/faigate/tokens.json` with `chmod 0o600` (:82).

4. "Interactive device-code login flows (Google, Qwen, Antigravity)" —
   `faigate/oauth/cli.py`: `qwen_device_code_flow()` :187, Google device-code
   flow :961, `antigravity_login()` fallback :1044-1045, `claude_code_oauth()`
   :613, `openai_codex_login()`. `main()` dispatcher (:~1013-1100) supports
   `qwen-portal`, `claude-code`, `openai-codex`, `google-gemini-cli`,
   `google-antigravity`.

5. "Antigravity provider in registry, catalog, and lane registry (ag/ model
   family)" — `faigate/registry.py:552` (`google-antigravity` ProviderDef),
   `faigate/provider_catalog.py:648` (`google-antigravity` entry),
   `faigate/lane_registry.py:324-390` (`ag/claude-opus-4-6-thinking` and five
   more `ag/` models, `family: "google-antigravity"`) plus canonical entries at
   `:1330-1411`.

6. "claude_code_oauth() reading token from local claude CLI settings" —
   `faigate/oauth/cli.py:613` reads macOS Keychain `Claude Code-credentials`
   with fallback to `~/.config/claude/settings.json`.

7. Console entry point (observable) — `pyproject.toml:65`
   `faigate-auth = "faigate.oauth.cli:main"`.

## Honest caveats

- `faigate/assets/metadata/catalog.v1.json` does NOT carry a `google-antigravity`
  entry (grep empty), while `provider_catalog.py:648` does. Roadmap "catalog" is
  satisfied by `provider_catalog.py`; the static metadata snapshot is missing the
  entry. Metadata-completeness gap only, does not flip the verdict.
- Token acquisition delegates to the external `faigate-auth` helper (runtime
  cannot mint tokens on its own). This matches the roadmap's own scope
  (v2.1.0 "OAuth wrapper should be optional" / "interactive login clearly
  separated from automated routing core"). By design, not a gap.
- A pending human sign-off on OAuth relay quota/terms (batch-plan TASK-012) is a
  go/no-go on enabling the relay, independent of whether the code exists.

## Conclusion

Roadmap "implemented" is correct. FJ-56-169 should be marked done WITH observable
evidence; the artifact is this file + the `file:line` map above.
