# TASK-007 — FJ-56-173 reconciliation (health-driven catalog refresh smartness vs. implemented state)

Reconciliation run 2026-08-31 against worktree HEAD `e1f664e`
(`feature/cat-docs`). Purpose: align ticket FJ-56-173
(`feat(catalog): health-driven catalog refresh smartness — drift detection +
deprecation edges + Gate Bar surface`, canonical backlog in
`fusionaize-planning`) with what is actually implemented in this repo, so the
ticket names what is already done here and isolates the rest as separate scope,
with no point left open in both buckets.

Method: map each of FJ-56-173's four iterations (A–D) to concrete `file:line`
evidence. READ ONLY on code.

## Ticket body (source of truth for the four iterations)

FJ-56-173's canonical body lives in the planning repo
(`fusionaize-planning/.skillweave/planning/backlog/FJ-56-173-...md`), not in
this repo. Its four numbered scopes are:

- **A.** Deprecation/replacement edges in the provider-catalog schema
  (`deprecated_by`, `deprecated_at`, `replacement_reason`) + startup warning +
  opt-in `auto_migrate: true` rewrite.
- **B.** Health-signal-driven demotion source feedback: `RoutePressure` →
  `freshness_status: stale-runtime` → structured event → analytics "config
  drift" badge.
- **C.** Drift detection against provider doc URLs (`release_notes_url`, weekly
  poll, cheap-LLM summary, structured GitHub issue).
- **D.** Gate Bar drift card (render layer over the A/B fields).

## Done here (with references)

These FJ-56-173 subtopics already exist in this repo. They are **not** full
implementations of the ticket's mechanism — they are the adjacent capabilities
the ticket builds on, and they are the only parts that can be cited as already
present:

1. **Deprecation *signal* (narrower than A's replacement edge).** A schedule of
   model deprecation already flows through the catalog as `tier_status`
   (`deprecated` / `retiring`), derived from an upstream `deprecation_date`:
   - `faigate/catalog_sources/litellm.py:122-146` — `_derive_tier_status()`
     maps a past `deprecation_date` to `deprecated`, a future one to `retiring`.
   - `faigate/catalog_sources/base.py:96-97` — `NormalizedEntry.tier_status`
     and `deprecation_date` on the interchange shape.
   - `faigate/catalog_sources/merge.py:104,220-221` — `tier_status` and
     `deprecation_date` resolved through the multi-source precedence merge.
   - `faigate/assets/metadata/catalog.v1.json:525` — at least one live
     `tier_status: "expired"` entry; the schema already carries the field.

2. **Freshness flag + drift awareness (building block for B).** The
   `freshness_status` field and drift-shaped surfaces exist, but only with the
   age-based values, not the runtime-health value:
   - `faigate/assets/metadata/catalog.v1.json` — `freshness_status` present
     (35 × `fresh`, 1 × `stale`, 10 × `unknown`); no `stale-runtime`.
   - `faigate/config.py:85,600-601` — `freshness_status` normalized per lane.
   - `faigate/dashboard.py:228,491,551,570,764` — freshness surfaced in
     dashboard summaries.
   - `faigate/main.py:1178-1179` — freshness participates in route-detail
     selection.

3. **Health-signal classifier (building block for B, input side).**
   - `faigate/adaptation.py:71` — `RoutePressure` classifies request failures
     into buckets (`model-unavailable`, `auth-invalid`, `endpoint-mismatch`),
     which is the exact signal FJ-56-173 B wants to feed the demotion loop.

4. **Catalog sync / refresh plumbing (host layer for all four).**
   - `faigate/catalog_resolver.py`, `faigate/metadata_catalog_sync.py`,
     `faigate/catalog_cache.py` — the resolution/sync/ETag-cache stack the
     ticket's "refresh loop" refers to.
   - `docs/CATALOG-UPDATER.md:156-169` — sync alerts (`sync-stale`,
     `sync-invalid`, `sync-auth`) already surfaced through
     `build_catalog_alerts`.

## Remaining — separate scope, not done here

These are the ticket's *own* novel mechanisms and are **explicitly absent**
from this repo (verified by grep for each exact identifier, empty result):

- **A (full).** `deprecated_by`, `deprecated_at`, `replacement_reason` and
  `auto_migrate` do not exist. Only the deprecation *signal* above is present;
  the **replacement edge that points at the successor model** is not.
- **B (demotion loop).** No `stale-runtime` value; `RoutePressure` is not wired
  back into the catalog loop, so no health-driven demotion, no structured event
  recording the request signature, no analytics drift badge.
- **C (doc-URL drift).** No `release_notes_url` field; no weekly poll; no
  LLM-summarised GitHub-issue emission.
- **D (Gate Bar card).** No drift card; no
  `/dashboard/quotas/<brand>?tab=drift` surface.

## Open-point rule

The ticket currently leaves A–D as *proposed iterations* with no "done"
markers. This reconciliation divides them cleanly:

- **Cited as present here:** deprecation signal, freshness field, health-signal
  classifier, catalog sync plumbing (all with `file:line` above).
- **Cited as separate scope:** `deprecated_by`/`replacement_reason`/`auto_migrate`
  (A), `stale-runtime` demotion loop (B), `release_notes_url` drift (C),
  Gate Bar drift card (D).

No single item appears as both "done here" and "open": the four novel
mechanisms (A–D proper) are listed once, under *remaining*, and the adjacent
capabilities are listed once, under *done here*.

## Conclusion

FJ-56-173 is **not implemented** as a feature; what exists here is the
substrate it would build on (deprecation signal, freshness field, RoutePressure,
catalog sync). The ticket's four mechanisms remain a distinct scope and should
not be marked done. This file is the reconciled evidence map.
