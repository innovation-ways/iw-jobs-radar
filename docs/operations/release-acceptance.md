# V1 release acceptance review

Review of the V1 definition of done (`ai-dev/docs/09`, "V1 definition of done" and the acceptance
matrix) against the repository as of the end of task T8. Evidence is an automated test, a command,
or a manual verification recorded in the ADR of the task. **The owner's trial period and sign-off
are still pending** (see the end).

## Acceptance matrix

| Capability | Evidence | Status |
|---|---|---|
| Career profiles and search intents | `test_profiles_api`, `test_profile_service`, `test_intent_service`, `test_revision_repositories` (immutable revisions, provenance); e2e `profile.spec` | Met |
| AI modes | No AI is the default (`test_ai_settings_service`); local model: `test_ollama_provider`, `make smoke`, ADR-046 manual check; compatible cloud provider: `test_openai_compatible_provider`, spy tests in `test_proposal_generation`. A **real** cloud call needs a key: `make smoke` with `JOBS_RADAR_SMOKE_API_*` | Met; real cloud call not run here |
| Privacy | `test_redaction`, `test_proposal_generation` (consent, redacted text only, no fallback), `test_ai_settings_api` (no key read-back, no key in logs), `test_profile_data_api` (export, typed-title deletion), `test_logging`, `test_outbound_policy` (no disk, one guarded client) | Met |
| Live collection | `test_collection_service`, `test_worker_runs`, `test_schedule_service`, `test_dedup_service`; real board in `make smoke` and ADR-042/045 manual checks | Met |
| Matching | `tests/unit/matching`, `test_evaluation_service`, `test_evaluations_api` (policy version, revisions, source hash, per-dimension evidence) | Met |
| Inbox | `test_inbox_transitions`, `test_inbox_service`, `test_inbox_api`; e2e `inbox.spec` | Met |
| Company intelligence | `test_company_enrichment`, `test_company_dossier*`, `test_company_summary`; real lookup in ADR-047. **Gap:** a company-level direct / agency classification with confidence is not produced (jobs carry an extracted employer type that feeds the score) | Partly met |
| Market pulse | `test_trends_service`, `test_trends_domain`, `test_trends_api` (reproducible weekly aggregates from stored data) | Met |
| Operations | Compose and health (`test_readiness`, `test_launcher`, `test_compose_exposure`), migrations (`test_migrations`), backups (`test_backup_restore`, `make restore-drill`), CI workflow (`test_ci_workflow`), secret and dependency scans (`make check-all`) | Met |

## Definition of done

| # | Item | Status |
|---|---|---|
| 1 | Every requirement mapped to an implementation and test where testable | Reviewed section by section through tasks T0-T8; the matrix above is the map |
| 2 | Persistent local deployment with PostgreSQL | Met (Docker Compose, named volume) |
| 3 | Agreed initial sources run daily and manually, with health and history | Machinery met. The research boards were seeded **disabled**; the owner enables the ones to follow |
| 4 | Real collected jobs reach the scored inbox | Met in the T4 acceptance (30 real jobs extracted, scored, listed). Needs a local analysis model chosen in AI & privacy |
| 5 | No AI, local and cloud AI from the same AI & privacy page | Met (cloud verified with fakes; see above) |
| 6 | Daily digest, company dossier/history and weekly pulse from real data | Digest and dossier verified on real data; the pulse needs evaluated jobs (a profile, an intent and a local model) |
| 7 | Automated tests, security checks and a synthetic restore test pass from a clean checkout | See "Clean-clone run" below |
| 8 | LAN-only, no auto-apply, no authenticated-board scraping | By design and by tests. **Check your `.env`:** `make config-check` warns when the API or database is bound beyond loopback |

## Clean-clone run

A fresh `git clone` of the repository at commit `36559eb` with no `.env` and no caches: `make install` then `make check` (backend gates, 1,200+ backend tests including the backup / restore drill on synthetic data, frontend gates and 258 frontend tests) finished with exit code 0 on 2026-10-09. The restore drill was also run on the development database (`make restore-drill`: 40 tables compared, PASSED). The end-to-end tests (`make test-e2e`, 13 passed) need the running stack and are run separately.

## Deferred improvements (recorded, not blocking V1)

From `ai-dev/docs/13` section 12 and what the work revealed:

- Currency conversion for pay comparison.
- A skills taxonomy (ESCO) and a larger place gazetteer (towns below about 15,000 inhabitants).
- Tuning of the constants of `matching-v1`, `dedup-v1` and the extraction prompts on more real data.
- OCR for scanned CVs.
- Company-level employer-type classification with confidence (gap above).
- Storing the relevance threshold per intent (it is a request parameter, default 45).
- Other source types (Lever, Ashby) through the same adapter interface.
- Notifications outside the app.
- Authentication, if the app is ever exposed beyond a trusted network.

## Owner trial and sign-off

Pending. Suggested trial: enable the boards you care about, choose a local model, create your
profile (import a CV or fill it in), set the daily schedule, and use Today and the Inbox for a
couple of weeks. Note anything surprising; run `make backup` first and `make config-check`.

Sign-off: ______________________  Date: ____________
