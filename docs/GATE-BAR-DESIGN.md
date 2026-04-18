# Gate Bar & Quota Widget Redesign

**Status:** Draft — v2.3.0 roadmap input.
**Scope:** (a) CodexBar-inspired refresh of the `/dashboard/quotas` widget in
fusionAIze brand, (b) new `fusionAIze Gate Bar` macOS menubar companion app,
(c) rename "Usage Dashboard" → "Cockpit" and point it at the Operator Cockpit
in the default browser.

## 0. Design-Thinking Lens

This doc is written under a design-thinking discipline, not as a
feature-port of CodexBar. Every decision is checked against the operator's
actual day, and every element that doesn't pull its weight gets cut. The
lens stays visible here so future edits stay honest.

### Empathize — the operator's day

The operator is running faigate locally. A typical moment:

> "I'm halfway through a Claude Code session, about to hand off a long
> review task. Before I kick it off, am I going to hit the 5-h window and
> get bumped to weekly overflow? Is there a cheaper lane I'm not using?
> Wait — did my Kilo credits already expire?"

That moment takes 3–5 seconds of glancing before real work resumes. The
widget either answers it fast, or it fails.

### Define — the widget's single job

> **Tell the operator, in one glance, whether they're in trouble on any
> active provider — and quietly hint at value they're leaving on the
> table.**

Everything else (adding providers, tuning lanes, exploring trends, auditing
routes) is a longer-lived task and belongs in the browser Cockpit. The
widget is a **glance surface, not a workspace.**

### Decision rules we apply to every element

1. **Value ≥ noise.** If an element doesn't change a decision an operator
   would make, it doesn't ship. No vanity counters, no decorative charts.
2. **Scan before read.** Position, colour, and size must carry the meaning
   before the operator reads a single word. Text is backup, not the
   channel.
3. **Active over available.** Active providers come first, always.
   Catalog/available-to-add comes second and never pushes active below the
   fold on a 13" laptop.
4. **Glance first, drill-down on demand.** Default views answer the
   3-second question. Per-brand quick-view answers the 30-second question.
   Cockpit answers the 5-minute question.
5. **Widget ≠ workspace.** No wizards, no forms, no writes. Every setup
   flow is a deep link to Cockpit.
6. **Decision-ready data.** Anything we surface has to be enough to act on
   — quota numbers show pace, catalog entries show pricing, drill-downs
   show which client is burning the budget. Half-data is worse than no
   data because it invites a second tab.

Each of the following sections points back to these rules where it matters.

---

## 1. Naming Pivot — brand names, not company names

Today the quota widget groups by `provider_group`, which uses company/engine
keys (`anthropic`, `openai`, `deepseek`, …). That mirrors the router's
internal provider IDs but is not how operators think about their
subscriptions.

Going forward the operator-facing surface uses **product/brand names**, the
same way CodexBar does:

| Current `provider_group` | New display `brand`     | What it means to the operator             |
|--------------------------|-------------------------|-------------------------------------------|
| `anthropic`              | **Claude**              | Claude Pro subscription + Anthropic API   |
| `openai`                 | **Codex**               | ChatGPT / Codex CLI subscription          |
| `gemini`                 | **Gemini**              | Google AI Studio free tier                |
| `deepseek`               | **DeepSeek**            | DeepSeek API credits                      |
| `kilocode`               | **Kilo Code**           | Kilo starter credits                      |
| `openrouter`             | **OpenRouter**          | OpenRouter credits + free daily           |
| `qwen`                   | **Qwen**                | Qwen free daily via OAuth                 |
| `blackbox`               | **Blackbox**            | Blackbox subscription + API               |
| *(future)*               | **Cursor**, **Droid**, **Antigravity**, **Copilot** | CodexBar parity roster |

### Catalog change

Introduce a `brand` field at package level (not a new grouping key). The
existing `provider_group` keeps routing-side semantics; `brand` is purely the
display label.

```jsonc
"anthropic-pro-5h-session": {
  "provider_id": "claude-sonnet-4.5",
  "provider_group": "anthropic",      // unchanged — routing key
  "brand": "Claude",                  // NEW — display label
  "brand_slug": "claude",             // NEW — CSS class / asset key
  "name": "Pro · 5-h session",        // package label within the brand card
  ...
}
```

Rules:

- When `brand` is absent, fall back to a lookup table keyed on
  `provider_group` (same table as above). No catalog migration breakage.
- The widget groups by `brand` (brand-slug, really), not `provider_group`.
  Two packages with the same `brand` render as subsections of one card, even
  if their `provider_group` differs (e.g. Claude Pro + Anthropic API both
  belong under the `Claude` card).
- Router code stays on `provider_group` / `provider_id`. Nothing in the
  scoring path reads `brand`.

---

## 2. What to adopt from CodexBar

Source: `docs/provider.md` in `steipete/CodexBar` + the four UI screenshots
the operator attached as `~/Desktop/codex-bar.html`.

> **Key divergence from CodexBar:** CodexBar is a tab-switcher — you click
> Codex/Claude/Cursor/Gemini to see one provider at a time. That works for a
> menubar popover where space is tight. The **fusionAIze quota widget stays
> an all-providers-at-a-glance overview**; every active brand is visible
> simultaneously in a scrollable stack of brand cards, clustered by brand.
> The Gate Bar menubar popover can afford either layout, but the default is
> still "show every active brand at once, scroll if needed" because our
> operator routinely checks "how am I doing on everything right now?".
> Tabs/filters are a future opt-in, not the default.

### Keep (maps cleanly onto faigate)

1. **Brand clustering (not tabs).** CodexBar clusters by brand via tabs;
   fusionAIze clusters by brand visually — one card per brand, all cards
   rendered together. A brand with multiple packages (e.g. Claude has five)
   stacks them as sub-rows inside the same card so the operator sees the
   whole brand situation in one glance.
2. **Per-brand detail panel with two stacked progress bars.**
   - top bar: "Session" (5-h window) or "Credits" if no session applies
   - bottom bar: "Weekly" (7-day window) or "Daily" for free tiers
   - thin red tick marker at the "pace" threshold — see §4.
3. **"Pace" indicator.** Expected-vs-actual usage at this point in the
   window. CodexBar prints "Pace: +2.3 %" in small type. We adopt it because
   it's the single most useful at-a-glance cue for a quota that resets.
4. **Identity line per brand.** CodexBar shows email + plan + login method,
   siloed per provider. We already have this via `identity` in the OAuth
   token store — surface `plan · login method` (e.g. "Pro · OAuth",
   "API · env var `ANTHROPIC_API_KEY`").
5. **Menubar percentage summary.** For Gate Bar: the menubar shows the
   tightest window across all brands as `fAI · 83 %` with a colour dot.
   CodexBar uses two stacked micro-bars as an icon — we copy the concept but
   draw it with the fusionAIze glyph rather than a generic bar.
6. **Refresh-interval picker.** Manual / 1 / 2 / 5 / 15 min. CodexBar default
   is 5 min; we keep that.
7. **"Identity stays local" posture.** All detection happens on-device; no
   data leaves the machine. This is already how faigate behaves — call it
   out explicitly in the Gate Bar about-box.

### Skip / adapt

- **CodexBar scrapes OpenAI's web dashboard via Safari/Chrome cookies.** We
  do not scrape. If a browser-cookie source is ever added, it goes behind an
  explicit opt-in and a per-provider toggle, never on by default.
- **CodexBar's `UsageProvider` compile-time enum.** We already have a
  data-driven catalog. Keep it data-driven; do not hard-code a provider enum
  in the Swift app either — the Gate Bar fetches its brand roster from the
  running gateway at `GET /api/quotas` (see §5).
- **macOS 15+ requirement.** We target **macOS 14+ (Sonoma)** so a two-year-
  old Intel MacBook Pro still runs the menubar. SwiftUI surfaces used: the
  subset that ships in the Sonoma SDK (no `MeshGradient`, no `Observable`-only
  APIs — use `ObservableObject`).
- **CLI-only fallbacks.** CodexBar falls back to `codex /status` parsing. We
  already have first-class quota capture in the gateway (`quota_poller.py`
  + header capture + local count); the Gate Bar is a pure consumer of the
  gateway's `/api/quotas`. No PTY, no CLI parsing in the Swift code.

---

## 3. Quota widget refresh (in the existing dashboard)

The widget lives at `/dashboard/quotas` and **remains the one-page overview
of every active faigate provider** — that's its entire reason for existing.
The refresh keeps everything inside the existing HTML shell and fusionAIze
brand CSS. No framework change, no new asset pipeline. No tabs, no filters
by default — just tighter clustering by brand.

Layout is a responsive grid: 1 column ≤ 640 px, 2 columns 640–1100 px, 3
columns ≥ 1100 px. Every active brand is rendered as one card and all cards
are visible on arrival. Inactive brands (credential missing) appear only in
the "Skipped" block at the bottom, never in the main grid.

### Visual spec (brand-card layout)

```
┌─────────────────────────────────────────────────────────────┐
│  Claude                                        Pro · OAuth   │  ← brand header
│  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░▓▓▓░░░░  83 %    ·  Pace +2 %│  ← session bar
│  Session · resets in 2 h 14 min                              │
│  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░  102 %               │  ← weekly bar
│  Weekly · rolled over to monthly overflow (17 € / 17.26 €)   │
│                                                              │
│  [ Cockpit ↗ ]   [ Refresh ]   last updated 12 s ago         │
└─────────────────────────────────────────────────────────────┘
```

- **Colours:** existing fusionAIze palette. Progress fill uses the accent
  gradient below 80 %, warn-orange 80–100 %, alert-red above 100 %.
- **Pace marker:** a 2-px vertical tick inside the bar at the expected
  position (elapsed fraction of the window). If actual > expected the tick
  is behind the fill; ahead of the fill means "under pace".
- **Brand header:** brand wordmark-style `<h3>` + right-aligned
  identity line (`plan · login method`).
- **Stacked sub-packages:** if a brand has more than one package (Claude has
  five), render them as stacked rows within one card, each with its own bar.
  CodexBar doesn't do this — we do because operators want the overflow
  package visible under the same umbrella as the Pro session.
- **Skipped (no credential):** the "Skipped packages" block already
  exists at the bottom of the widget; keep it, but label with the brand
  (e.g. "Qwen — no OAuth token found").

### Cockpit link (rename from "Usage Dashboard")

The button currently reads "Usage Dashboard" and links to the widget itself.
Replace with a **Cockpit** button in the brand-card footer that opens the
fusionAIze Operator Cockpit in the system's default browser:

```html
<a class="button--ghost" href="https://cockpit.fusionaize.ai/"
   target="_blank" rel="noopener">Cockpit ↗</a>
```

The cockpit URL is read from `FAIGATE_COCKPIT_URL` (env / config), defaulting
to the public operator cockpit URL. `target="_blank"` + `rel="noopener"` is
the correct way to hand off to the OS default browser from the built-in
dashboard — no custom URL handler required.

### Page composition — active first, catalog second

The widget page is **two blocks, in this fixed order**:

1. **Active providers** (the clustered brand-card grid from the visual spec
   above). This is the primary surface — "what am I working with right
   now?". Every brand with a usable credential renders a card here.
2. **Catalog · available to add** (new, mini). A compact list derived from
   the shared fusionaize-metadata catalog, filtered to brands the operator
   does **not** yet have active. Intentionally small — one line per brand,
   no bars, no numbers, no setup UI inside the widget.

That ordering is deliberate: the overview always answers "how am I doing?"
first, and only then whispers "here's what else exists". The catalog block
never pushes the active grid below the fold on a typical laptop viewport.

The absorbed "Skipped packages" block stays as a third tier at the bottom —
packages the operator has in their local catalog but the credential is
missing/placeholder. Distinct from "catalog available to add", because
skipped entries are one env-var away from becoming active, whereas catalog
entries need a full onboarding flow.

### Catalog · available to add (mini block)

**Why this block exists (design-thinking check):** the operator cannot make
a "should I wire this up?" decision from a brand name alone. A brand name
without pricing is noise (rule 1: *value ≥ noise*). A brand name **with**
pricing and the quota shape is decision-ready (rule 6: *decision-ready
data*) — the operator sees "Cursor · Pro $20/mo · 500 fast/mo" and knows
in under two seconds whether it's worth the 3-minute onboarding in
Cockpit. The block's job is one thing: turn discovery into a fast yes/no.

Visual:

```
┌─────────────────────────────────────────────────────────────┐
│  Available to add                              from catalog │
│                                                             │
│  Cursor       Pro · $20/mo · 500 fast req/mo      Add in    │
│                                                   Cockpit ↗ │
│  Droid        free · 50 req/day                   Add in    │
│                                                   Cockpit ↗ │
│  Antigravity  early access · 200 free credits     Add in    │
│                                                   Cockpit ↗ │
│  Copilot      Individual · $10/mo · unlimited     Add in    │
│                                                   Cockpit ↗ │
│  Mistral API  pay-as-you-go · from $0.25 / 1M tok Add in    │
│                                                   Cockpit ↗ │
│  Groq         free tier · 14 400 req/day          Add in    │
│                                                   Cockpit ↗ │
│                                                             │
│  … 3 more · see all in Cockpit ↗                            │
└─────────────────────────────────────────────────────────────┘
```

Row grammar — three scannable columns, in this order:

1. **Brand** (bold, brand colour accent at 60 % opacity so it reads softer
   than an active card).
2. **Tagline** = `tier · price · quota shape`. Designed to parse
   left-to-right in a single glance:
   - *tier*: `free`, `Pro`, `Individual`, `early access`, `pay-as-you-go`
   - *price*: `$X/mo`, `free`, `from $X / 1M tok`, `X€ signup credits`
   - *quota shape*: `N req/day`, `N fast req/mo`, `unlimited`,
     `5-h session + monthly`, `OAuth free daily`
   Any component can be omitted when genuinely absent (e.g. early-access
   with no public price → `early access · 200 free credits`). Never pad.
3. **CTA**: the same `Add in Cockpit ↗` link on every row — consistent CTA
   means the eye doesn't re-orient per row.

Rules:

- **Data source:** the shared catalog at
  `fusionaize-metadata/packages/catalog.v1.json` (already synced locally).
  We already read this file — the widget just filters it by
  `brand_slug NOT IN active_brands`.
- **Max 6 rows** by default; anything beyond collapses behind
  "… N more · see all in Cockpit ↗". The widget is not a catalog browser.
- **New field:** `catalog_tagline` on the first package of each brand.
  Authored (not auto-generated) — we want the copy to be tight and
  comparable across brands. Falls back to `name` only as an emergency; a
  missing tagline is a catalog bug worth fixing, not a rendering
  fallback path we're proud of.
- **No setup UI in the widget.** Every row's CTA is the same: "Add in
  Cockpit ↗", which opens
  `${FAIGATE_COCKPIT_URL}/providers/add?brand=<brand_slug>` in the default
  browser. The onboarding flow (keys, OAuth, model picks, lane config)
  lives in Cockpit and only in Cockpit.
- **No write paths** in the dashboard. The widget does not touch the
  catalog file, does not write env vars, does not invoke wizards. Anything
  that mutates state belongs to Cockpit.

**Test criterion (design-thinking closing loop):** when we prototype,
watch the operator look at a catalog row and ask "what can I do with this
and what does it cost?". If the answer takes more than 2 seconds of
reading, the tagline is wrong — shorten it, don't enlarge the row.

This is the design contract for the dashboard going forward:

> The built-in dashboard is a **glance surface** for active providers plus
> a mini pointer at the catalog. All deeper data views and every flow that
> adds, edits, or configures a provider run in the browser Cockpit.

### Per-brand detail view (drill-down from a card)

Clicking a brand card navigates to `/dashboard/quotas/<brand_slug>` — a
"quick view" that stitches together the four pieces an operator actually
needs when they zoom in on a single brand. It is intentionally a *subset* of
the Operator Cockpit, not a competitor to it; Cockpit stays the deep
analysis surface.

Layout (single column, brand-themed accent):

```
┌─────────────────────────────────────────────────────────────┐
│  ← Overview                          Claude                 │
├─────────────────────────────────────────────────────────────┤
│  QUOTA                                                      │
│  (identical block to the brand card on the overview —       │
│   session / weekly / credits bars, pace, identity)          │
├─────────────────────────────────────────────────────────────┤
│  CLIENTS (last 24 h)                                        │
│  ▇▇▇▇▇▇ Claude Code          64 %  · 412 req                │
│  ▇▇▇▇   Cursor               22 %  · 141 req                │
│  ▇▇     faigate-stats CLI     9 %  ·  58 req                │
│  ▇       aider                 5 %  ·  31 req                │
├─────────────────────────────────────────────────────────────┤
│  ROUTES                                                     │
│  claude-sonnet-4.5   → anthropic (direct)       412 req     │
│  claude-haiku        → anthropic (direct)       141 req     │
│  claude-opus         → openrouter (fallback)     18 req     │
├─────────────────────────────────────────────────────────────┤
│  ANALYTICS (sparkline, last 24 h)                           │
│  requests   ▁▂▂▃▅▆▇█▇▆▅▃▂▂▁▂▃▅▆▇█▇▆▅             642        │
│  tokens     ▁▂▃▄▅▆▇███▇▆▅▄▃▂▁▂▃▄▅▆▇██          1.8 M        │
│  cost       ▁▁▂▂▃▃▄▅▆▆▇▇▇▆▅▄▃▃▂▂▁▁▂▂          2.14 €        │
│                                                             │
│  [ Open in Cockpit ↗ ]                                      │
└─────────────────────────────────────────────────────────────┘
```

Blocks in order of operator priority:

1. **Quota** — the same brand card from the overview, full-width. No new
   data fetch; reuses `/api/quotas`.
2. **Clients** — the top-N client apps that hit this brand in the last
   24 h. Data source: `client_app` tag on the SQLite request log (already
   captured via Anthropic-bridge + OpenAI-compat user-agent sniffing).
   New endpoint `GET /api/quotas/<brand_slug>/clients?window=24h`.
3. **Routes** — routing lanes that resolved to this brand in the same
   window, showing model ID, provider the lane selected, and whether it
   was `direct` / `fallback` / `cost-optimized`. Data source: the route
   decision log we already write. New endpoint
   `GET /api/quotas/<brand_slug>/routes?window=24h`.
4. **Analytics (small charts)** — three sparklines: requests, tokens, cost.
   uPlot is already on the dashboard bundle; reuse it at `height: 40px`.
   Data source: the same SQLite log, bucketed into 60 × 24-min bins.
   New endpoint `GET /api/quotas/<brand_slug>/analytics?window=24h`.
5. **Open in Cockpit ↗** — a brand-scoped Cockpit link
   (`${FAIGATE_COCKPIT_URL}/providers/<brand_slug>`) for when the operator
   needs the full analysis view.

The quick view is a **read-only composite**; it writes nothing, it is safe
to reload, and it degrades gracefully if any of the three new endpoints
fails (the section just collapses with an "unavailable" hint).

### Default landing view (user-configurable)

Operators have different "home screens" — one person opens the dashboard to
check Claude quota first, another always wants the full overview.

Add a persisted setting `dashboard.quotas.default_view` with three options:

| Value                | Behavior on `/dashboard/quotas`                             |
|----------------------|-------------------------------------------------------------|
| `overview` (default) | Current clustered all-brands grid.                          |
| `brand:<slug>`       | Redirect to `/dashboard/quotas/<slug>` (per-brand detail).  |
| `cockpit`            | 302 to `FAIGATE_COCKPIT_URL` in the same tab.               |

- Stored in `FAIGATE_CONFIG_FILE` under `dashboard.quotas.default_view`.
- Surfaced in the dashboard settings panel with a radio group plus a
  dropdown of available brands (same roster the widget computes).
- A small "Home ⤴" pin appears on every brand card and on the overview
  header; clicking it sets that view as the default landing. One-click
  promotion, no modal.
- The URL bar still works — `/dashboard/quotas` respects the setting,
  `/dashboard/quotas?view=overview` forces the overview regardless.
- Gate Bar reuses the same setting: its popover's "Open" button honours
  the operator's chosen default view.

---

## 4. "Pace" computation (shared between widget and Gate Bar)

Defined in `quota_tracker.py` so both consumers get the same number.

```
pace_delta = used_ratio - elapsed_ratio
```

- `used_ratio`   = `used / total` (0.0–1.0, clamped)
- `elapsed_ratio`= fraction of the reset window that has elapsed
- Formatted as `+X %` / `−X %` with one decimal; `0 %` rendered as "on pace".

Only defined for `rolling_window` and `daily` packages. For `credits`
packages we surface `burn_per_day` and `projected_days_left` instead,
which we already compute.

---

## 5. Gate Bar — macOS menubar companion

**Target:** macOS 14+ (Sonoma) Universal binary (x86_64 + arm64). Linux port
deferred. Windows: not planned.

### Architecture

```
┌────────────────────────┐        http://127.0.0.1:<port>/api/quotas
│   fusionAIze Gate Bar  │ ──────────────────────────────────▶ faigate daemon
│   (SwiftUI menubar)    │ ◀────────────────────────────────── JSON response
└────────────────────────┘
            │
            ▼
     macOS Notification Center
     (alert thresholds)
```

No shared memory, no Unix socket, no filesystem coupling. The Gate Bar is a
pure HTTP client to the local gateway. That means:

- Gate Bar works the moment the gateway is running — no separate auth setup.
- Brand roster is discovered at runtime; the app ships with no hard-coded
  provider enum.
- Uninstalling Gate Bar cannot corrupt gateway state.

### Surfaces

1. **Menubar icon + label:** `fAI · 83 %` (tightest window across all
   brands, colour-coded). Click opens the popover.
2. **Popover:** reuses the visual spec from §3, rendered in SwiftUI. One
   card per brand, stacked vertically, scrollable if taller than screen.
3. **Preferences window:**
   - Refresh interval (manual / 1 / 2 / 5 / 15 min; default 5)
   - Notification thresholds (session 80 %, weekly 80 %, pace +10 %)
   - Gateway URL (default `http://127.0.0.1:4001`)
   - Launch at login (`SMAppService.mainApp.register()`)
4. **"Cockpit ↗" button** in the popover footer — opens the Operator Cockpit
   in the default browser via `NSWorkspace.shared.open(_:)`.

### Distribution

- Homebrew cask: `brew install --cask fusionaize/tap/gate-bar`
- Direct download: notarized `.dmg` from GitHub releases
- Auto-update via Sparkle 2 (EdDSA-signed appcast)
- Code-signed with a Developer ID Application certificate
- Notarized + stapled

### Privacy posture (about-box copy)

> Gate Bar reads usage data from your local fusionAIze Gate daemon over
> `127.0.0.1`. Account identifiers, plan names, and login methods stay on
> this machine. Gate Bar never connects to a fusionAIze-hosted service; the
> Cockpit link just opens a web page in your default browser.

---

## 6. Rollout plan

**Phase A — data model & naming (v2.2.x point release):**
- Add `brand` / `brand_slug` to catalog schema (`fusionaize-package-catalog/v1.3`).
- Fallback table in `quota_tracker.py` for catalogs still on v1.2.
- Extend `QuotaStatus` with `brand`, `brand_slug`, `pace_delta`, `identity`.

**Phase B — widget refresh (v2.3.0):**
- Brand-card layout at `/dashboard/quotas`.
- "Cockpit ↗" link replaces "Usage Dashboard" button.
- Pace marker + identity line.
- Per-brand detail route `/dashboard/quotas/<brand_slug>` with quota /
  clients / routes / analytics blocks.
- New read-only endpoints: `/api/quotas/<slug>/clients`, `/routes`,
  `/analytics` (all `?window=24h` by default).
- `dashboard.quotas.default_view` setting + one-click "Home ⤴" pin.
- "Available to add" mini catalog block at the bottom of the overview,
  reading from the existing fusionaize-metadata catalog. New authored
  field `catalog_tagline` = `tier · price · quota shape` (e.g. "Pro ·
  $20/mo · 500 fast req/mo", "free · 50 req/day"). Each row's CTA is a
  deep link to `${FAIGATE_COCKPIT_URL}/providers/add?brand=<brand_slug>`
  — no onboarding UI inside the dashboard.

**Phase C — Gate Bar 0.1 (v2.3.0 companion release):**
- SwiftUI project, macOS 14+ Universal.
- Popover with brand cards, menubar icon, preferences.
- Sparkle 2 auto-update, Homebrew cask.

**Phase D — CodexBar parity roster (v2.4+):**
- Add Cursor, Droid, Antigravity, Copilot brands to the catalog (with
  credential gating — they only appear if keys/OAuth are present).

---

## 7. Deferred / unresolved

- **Homebrew formula dylib ID error on `pydantic-core`.** Two attempts at a
  source rebuild in the formula post-install step failed to actually execute
  the rebuild (no `==>` line, build time too short for a Rust compile). The
  `Failed changing dylib ID` message is cosmetic (Python uses `dlopen`) but
  noisy. Diagnosis needed before next tap bump. Tracked separately — do not
  block v2.3 on it.
- **Linux port of Gate Bar.** Blocked on evaluating GTK4 vs Qt6 vs a Tauri
  wrapper around the existing widget. Revisit after the macOS version is in
  operator hands.
