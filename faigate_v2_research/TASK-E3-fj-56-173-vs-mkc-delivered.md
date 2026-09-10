# TASK-E3 — FJ-56-173 vs. the MKC cut: what was delivered

Reconciliation run against worktree `feat/mkc-e2` @ `c7e1b91`. Purpose: state,
per part A–D of FJ-56-173 (`feat(catalog): health-driven catalog refresh
smartness`), whether the current codebase delivered it, delivered part of it,
or left it untouched. Honest, not flattering — the claim that matters is the
one that survives the next read.

FJ-56-173's canonical body lives in
`fusionaize-planning/.skillweave/planning/backlog/FJ-56-173-feat-...md`. Its four
scopes are:

- **A.** Deprecation/replacement edges in the provider-catalog schema
  (`deprecated_by`, `deprecated_at`, `replacement_reason`) + startup warning +
  opt-in `auto_migrate: true` rewrite.
- **B.** Health-signal-driven demotion source feedback: `RoutePressure` →
  `freshness_status: stale-runtime` → structured event → analytics "config
  drift" badge.
- **C.** Drift detection against provider doc URLs (`release_notes_url`, weekly
  poll, cheap-LLM summary, structured GitHub issue).
- **D.** Gate Bar drift card (render layer over the A/B fields).

## Verdict per part

| Part | Status | Evidence |
|------|--------|----------|
| A | **untouched** | `deprecated_by`, `deprecated_at`, `replacement_reason`, `auto_migrate` — zero occurrences in `faigate/` (grep, empty). |
| B | **untouched** | `stale-runtime` and `release_notes_url` — zero occurrences. `RoutePressure` exists but is not wired back into any catalog demotion loop. |
| C | **untouched** | no `release_notes_url` field; no weekly doc-URL poll; no LLM-summary issue emission. |
| D | **untouched** | no drift card; no `/dashboard/quotas/<brand>?tab=drift` surface. |

No FJ-56-173 mechanism — deprecation edges, runtime-health demotion,
doc-URL drift, or the Gate Bar card — is implemented. All four parts are
untouched as originally specified.

## What the MKC cut built instead

The MKC cut is a *different* scope: it moved model knowledge out of hardcoded
tables into the catalog and made broken catalog states loud. It does not
implement FJ-56-173, but it supplies a substrate that overlaps with the
ticket's *intent* (make the catalog restore trust), not its *mechanism*.

| MKC mechanism | Code | Overlaps FJ-56-173 intent |
|---------------|------|----------------------------|
| Integrity guard rejects a shrunk catalog vs. bundled baseline | `faigate/metadata_catalog_sync.py:133` | Related to B's goal "catch what the operator sees" — but by shape, not by health signal. |
| `model_not_found` instead of silent substitute 200 | `faigate/main.py:5386` | Closes the "silent drift" failure mode FJ-56-173 framed, via identity, not health. |
| Evidence gate (`belegt`/`plausibel`/`unbestaetigt`) | `faigate/catalog_views.py:86` | A new correctness layer with no FJ-56-173 counterpart. |
| Canonical identity path `[hop/]vendor/model[:variant]` | `faigate/model_identity.py:29` | No FJ-56-173 counterpart. |

**Important distinction kept honest:** the deprecation *signal* that existed
before (`tier_status`: `deprecated`/`retiring` in the catalog) is still only a
*tier status*, not FJ-56-173 A's *replacement edge*. A `deprecated_by` pointer
to a successor model does not exist. That signal predates both this ticket and
the MKC cut and is not claimed as FJ-56-173 delivery.

## Conclusion

FJ-56-173 is **not delivered** — not partially, not in one part. All four
scopes remain untouched as mechanisms. The MKC cut delivered adjacent
capabilities (integrity guard, explicit unknown, evidence gating, identity
paths) that share the ticket's *intent* but none of its *mechanisms*. The
ticket must remain open; marking it done would be overclaiming.

Prior reconciliation of this ticket is recorded in
`faigate_v2_research/TASK-007-fj-56-173-catalog-smartness-reconciliation.md`
(run against the pre-MKC code); the verdict there — "not implemented as a
feature, only the substrate" — still holds, unchanged in direction by the MKC
cut.
