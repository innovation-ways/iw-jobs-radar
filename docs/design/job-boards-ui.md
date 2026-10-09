# Design: Job boards on the Sources screen

Status: ADR-049 approved 2026-10-09 (`ai-dev/docs/11 - Architecture Decision Log.md`); implementation is task T9. Research: `docs/research/R-00173-job-boards-as-sources.md`. Visual rules come from R-00170 and the existing screens (`frontend/src/pages/Sources.tsx`, `frontend/src/features/sources/`, `frontend/src/features/ai/ConnectionCard.tsx`).

## 1. What the owner can do

1. See two groups on the Sources screen: **Company boards** (today's table, unchanged) and **Job boards** (new).
2. Add a job board from a short **catalogue** (name, coverage, terms note, "needs a key" tag). Boards that need a key (ITJobs.pt) ask for it in the same form; the key is checked against the service before anything is saved.
3. Before saving, see a **preview** ("212 of 1,398 postings match your filters") and adjust the filters.
4. Enable, disable, run now, edit filters, replace or remove the key, and delete the board.
5. See on every posting (inbox row and detail) which board it came from, with a link back.

## 2. Layout (keeps the existing page structure)

The page keeps its container (`max-w-5xl`, 6-unit padding), header row with "Run all now", status/alert banners, and the `ScheduleCard`. The `AddBoardCard` (Greenhouse token) moves into the Company boards section header area. Nothing is hidden behind tabs: two sections, each with one heading, so the page reads top to bottom and works with the keyboard in a single tab order.

```
Sources                                                     [ Run all now ]
Company boards and job boards · one run per day by default

┌ Daily schedule ───────────────┐ ┌ Add a company board ───────────┐
│ 07:30 Europe/Lisbon  (read…)  │ │ Board token [__________] [Validate & add]
└───────────────────────────────┘ └────────────────────────────────┘

Company boards                                        (existing table, unchanged)
┌ Company ─ Status ─ Postings ─ New ─ Changed ─ Last update ─ [Run now][Disable] ┐

Job boards                                                [ + Add a job board ]
Boards publish jobs from many companies. Filters decide which postings are kept.
┌ Board ───────────── Status ───── Kept ─ New ─ Changed ─ Last update ─ Actions ──────────────┐
│ Himalayas            ✓ Updated    212    8     3     Today 07:31   [Run now][Disable][Settings ▾]
│ Remote, worldwide · eligible countries listed per job
│ ITJobs.pt            ✕ Failed       0    —     —     Today 07:31   [Run now][Disable][Settings ▾]
│ Portugal · IT                key refused (authentication)
│ Arbeitnow            ○ Never run    —    —     —     —             [Run now][Disable][Settings ▾]
└──────────────────────────────────────────────────────────────────────────────────────────────┘

Recent runs (existing RunHistory; rows name the board)
```

Notes:
- Same table style as `SourcesTable` (caption for screen readers, uppercase small headers, status in words plus icon, never colour alone).
- The first column of a job board shows the **name** and a one-line **coverage note** from the catalogue instead of a company token.
- "Kept" is the number of open postings the board contributes after filters (the existing `open_postings`).
- A job board row never shows a company, because a board has many.

## 3. Adding a job board (inline panel, no modal)

"+ Add a job board" opens a panel directly under the section heading (disclosure level 1). Choosing a board shows its form in place (level 2). A modal is avoided so focus and scrolling stay simple and the pattern matches the inline forms of the AI & privacy page.

```
Add a job board                                                        [ Close ]
┌───────────────────────────────────────────────────────────────────────────┐
│ Arbeitnow       Europe · remote and relocation   Free, no key       [ Add ]
│ Jobicy          Remote · Europe filter           Free, no key       [ Add ]
│ Himalayas       Remote · eligible countries      Free, no key       [ Add ]
│ ITJobs.pt       Portugal · IT                    Needs a free key   [ Add ]
│ Already added boards show "Added" and no button.
└───────────────────────────────────────────────────────────────────────────┘

Add ITJobs.pt
  API key        [••••••••••••        ]  Free key from itjobs.pt/api (request it by email).
                                         Stored encrypted. It is sent once and never shown again.
  Countries     Portugal, Spain, … + worldwide remote   (from your profile and intents)  [ Change in Profile & intent ]
  Categories     [ Software × ] [ Data × ] [ DevOps × ] [ Security × ]
  Search terms   [ optional ]            Posted within  [ 30 ▾ ] days
  Per run limit  [ 500 ]
  Terms: "Link back to the source. Read on 2026-10-09." ↗ itjobs.pt

  [ Check & preview ]
  ✓ Key accepted. 212 of 1,398 postings match these filters.
  [ Add ITJobs.pt ]   [ Cancel ]
```

Behaviour:
- `Check & preview` calls `POST /api/v1/sources/preview` (key and filters in the body, nothing saved). The result is either a preview or a classified error: `authentication` ("The key was refused"), `unreachable`, `invalid_payload`. The `Add` button is disabled until a preview succeeded for the current values; any edit invalidates the preview.
- `Add` calls `POST /api/v1/sources` with the same body; the server validates again, saves, and the new row appears (and the panel closes with a `role="status"` message: "Added ITJobs.pt. Run it to collect its jobs.").
- Boards without a key skip the key field. Their only extra step is the preview.
- The key input is `type="password"`, `autoComplete="off"`, and its value is cleared from state after a successful save, as in `ConnectionCard`.
- The countries are **read-only** and come from the profile and the enabled intents (`GET /api/v1/source-scope`, ADR-049.11); the form links to Profile & intent. Without an enabled intent the form says so and `Check & preview` is disabled. Other defaults come from the catalogue (last 30 days, 500 per run); the Settings drawer uses the same ones.

## 4. Row settings (disclosure level 2)

`Settings ▾` expands a panel below the row (`aria-expanded`, `aria-controls`; the table row gets a second `<tr>` with `colSpan`).

```
Himalayas settings
  Filters   categories [...]   terms [ ]   max age [30] days   limit [500]      Countries: Portugal, Spain, … (from your profile)
            [ Save filters ]   Applies from the next run. Postings already kept are not closed by a new filter.
  Key       Credential: saved (updated 2026-10-09)   [ Replace… ] [ Remove key ]      ← only for boards that need a key
  Source    Himalayas · data refreshed every 24 h · next run allowed after 07:31 · Terms ↗ · Link back required
  Note      A board is switched off with Disable; removing a source is not offered (its postings stay in the inbox history).
```

- Saving filters uses `PUT /api/v1/sources/{source_configuration_id}` with `expected_version` (409 on a stale version, as for enable/disable).
- Replace/Remove key reuse the write-only pattern of the AI connection card: placeholder `•••••• (replace)`, "Credential: saved | not set", never echoed.
- There is no delete in this version: a source with collected postings is kept and disabled instead.

## 5. Status, errors and rate rules in words

| State | Text and icon (existing `STATUS_STYLE`) | Notes |
|---|---|---|
| Never run | "Never run" (dashed circle) | |
| Running | "Running…" (spinner) | polling as today |
| Updated / unchanged | "Updated" / "Unchanged" (check) | boards without ETag report "Updated" when postings changed |
| Partial | "Partial — limit reached" (alert, caution tone) | new; run hit the per-run limit, nothing was closed (ADR-049.5) |
| Failed | "Failed" (alert) + `error_message` + `error_class` | classes include new `authentication` |
| Disabled | "Disabled" (minus) | |
| Too soon | Run now disabled with `title`/text "Allowed again at 14:05" | server returns `409 too_soon`; the client uses `next_run_allowed_at` from `SourceRead` so it normally never gets the 409 |

## 6. Where the board shows up elsewhere

- **Inbox row** (`JobRow`): a small text chip with the board name next to the company, only for postings from a job board ("via Himalayas"); company-board postings show nothing new.
- **Job detail** (`JobDetail`): a "Sources" line listing each listing of the opportunity: "Anthropic careers (Greenhouse)" and "Himalayas ↗". The link goes to the board's canonical URL (this is also the attribution the board's terms ask for). Where the catalogue says so: "Delayed up to 24 h by Remotive".
- **About & credits**: one entry per board that is currently added (name, link, short attribution text).
- **Trends**: no new widget; enabling, disabling or filtering a board appears through the existing source-change marker.

## 7. API changes (the implementation will regenerate `openapi.json` and `schema.d.ts`)

| Method and path | Purpose |
|---|---|
| `GET /api/v1/source-catalogue` | Catalogue entries: `catalogue_key`, `display_name`, `coverage_note`, `requires_credential`, `credential_label`, `terms_note`, `terms_url`, `terms_read_on`, `default_filters`, `available_categories`, `already_added` |
| `POST /api/v1/sources/preview` | Body: `catalogue_key`, `credential` (optional, write-only), `filters`. Returns `{display_name, postings_total, postings_matching, matching_is_lower_bound}` or a classified error (`authentication`, `configuration`, `timeout` ...); saves nothing |
| `POST /api/v1/sources` | Existing endpoint extended: `source_type` + `external_identifier` as today for company boards; for job boards both equal the catalogue key, plus optional `credential` and `filters` |
| `PUT /api/v1/sources/{source_configuration_id}` | Existing; adds `filters` |
| `PUT` / `DELETE /api/v1/sources/{source_configuration_id}/credential` | Write or remove the key; `SourceRead` returns only `credential_status` (`saved`, `none`, `not_needed`) and `credential_updated_at` |
| `GET /api/v1/source-scope` | Read-only `{configured, country_codes, include_worldwide, any_country}` derived from the profile and the enabled intents |
| `SourceRead` additions | `category` (`company_board` or `job_board`), `coverage_note`, `filters`, `credential_status`, `next_run_allowed_at`, `terms_url`, `attribution_text`, `next_run_allowed_at` (and `dropped_count` on run results) |

IDs are integers, errors use the common envelope (`422` invalid filters, `409` stale version or `too_soon`, `503` source unavailable), no credential in any response or log.

## 8. Frontend components

| Component | Responsibility |
|---|---|
| `features/sources/JobBoardsSection.tsx` | The section: heading, "+ Add a job board", table, empty state ("No job boards yet. Add one to find companies you do not watch yet.") |
| `features/sources/JobBoardsTable.tsx` | Rows with status, counts, actions, expandable settings row (shares `STATUS_STYLE` and `statusOf` with `SourcesTable`, extracted into `status.ts`) |
| `features/sources/CataloguePanel.tsx` | Lists catalogue entries; "Added" state |
| `features/sources/AddJobBoardForm.tsx` | Key (when needed), filters, `Check & preview`, `Add`; plain React state with targeted validation (ADR-043) |
| `features/sources/BoardFiltersFields.tsx` | Shared filter fields for the add form and the settings drawer (uses `ChipsInput` for countries, categories, terms) |
| `features/sources/BoardCredentialField.tsx` | Write-only key field, replace/remove, same pattern as `ConnectionCard` |
| `queries.ts` | `useCatalogue`, `previewBoard`, `addJobBoard`, `updateFilters`, `writeCredential`, `removeCredential`, `deleteSource` |
| `features/inbox/JobRow.tsx`, `JobDetail.tsx` | Board chip and sources line |

All exported components get JSDoc; texts in English; keyboard order follows reading order; `ChipsInput`, `LocationPicker` (for the country chips, offline from `geonamescache`), `Button` and the field classes are reused, no new UI library.

## 9. Accessibility and states

- Every status is text plus icon; the preview, add and error messages use `role="status"` / `role="alert"` as the existing cards do.
- Expand/collapse buttons have an accessible name that includes the board ("Settings for Himalayas"), `aria-expanded`, and focus moves to the first field when a panel opens and back to the button when it closes.
- Loading, error with "Try again", empty and disabled states exist for the catalogue and the table, as for company boards.
- Dark and light themes use the existing tokens only.

## 10. Test plan (TDD, synthetic data only)

- Backend unit: catalogue entries valid (unique keys, https endpoints, terms date present, no scraping type); filter model validation; each adapter maps a synthetic recorded response (paging, missing salary, missing company, empty list); credential never appears in `url`, logs or errors; `partial` outcome does not close postings; `too_soon` rule.
- Backend integration (testcontainer): add with and without key, refused key saves nothing (422, class `authentication`), preview saves nothing, per-posting company resolution and dedup against a Greenhouse listing, primary posting is the company-board listing, filter change does not close postings.
- Frontend (Vitest): catalogue panel, add flow with key and preview gating, write-only key field, filters save with 409, status texts, too-soon button state, board chip and sources line.
- E2E (Playwright, local stack): add a board from the catalogue against a stubbed backend board, run, see postings. Real boards only in opt-in smoke tests.

## 11. Implementation order (proposed task T9, after the owner approves ADR-049)

- T9.1 Domain and data: source categories, new `SourceType` values and migration, `SourcePosting.company_name`, filter model, `authentication` error class, catalogue, API contract and snapshot.
- T9.2 Adapter contract change and the three keyless adapters (Arbeitnow, Jobicy, Himalayas) with synthetic fixtures.
- T9.3 Pipeline: per-posting company, filters before storage, `partial` rule, politeness and `too_soon`, primary-posting rule in dedup.
- T9.4 Credentials: encrypt, write-only endpoints, redaction, preview and add with key.
- T9.5 Frontend: Job boards section, catalogue, add form, settings, key field; inbox chip and sources line; About credits.
- T9.6 ITJobs.pt adapter after the owner has the key and confirms the fields and terms.
- T9.7 Operations docs (sources and providers runbook, known limitations, About) and an opt-in smoke test.

Each sub-task: tests first, quality gates, one focused commit on `main` (Conventional Commits, scopes `api|db|worker|frontend`).
