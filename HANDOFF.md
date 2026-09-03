# HANDOFF — Full React/Dynamic-UI Migration, Phase F (Phases — list/manage)

## Status

**Phase F of the full React migration plan is complete.** Plan file: `C:\Users\RachurA\.claude\plans\this-application-needs-a-composed-adleman.md` (page inventory, port order A through Q). Phases A (router/AppShell/dark mode), B (Help), C (Weekly Import), D (Exceptions Queue), and E (Phase Detail) shipped in prior sessions.

## What was just done (Phase F)

Goal: port the Phases list/manage page (legacy `renderPhases()`, `app/static/app.js`) — described in the plan as "simple CRUD, natural companion to E." No backend changes were needed; every endpoint this page calls already existed (`GET/POST /api/engagements/:id/phases`, `PUT/DELETE /api/engagements/:id/phases/:phase_id`).

### New page: `app/frontend/src/pages/Phases.jsx`
Ported from legacy `renderPhases()`:
- Reuses `phases` from `EngagementLayout`'s outlet context (same `full_engagement()`/`phase_summary()` data legacy's own `/api/engagements/:id` call returned) rather than re-fetching — the overview endpoint already includes every field this page needs (`phase_name`, `phase_code`, `sow_fees`, `actual_hours`, `status`, `is_default`).
- **Editable table**: name/code/SOW-budget inputs per phase, local edit state synced from context on every `reload()`, one "Save phases" button that PUTs every row (unconditional loop, matching legacy's PUT-every-row-not-just-dirty-ones semantics exactly).
- **Guards ported 1:1 from legacy**: name/code disabled when engagement is closed; SOW-budget input additionally disabled once `phase.actual_hours > 0` (budget-lock parity — confirmed this 409s with `budget_locked` against real data, see Verification); Delete button shown only when `!is_default && !actual_hours && status !== 'closed'` (confirmed the backend independently enforces this via a `phase_in_use` 409, so the UI guard isn't the only thing standing between a user and a bad delete).
- **Forecast link**: `<Link>` (not `<a>`) straight to the already-React `phases/:phaseId` detail route from Phase E — no full-reload hop through legacy needed, since both pages are React-owned now.
- **Add-phase side form**: name (required)/code/SOW-budget, POSTs and reloads on success, hidden entirely when the engagement is closed (matches legacy).
- Inline `hint`/`hint danger-text` feedback for save/add/delete outcomes — no global toast system exists on the React side yet, so this follows the same pattern already established in `Overview.jsx`/`Exceptions.jsx`/`Import.jsx`.

### Routing (one-line-per-phase static-routing exception, as in every prior phase)
- **`app/app.py`**: `_REACT_ENGAGEMENT_SUBROUTE_RE` grew from `^\d+/(import|exceptions|phases/\d+)$` to `^\d+/(import|exceptions|phases|phases/\d+)$` — adds the bare `phases` list route (the `phases/\d+` detail route was already React-owned since Phase E).
- **`App.jsx`**: added `<Route path="phases" element={<Phases/>} />` as a sibling of the existing `phases/:phaseId` child route under `EngagementLayout`.
- **`EngagementTabs.jsx`**: added `"phases"` to `REACT_OWNED`, so the tab nav now does a client-side `<Link>` transition to the Phases tab instead of a full reload.
- **`app/static/app.js`**: added `'phases'` to the mirrored `REACT_ENGAGEMENT_SUBROUTES` Set (used by legacy's own `engagementTabs()` to decide `data-link` vs plain `<a>`) — this is the same class of fix Phase E made for the Team tab's phase-detail link, applied preemptively here so legacy's tab nav never intercepts this URL via client-side pushState and renders the now-dead `renderPhases()` from memory. Grepped for any other legacy anchor pointing at the bare `/engagements/<id>/phases` URL — only the tabs nav does, so no other fix was needed. `renderPhases()` itself is left in place as dead code, consistent with how `renderPhaseDetail()` was left alone in Phase E (retirement is Phase Q's job).

### New CSS (`GlobalStyle.jsx`)
- `.table-wrap td input, .table-wrap td select` — generic inline-editable-table-cell styling. Nothing on the React side had this yet (every prior ported table was read-only or used the `weekly-grid`-scoped input styling from Phase E); this is unscoped to any one table so Team roster (G) and Rate model (H) can reuse it directly instead of it being redefined per page.
- `.split-layout` / `.side-form form` — the two-column table + side-panel-form layout, ported from legacy (`grid-template-columns: minmax(0,1.7fr) minmax(300px,.7fr)`), collapsing to one column at `BREAKPOINTS.narrow` (900px) rather than legacy's ad hoc 1100px, per the plan's breakpoint-consolidation goal. This is also reusable — Adjustments (I) and Expenses (K) use the same legacy shape.

## Verification performed

- `npm run build` in `app/frontend` — succeeds (316KB JS, up from 311KB; unchanged CSS chunk size class).
- `python -m pytest tests/ -q` — all 50 tests pass (no `/api/*` changes this phase).
- `node --check app/static/app.js` — syntax OK after the `REACT_ENGAGEMENT_SUBROUTES` edit.
- Grepped for other legacy anchors targeting the bare `/engagements/<id>/phases` URL — none found besides the tabs nav (already covered by the Set edit).
- **Live-server verification against real seed data** (isolated port, throwaway copy of `demo_seed.db`, deleted after):
  - Routing split: `/engagements/5/phases` (bare) and `/engagements/5/phases/18` (detail) both serve the React bundle; `/engagements/5/team` still serves the legacy shell.
  - `GET .../overview` phase shape confirmed to match exactly what `Phases.jsx` renders (checked against engagement 5's two real phases, both with real actuals).
  - Created a throwaway phase via `POST .../phases` (the Add-phase form's exact call) — response shape matches.
  - Updated it via `PUT .../phases/:id` (the Save-phases button's exact call, no actuals so SOW budget was editable) — confirmed the new values persisted.
  - Attempted a SOW-budget change on a phase **with** real actuals (id 18) via the same `PUT` — got back a real `409 budget_locked` with `field_name: "sow_fees"`, proving the client-side `sowDisabled` guard matches a live backend rule, not a guess.
  - Deleted the throwaway phase (no actuals) via `DELETE .../phases/:id` — succeeded, matching the `canDelete` guard.
  - Attempted to delete a phase **with** real actuals (id 18) via the same `DELETE` — got back a real `409 phase_in_use`, confirming the backend independently enforces what the UI's `canDelete` guard also checks.
  - Confirmed the built bundle contains the new page's strings ("Workstreams", "Save phases", "Persistent phase management").
  - Test server killed, throwaway phase/db cleaned up (the throwaway phase was deleted as part of the DELETE test above; the db copy itself was a scratch-dir copy, removed after).

## Known gap — still not visually confirmed

Same corporate-network Playwright/Chromium limitation as every prior phase (A–E) — no real-browser check was possible. The `.split-layout` two-column-to-one-column collapse at 900px, the inline-editable table cells, and dark mode on this page have only been verified structurally (curl/API + reading every CSS rule against every className used in `Phases.jsx`), not visually. Packaging (`build.bat`/the `.exe`) was not rebuilt this session, consistent with Phases A–E.

## What to do next

Start **Phase G (Team roster)** in a new session, per the plan file. It's the natural next step after F — legacy's `renderTeamConfig()` (`app/static/app.js`) currently bundles *both* the team roster table and a duplicate, now-fully-superseded phase-config table (the one whose `data-link` was fixed in Phase E) into one page. Phase G should make an explicit decision — flagged in the plan, not to be silently resolved — about whether to drop that duplicate phase table from the ported Team page now that Phase F's dedicated Phases page exists, rather than porting the duplication forward. Phase G can also reuse the new `.table-wrap td input, .table-wrap td select` CSS added this phase for its own editable roster rows.

On a machine where Playwright can install Chromium, run:
```
cd app && python app.py
node app/tests/browser_smoke.cjs   # still broken at the pre-existing /dashboard assertion, unrelated to F
```
and manually visit `/engagements/<id>/phases` to visually confirm the split-layout table+form, the disabled-state styling on locked SOW-budget cells, and dark mode.

## Files touched

- New: `app/frontend/src/pages/Phases.jsx`
- Modified: `app/frontend/src/App.jsx` (new route), `app/frontend/src/components/EngagementTabs.jsx` (`REACT_OWNED` grew), `app/frontend/src/styles/GlobalStyle.jsx` (table-input + split-layout/side-form CSS), `app/app.py` (`_REACT_ENGAGEMENT_SUBROUTE_RE` grew), `app/static/app.js` (`REACT_ENGAGEMENT_SUBROUTES` grew)
- `app/frontend_dist/*` — rebuilt output
- `app/HANDOFF.md` — this file

No `calculations.py`/`schema.sql`/`importers.py` changes; no `/api/*` route changes.

## Verify command

```
cd app/frontend && npm run build

cd .. && python -m pytest tests/ -q
```
Expect: Vite build succeeds, `50 passed`.
