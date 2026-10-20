# Domain packs: plan and characterisation tests (ADR-080)

Status: approved on 2026-10-20 (ADR-080). Phases 0 to 4 are implemented; the later phases follow.

Goal: the job domain (vocabulary, pre-filter, skills, requirements) becomes data that ships in packs, so Jobs
Radar serves any occupation, and the current owner's installation keeps every term, revision, score and
inbox row it has today.

## 1. Phases

Each phase ends with all quality gates green and one or more focused commits on `main`. Nothing is pushed
until the owner confirms the whole work (owner decision).

| Phase | Content | Behaviour change for the current owner |
|---|---|---|
| 0 | Safety net: `make backup`, `make restore-drill`, the characterisation tests of section 3 | none |
| 1 | ADR-080 approved, doc 13 updated as phases land | none |
| 2 | Seed constants leave run time: validation, defaults, demo and frontend read the database or an API | none (golden tests prove it) |
| 3 | Editable taxonomy (API and screen), prompt generated from the database | none (prompt byte-identical) |
| 4 | Pack schema, ten pack files, idempotent loader, activation, package data in the image | owner marked as "Software, data and IT" active |
| 5 | Pre-filter areas and noise as data | none (corpus test) |
| 6a | Skills: `tool_equipment` and `credential` kinds | none |
| 6b | Credentials, `schedule`, `travel`, two dimensions at weight 0, gate G12 off, `matching-v1.9`, `extract-v5` | scores unchanged until the owner raises a weight; one agreed re-extraction |
| 6c | Setup assistant, pack-derived defaults, "Re-extract open jobs" action | none for the owner |

## 2. What the current code ties to the domain (found by reading it)

- `domain/taxonomy_seed.py`, `taxonomy_additions.py`, `taxonomy_v3.py`: frozen constants. Run-time importers:
  `schemas/intent.py`, `demo/persona.py`. Test importers: `tests/data.py`, `tests/integration/test_seed_data.py`,
  `tests/unit/schemas/test_intent_schema.py`, `tests/unit/test_demo_jobs.py`. Migrations 0002, 0017 and 0025
  import them and must not be edited.
- `domain/job_board_rules.py`: `_AREAS` (software, data, devops, telecom, security) and `_NOISE` (moved to the packs in phase 5).
- `services/extraction_prompt.py`: text and the `bounded_schema()` limits; `services/extraction_rules.py:216`
  already validates families against the database.
- `domain/matching/engine.py`: compares keys and stances only; `qualifications` (weight 0) and `radius_km` /
  gate G2 already exist.
- `domain/enums.py`: `SkillKind` (`technology`, `domain_knowledge`, `method`), prompt versions, accepted
  prompt versions (ADR-077).
- Frontend: `features/intent/defaults.ts`, `validate.ts`, `StanceGroup.tsx`, `IntentForm.tsx`,
  `features/sources/BoardSettings.tsx`, `filters.ts`, `pages/Trends.tsx`, `features/profile/DirectionsEditor.tsx`
  and the builders in `src/test/builders.ts`.

## 3. Characterisation tests (phase 0)

These tests describe what the system does today. They must pass **before and after every later phase**. A
golden file is generated once from the current code and committed under `backend/tests/golden/`; changing it
needs a conscious, reviewed edit. All data is synthetic (project rule).

| ID | Test | Layer | What it freezes | Fails if |
|---|---|---|---|---|
| C1 | Taxonomy snapshot | integration (testcontainer, migrations to head) | the set of `(kind, term_key, label)` after migrations, and the origin of each | a term is lost, renamed or relabelled |
| C2 | Extraction prompt golden | unit | system prompt text, `bounded_schema()` and the allowed-keys message built for the full current taxonomy | the prompt changes by a single byte before phase 6b |
| C3 | Pre-filter corpus | unit | `categorise()` and the noise rule over a corpus of at least 80 synthetic titles (technology, trades, health, noise) with the expected areas | an area or noise decision changes for the Software pack |
| C4 | Matching golden | unit (pure engine) | `fit_score`, `recommendation`, gates and every dimension's status, strength and contribution for at least 12 fixed (profile, intent, job attributes) scenarios: remote EU, hybrid inside and outside the radius, rejected role, rejected sector, contractor day rate, unknown pay, part-time rejected, skills coverage, direction judgement, qualifications | any score or gate differs |
| C5 | Weight neutrality (written now, enabled in 6b) | unit | the C4 scenarios re-run with the new dimensions at weight 0 and G12 off give identical results | a new rule changes an old score |
| C6 | Intent schema accepts today's data | unit | the demo persona's intents and the worked example of doc 13 section 4 validate and round-trip | validation rejects an existing intent |
| C7 | Immutable history | integration | after each new migration, counts and content hashes of `profile_revision`, `intent_revision`, `job_extraction`, `match_evaluation`, `score_dimension`, `inbox_event` and the owner's `job_inbox_item` rows are unchanged, and `taxonomy_term_id` / `term_key` of every existing term are unchanged | a migration touches an immutable row or a key |
| C8 | Upgrade path | integration | database at the current head with a populated owner scene (factories) upgrades to the new head and downgrades where the migration is reversible, and `taxonomy_version` only increases | a migration loses data |
| C9 | Taxonomy API contract | integration | `GET` taxonomy groups returns today's terms, grouped, in the same order | the response shape or terms change |
| C10 | Frontend defaults | Vitest | `defaults.ts` produces today's default intent for the current taxonomy; `validate.ts` accepts and rejects the same cases as today | defaults or validation drift |
| C11 | Demo persona | unit and integration | `make demo` data (`demo/persona.py`) is unchanged: same intents, same stances | the demo changes |
| C12 | OpenAPI snapshot | unit (exists) | `backend/openapi.json` and `frontend/src/api/schema.d.ts` only change in phases that add endpoints | stale snapshot |

Existing tests that must stay green unchanged (they already exercise the contract): `tests/unit/matching/*`,
`test_job_board_rules.py`, `test_extraction_prompt.py`, `test_extraction_rules.py`, `test_posting_filter.py`,
`test_demo_jobs.py`, `integration/test_seed_data.py`, `integration/test_intent_service.py`,
`integration/test_evaluation_service.py`.

## 4. Tests added with later phases (each written first, RED then GREEN)

| Phase | Tests |
|---|---|
| 2 | No module under `src/jobs_radar` (outside `alembic`) imports the seed constants (import-linter contract); intent validation reads terms from the database |
| 3 | Add, relabel, deactivate and merge a term; keys immutable; `taxonomy_version` bumps once per change; prompt built from the database equals C2 for the Software pack; inactive terms are not offered to the model; stored intents referencing an inactive term still load |
| 4 | Pack schema validation (rejects unknown fields, duplicate keys, empty keys); loader idempotent (second run changes nothing); upgrade adds new terms and keeps owner edits; a removed pack term is deactivated, not deleted; activation of several packs; pack files are found as package data (`importlib.resources`) and are present in the backend image build context; the demo uses the Software pack |
| 5 | Keywords compile to escaped whole-word patterns (no user regex, hostile input safe, tested with property tests); C3 holds for the Software pack; a trades corpus ("Electrician", "Maintenance technician") passes the trades pack and fails Software; noise per pack |
| 6a | New skill kinds persist and resolve through aliases; existing skills keep their kind |
| 6b | Extraction schema salvage for credentials, schedule, travel; quotes verified verbatim; stances on schedule and travel; credential coverage in `qualifications`; G12 fires only when enabled and only on known data; `matching-v1.9` evaluations are new rows and old ones remain; C5 enabled |
| 6c | Setup assistant: pack choice persists, intent prefilled from pack, existing owner is not forced through it; "Re-extract open jobs" queues only open jobs and only on confirmation; Playwright smoke for the new screens |
| all | `make docs-check` (column comments), `make arch-check`, 80% coverage, `make docs-schema` regenerated |

## 5. Risks and how each is closed

| Risk | Mitigation |
|---|---|
| The owner's data is damaged by a migration | `make backup` and `make restore-drill` first; two-step migrations; C7 and C8 |
| The prompt changes and open jobs are queued again | C2 golden; ADR-077 rule (taxonomy changes re-extract nothing); the single re-extraction is an explicit owner action in 6b/6c |
| A small local model degrades with too many keys | prompt lists only active packs; sample run with `make` tooling on the demo before accepting phase 3 |
| Pack updates overwrite the owner's edits | loader rule (add only, never overwrite or delete) tested in phase 4 |
| Packs missing from the published image | package-data test and image build check in phase 4 |
| Scope creep into general job sources | explicitly out of scope (ADR-080 point 12, ODR-008) |

## 6. Questions that stay open until the design of the phase concerned

- Final keys and names of the two new dimensions in phase 6b (proposal: `schedule`, `travel`, or one combined
  `schedule_travel`).
- Whether pack activation is stored per owner (`owner_id` is present in the model) or globally; the proposal is
  per owner, consistent with the rest of the model.
- How a pack declares suggested stances for the global kinds (arrangement, seniority); proposal: a small
  `defaults` block in the pack file.

## 7. Progress and decisions taken on the way

| Phase | State | Notes |
|---|---|---|
| 0 | done | characterisation tests and golden files in `backend/tests/golden` |
| 2 | done | seeds are for migrations only (import-linter contract) |
| 3 | done | editable vocabulary, merge (survivor's stance wins), Vocabulary screen |
| 4 | done | ten packs as package data, loader at start-up, per-owner activation, Packs screen; guide in `docs/packs.md` |
| 5 | done | areas and noise in the pack files; rules compiled from keywords (`domain/prefilter.py`), read per owner from the packs that are on; no table |
| 6a | done | skill kinds `tool_equipment` and `credential`; credentials in packs, extraction, qualifications and gate G12 (off); profile section. The model is not asked for credentials until 6b |
| 6b, 6c | to do | schedule and travel (taxonomy v4, `schedule_travel`, G13, G14, `matching-v1.9`, `extract-v5`); setup assistant, pack defaults, re-extraction action |

Decisions of phase 4: a term in no pack is always offered (`other`, user terms, the global kinds);
an installation that already has a profile gets the software pack switched on by migration `0030`, a
fresh one chooses; the loader never rewrites a label and only switches off what a loaded pack stopped
listing; a stored intent is validated against every term, whatever packs are on. A pack file must
list at least 10 role families and 5 sectors, and a key has one label in every pack.

Decision of phase 5 (a refinement of ADR-080, point 7): areas and noise are read from the pack files of
the packs the owner has switched on, not stored in tables. Nothing about them is edited by the
owner yet, so a table would only copy the files; owner-defined areas would need one, later. A board
with no stored areas selects every area of the owner's packs; a request that names none gets the
same. Chosen areas that no switched-on pack defines are ignored (nothing is filtered by them).

Decisions of phase 6a: credentials are skills of kind `credential` (level and years are fixed and not
shown); the contract has `credentials` but the model-facing schema leaves it out until the prompt that
explains it ships in 6b, so the prompt is unchanged and nothing is re-extracted; the qualifications
dimension is the mean of the education part and the credentials part that the posting states, and is
exactly what it was when a posting names no credential; G12 fires only for a required (`must`)
credential, only when the owner turned the option on. The policy version is bumped in 6b, together
with the prompt, so that one rescore covers every change.
