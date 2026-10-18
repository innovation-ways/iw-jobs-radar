
# Jobs Radar — Domain Schemas and Matching Rules v1

> **About this published copy.** This is the maintainer's domain design document, published with the
> code: it is the reference for the data shapes and the scoring rules (`matching-v1` and its later
> policy versions, see the architecture decision log in `docs/decisions/`). References to other
> numbered documents (for example "LLD §5", "document 00", "UC-03") point to the maintainer's
> design pack, which is not part of this repository. The worked examples use invented values.

## Purpose and status

This document fixes the data shapes and the matching rules that the implementation needs before the first line of domain code: taxonomies, the Career Profile, the Search Intent, the normalised job, the AI extraction contract, the `matching-v1` scoring rules, the Company entity, duplicate handling and the trend data model.

**Status: owner decisions D1–D10 recorded on 2026-10-08 (section 13); the document is otherwise a draft for review.** Everything else follows accepted ADRs (004–006, 021–026) and research R-00170, R-00171 and R-00172. If this document conflicts with another, stop and record a decision request (see document 00).

## 1. Conventions

- JSON field names are `snake_case`. Primary keys and foreign keys follow `{table_name}_id` (ADR-014). Timestamps are UTC ISO-8601.
- Every attribute extracted from a job is a **fact with a status**: `known` (value present) or `unknown` (not stated or not trustworthy). `unknown` is never replaced by a guess (ADR-005).
- Taxonomy keys are lowercase `snake_case` strings (for example `ai_solutions_engineering`). Keys are never reused or deleted (section 2).
- Weights, stance strengths and thresholds are **policy constants** of a named policy version (`matching-v1`, `dedup-v1`, `extract-v1`) and are stored with every result that used them.
- Names of normalised job fields follow schema.org `JobPosting` where an equivalent exists (R-00172 F6).

## 2. Taxonomies

A taxonomy is a controlled list of terms with a key and a label. Terms are never deleted: a merge or rename is recorded as `replaced_by`, and every query resolves through that chain so that historic counts stay comparable (ADR-022).

| Table | Columns (besides `created_at`) |
|---|---|
| `taxonomy_term` | `taxonomy_term_id`, `kind`, `term_key`, `label`, `origin` (`seed`, `user`, `ai_proposal_accepted`), `replaced_by_taxonomy_term_id` (nullable), `taxonomy_version` introduced |

Unique on `(kind, term_key)`. The global `taxonomy_version` is an integer that increases whenever a term is added, merged or renamed; extractions record the version they used.

### 2.1 Initial seed terms

| Kind | Initial keys |
|---|---|
| `role_family` | `ai_solutions_engineering`, `ai_ml_engineering`, `data_engineering`, `data_analysis`, `software_engineering_general`, `backend_engineering`, `frontend_engineering`, `devops_platform`, `solutions_architecture`, `enterprise_architecture`, `telecom_billing_bss_oss`, `product_management`, `project_programme_management`, `consulting_integration`, `ai_governance_risk`, `security`, `qa_testing`, `sales_account_management`, `customer_support`, `other`; added in taxonomy v2 (ADR-060): `finance_accounting`, `legal_compliance`, `hr_recruiting`, `marketing_communications`, `operations_admin`, `design_creative` |
| `sector` | `telecom`, `enterprise_it`, `software_saas`, `finance_banking`, `insurance`, `public_sector`, `healthcare`, `retail_ecommerce`, `manufacturing_industrial`, `energy_utilities`, `logistics_transport`, `media_entertainment`, `education`, `consulting_services`, `gambling`, `defence_aerospace`, `other` |
| `seniority_level` | `intern`, `junior`, `mid`, `senior`, `staff_principal`, `management`, `executive` |
| `engagement_type` | `employee_permanent`, `employee_fixed_term`, `contractor_b2b`, `freelance`, `internship` (hours are a separate attribute, see 5) |
| `work_arrangement` | `remote`, `hybrid`, `onsite` |
| `employer_type` | `direct_employer`, `agency_recruiter`, `consultancy_outsourcer` |
| `benefit` | `equity`, `bonus`, `learning_budget`, `flexible_hours`, `four_day_week`, `health_insurance`, `extra_leave`, `relocation_support`, `home_office_budget` |

Company stage (startup, scale-up, enterprise) and size are **informational** in V1 and are not scored (R-00172 F2); they are stored as company facts (section 9).

### 2.2 Skills

Skills are not a fixed list. They live in `skill` rows created on demand:

| Table | Columns |
|---|---|
| `skill` | `skill_id`, `canonical_name`, `kind` (`technology`, `domain_knowledge`, `method`), `esco_uri` (nullable) |
| `skill_alias` | `skill_alias_id`, `skill_id`, `alias_normalised` (lowercase, punctuation stripped, for example `node js`, `nodejs`) |
| `skill_relation` | `skill_relation_id`, `skill_id_a`, `skill_id_b`, `relation` (`equivalent`, `related`, `unrelated`), `origin` (`ai`, `user`), `provider`, `model`, `prompt_version`, `created_at` |

Rules: extraction maps a skill mention to a `skill_id` through aliases; an unmapped mention becomes a `skill_candidate` that the extractor proposes with a canonical name, accepted automatically when it normalises to an existing alias and queued for review otherwise. `skill_relation` caches AI judgements for a skill pair (symmetric, stored once with `skill_id_a < skill_id_b`), so the same pair is never judged twice. An optional mapping to ESCO is a later enhancement (R-00172 F7).

User-defined role families or sectors (the "Add…" fields in the Search Intent) create a `taxonomy_term` with origin `user`; the AI is shown all terms, so a user term participates in extraction from the next taxonomy version.

## 3. Career Profile facts

A `ProfileRevision.facts_json` has this shape. Every fact carries provenance.

```json
{
  "schema_version": 1,
  "headline": "AI solutions and integration engineer",
  "base_location": {
    "place": "Lisbon, Portugal", "country": "PT", "timezone": "Europe/Lisbon",
    "latitude": 38.72, "longitude": -9.14
  },
  "years_experience": 12,
  "languages": [
    {"language": "pt", "level": "native"},
    {"language": "en", "level": "C1"}
  ],
  "skills": [
    {"skill_id": 17, "level": "expert", "years": 10,
     "provenance": {"origin": "document", "evidence_id": 41, "accepted_at": "2026-10-08T10:00:00Z"}}
  ],
  "experience": [
    {"title": "Solutions Architect", "organisation": "Example Corp", "start": "2019-01", "end": "2024-06",
     "summary": "Led integration of machine-learning features into telecom platforms.",
     "sectors": ["telecom", "enterprise_it"],
     "provenance": {"origin": "document", "evidence_id": 43, "accepted_at": "2026-10-08T10:00:00Z"}}
  ],
  "education": [{"level": "msc", "field": "Computer Science", "provenance": {"origin": "manual"}}],
  "certifications": [{"name": "Example Certification", "year": 2022, "provenance": {"origin": "manual"}}]
}
```

- `level` for skills: `beginner`, `intermediate`, `advanced`, `expert`. Language levels: `A1`–`C2` or `native`.
- `provenance.origin` is `manual`, `document`, `llm` or `import`; only `manual`, accepted `document`/`llm` and `import` facts exist in a revision (rejected and deferred proposals never do).
- `base_location` is the anchor for hybrid and on-site distance rules; coordinates come from the local gazetteer (section 13, D1).
- `sectors` in experience is informational in V1 scoring (sector scoring uses intent stances) and is used by the AI summary.

## 4. Search Intent

An `IntentRevision.intent_json` has this shape (the values below are an invented worked example, not a real person's search).

```json
{
  "schema_version": 1,
  "title": "AI & telecom billing — remote first",
  "stances": {
    "role_families": [
      {"key": "ai_solutions_engineering", "stance": "preferred"},
      {"key": "telecom_billing_bss_oss", "stance": "preferred"},
      {"key": "software_engineering_general", "stance": "acceptable"},
      {"key": "data_analysis", "stance": "rejected"},
      {"key": "sales_account_management", "stance": "rejected"}
    ],
    "work_arrangements": [
      {"key": "remote", "stance": "preferred"},
      {"key": "hybrid", "stance": "acceptable"},
      {"key": "onsite", "stance": "acceptable"}
    ],
    "engagement_types": [
      {"key": "contractor_b2b", "stance": "preferred"},
      {"key": "freelance", "stance": "preferred"},
      {"key": "employee_permanent", "stance": "acceptable"},
      {"key": "employee_fixed_term", "stance": "acceptable"},
      {"key": "internship", "stance": "rejected"}
    ],
    "hours": {"part_time": "rejected"},
    "seniority_levels": [
      {"key": "junior", "stance": "rejected"}, {"key": "mid", "stance": "acceptable"},
      {"key": "senior", "stance": "preferred"}, {"key": "staff_principal", "stance": "preferred"},
      {"key": "management", "stance": "acceptable"}
    ],
    "sectors": [
      {"key": "telecom", "stance": "preferred"}, {"key": "enterprise_it", "stance": "preferred"},
      {"key": "finance_banking", "stance": "acceptable"}, {"key": "gambling", "stance": "rejected"}
    ],
    "employer_types": [
      {"key": "direct_employer", "stance": "preferred"},
      {"key": "agency_recruiter", "stance": "acceptable"},
      {"key": "consultancy_outsourcer", "stance": "acceptable"}
    ]
  },
  "work_rules": {
    "remote": {"eligible_regions": ["EU", "UK"], "timezone": "Europe/Lisbon", "timezone_tolerance_hours": 2},
    "onsite_hybrid": {"base_place": "Lisbon, Portugal", "latitude": 38.72, "longitude": -9.14, "radius_km": 40}
  },
  "compensation": {
    "employee_pay": {"currency": "EUR", "payments_per_year": 14, "annual_minimum": 60000, "annual_target": 75000},
    "contractor_day_rate": {"currency": "EUR", "minimum": 450, "target": 550},
    "reject_below_minimum": true
  },
  "languages": {"can_work_in": ["pt", "en"], "reject_unspoken_required": true},
  "keywords": ["LLM", "RAG", "billing", "charging", "mediation"],
  "exclusions": {"companies": ["Harbor Systems"], "words": ["unpaid", "internship"]},
  "filters": {"max_posting_age_days": null, "needs_visa_or_relocation": false},
  "benefits_wanted": [],
  "weights": {
    "role_responsibilities": 25, "skills_technology": 15, "work_arrangement_location": 15,
    "engagement_terms": 10, "compensation": 10, "seniority_experience": 8,
    "domain_sector": 10, "company_profile": 7, "benefits_flexibility": 0, "qualifications": 0,
    "career_direction": 0
  },
  "alert_threshold": 65
}
```

### 4.1 Validation (server side)

| Field | Rule |
|---|---|
| `stance` | one of `preferred`, `acceptable`, `rejected`; every `key` must exist in the taxonomy for its kind; no duplicates |
| each stance group | `work_arrangements`, `engagement_types`, `seniority_levels` and `employer_types` list **every** taxonomy term (the UI defaults new terms to `acceptable`); `role_families` and `sectors` may list a subset (see 7.2, "unlisted") |
| group coherence | at least one option per group that is not `rejected`, otherwise the intent is rejected as incoherent (UC-03) |
| `weights` | integers 0–40; at least one above 0 |
| `compensation.*` | minimum ≥ 0; target ≥ minimum; `currency` is an ISO 4217 code; one currency per form |
| `employee_pay.payments_per_year` | 12 or 14. The canonical stored values are **annual**; the monthly figure is derived (`annual ÷ payments_per_year`) and the UI shows both linked fields (editing one updates the other). Contractor pay has **only** a day rate: no monthly or annual form |
| `work_rules.remote.eligible_regions` | ISO 3166-1 alpha-2 codes or the groups `EU`, `EEA`, `EUROPE`, `UK`, `WORLD`; `EU` expands to its member states |
| `timezone`, tolerance | IANA name; tolerance 0–12 hours, or `null` for any |
| `radius_km` | 1–500 |
| `languages.can_work_in` | ISO 639-1 codes; at least one |
| `keywords` | at most 50 items, each at most 60 characters; they help extraction recall only and are **not scored** |
| `exclusions` | at most 100 items per list; words match whole words, case-insensitively |
| `alert_threshold` | integer 0–100 |
| `title` | 1–120 characters |
| unknown fields | rejected (strict schema) |

## 5. Normalised job

`JobSnapshot.normalised_json` plus the AI extraction (section 6) produce this shape. Names follow schema.org `JobPosting` where possible.

```json
{
  "schema_version": 1,
  "title": "Senior AI Solutions Engineer",
  "description_text": "…plain text, HTML removed and entities decoded…",
  "employment": {"types": [{"value": "contractor_b2b", "status": "known"}], "hours": {"value": "full_time", "status": "known"}},
  "work_arrangement": {
    "mode": {"value": "remote", "status": "known"},
    "remote_eligibility": {"status": "known", "anywhere": false, "regions": ["EU"], "countries": [],
                            "timezone_offset_range_hours": [0, 2]},
    "locations": [{"raw": "Remote - EU", "country": "", "region": "EU", "city": "", "latitude": null, "longitude": null}]
  },
  "compensation": {"status": "unknown"},
  "seniority": {"levels": ["senior"], "years_required_min": 8, "status": "known"},
  "role_families": [{"key": "ai_solutions_engineering", "confidence": 0.93}],
  "sectors": {"primary": "enterprise_it", "secondary": ["finance_banking"], "status": "known"},
  "skills": {"required": [{"skill_id": 17, "importance": "must"}], "preferred": [{"skill_id": 52, "importance": "nice"}]},
  "languages_required": [{"language": "en", "level": "C1"}],
  "employer": {"company_id": 9, "type": {"value": "direct_employer", "status": "known"}},
  "education_required": {"level": "bachelor", "status": "known"},
  "benefits_mentioned": ["flexible_hours"],
  "visa_sponsorship": {"status": "unknown"},
  "posted_at": "2026-10-06T08:00:00Z",
  "valid_through": null,
  "source": {"source_type": "greenhouse", "external_job_id": "4461450008", "url": "https://job-boards.example/…", "apply_url": "https://…"}
}
```

`compensation` when known:

```json
{"status": "known", "form": "day_rate", "currency": "EUR", "min": 500, "max": 600, "period": "day", "disclosed": true,
 "assumptions": []}
```

- `form` is `annual_salary`, `day_rate` or `hourly_rate`; `period` the original period (`year`, `month`, `day`, `hour`).
- Conversion assumptions are applied by the evaluator only and are recorded in `assumptions`: hourly → day ×8 hours; monthly → annual × the intent's `payments_per_year` (12 or 14), unless the posting states the number of payments, in which case that number is used. The assumption used is shown in the evidence.
- Every attribute extracted by the AI also stores `confidence` (0–1) and `evidence` (a verbatim quote); see 6.

### 5.1 Greenhouse mapping (first source, ADR-015)

| Greenhouse field | Normalised field |
|---|---|
| `id` | `source.external_job_id` |
| `absolute_url` | `source.url` / `apply_url` |
| `title` | `title` |
| `content` (HTML-escaped HTML) | unescape, sanitise, then `description_text` |
| `location.name`, `offices[]` | `work_arrangement.locations[].raw` (normalised in 6.2) |
| `first_published` | `posted_at` |
| `updated_at` | change detection input (LLD §5) |
| `departments[]` | stored as `department` hint for role classification |
| `metadata[]` (custom fields) | stored raw; used as hints only (for example "Location Type") |
| `language` | `source.language` |

The board `name` identifies the company (section 9). No Greenhouse field gives seniority, compensation, work arrangement or skills reliably; those come from the description through the extractor.

## 6. AI extraction contract

### 6.1 Principles (refines ADR-021; see proposed ADR-027)

1. The AI **extracts attributes from the job once per snapshot, independent of any intent**. It is never given the intent or profile for this step, so one extraction serves every intent and profile.
2. Categorical dimensions (work arrangement, engagement, seniority, sector, employer type, role family) are scored **deterministically** from those attributes and the intent's stances.
3. The only profile-dependent AI step is the **skill-equivalence judgement** for skills that do not match by alias (cached per pair in `skill_relation`).
4. Evidence is mandatory: each extracted attribute carries a verbatim quote from the job description.
5. A failed or unavailable AI leaves the job **not evaluated**; nothing is guessed (ADR-021).

### 6.2 Run policy

- Extraction runs for each new or materially changed snapshot (LLD §5), queued in the worker, with at most 3 attempts and bounded timeouts.
- Prompt template `extract-v1`, temperature 0, description truncated to a fixed maximum (initial 12,000 characters) with a `truncated` flag stored.
- **Deterministic hints first**: structured source fields (Greenhouse location, department, dates, JSON-LD if present) are supplied as hints; the AI may confirm or contradict them, and contradictions are flagged.
- Output must validate against the extraction JSON schema (the object in section 5 plus `confidence` and `evidence` per attribute). One repair attempt is allowed; then the extraction is marked `failed`.
- **Evidence check:** each `evidence` quote must occur in the description after whitespace and case normalisation. If not, that attribute is downgraded to `unknown` and marked `evidence_unverified`.
- Locations are resolved to a country, region and city, and to coordinates through the offline gazetteer (the Python package `geonamescache`, MIT code; GeoNames data under CC BY 4.0, which requires visible attribution; it bundles cities above 15,000 inhabitants with latitude, longitude and IANA time zone). **Disambiguation:** prefer an exact primary-name match; use a country hint from the posting or company; otherwise the most populous match; if several countries remain possible and no hint exists, the location stays unresolved (`latitude = null`, hybrid/on-site distance is then `unknown`). Towns below the population threshold are unresolved; a larger gazetteer is a deferred improvement.

### 6.3 Stored result

| Table | Columns |
|---|---|
| `job_extraction` | `job_extraction_id`, `job_snapshot_id`, `status` (`pending`, `succeeded`, `failed`), `provider`, `model`, `prompt_version`, `taxonomy_version`, `truncated`, `attributes_json`, `error_class`, `latency_ms`, `created_at` |

Rows are queued as `pending` and finalised once (`succeeded` or `failed`), after which they are immutable (ADR-041); a new model or prompt version creates a new row and evaluations reference the extraction they used.

## 7. Matching policy `matching-v1`

### 7.1 Inputs and output

Input: a `job_extraction` (`succeeded`), the profile revision, the intent revision. Output: a `MatchEvaluation` with `recommendation`, `fit_score`, `gates_failed[]` and one `ScoreDimension` per dimension (including those with weight 0, flagged `excluded`).

### 7.2 Stance strengths

`preferred` = **1.0**, `acceptable` = **0.5**, `rejected` = 0 and sets a gate (7.6). For attributes with several values (for example a job open to two engagement types) the **best non-rejected stance** is used; the dimension is rejected only if **all** values are rejected. A role family or sector that the intent does not list is **unlisted**: strength 0, status `mismatch`, **no gate**.

### 7.3 Status and quality label

`status` is `match` (strength > 0), `mismatch` (attribute known, strength 0) or `unknown` (attribute missing or unverified). A derived `quality` label is shown beside `match`: **strong** (strength ≥ 0.75), **partial** (0.25 to < 0.75), **weak** (> 0 and < 0.25). Preferred therefore shows as a strong match and acceptable as a partial match.

### 7.4 Dimension rules

| Dimension | Strength rule |
|---|---|
| Role & responsibilities | Role families with `confidence ≥ 0.6`; strength = best stance strength among them; all rejected → gate; none known → `unknown` |
| Skills & technology | For each required skill (`must` weight 2, `nice` weight 1): coverage 1.0 if the profile has it (alias match; if the job states a level, the profile level must be at least one step below it, otherwise 0.75), 0.5 if the profile has a skill judged `equivalent` (or 0.25 if `related`), else 0. Strength = Σ(weight × coverage) ÷ Σ(weight). No skills extracted → `unknown`. A missing must-have is **not** a gate |
| Work arrangement & location | `mode` stance strength × place factor. **Remote:** place factor 1.0 if stated eligibility intersects the user's regions and the time-zone band is within tolerance; 0.8 if eligibility is not stated (risk, R-00172 F4); no intersection or band outside tolerance → gate. **Hybrid/on-site:** best location within `radius_km` of the base place → factor 1.0; all outside the radius → gate; coordinates unknown → `unknown` (no gate). A mode with stance `rejected` → gate |
| Engagement & contract terms | Best stance among engagement types; `strength = min(type strength, hours strength)` where hours strength is the `part_time` stance strength when the job is part-time, else 1.0; rejected type or hours → gate |
| Compensation | See 7.5 |
| Seniority & experience | Best stance among the levels the job allows (a "mid–senior" job allows both); all rejected → gate. Years required is informational in V1 |
| Domain & sector | Stance of the **primary** sector; `rejected` primary → gate even if a secondary sector is preferred; unlisted → mismatch without gate |
| Company profile | Stance of the employer type; `unknown` if not determined; `rejected` → gate |
| Benefits & flexibility (optional) | Fraction of `benefits_wanted` mentioned in the job; none stated → `unknown`; if `benefits_wanted` is empty the dimension is `unknown` |
| Career direction (optional, ADR-057, `matching-v1.3`) | The career directions (profile facts: up to 5 texts of up to 1,000 characters) are each judged by the local model against the job: `strong` 1.0, `partial` 0.5, `weak` 0.2, `none` 0 (mismatch, no gate), `unknown` = could not tell. The **best known level** among the enabled directions counts, chosen by the engine; all `unknown` → `unknown` (contributes 0, weight counts). A job with no judgement at all is **not assessed**: the dimension is left out and the other weights are renormalised, so old and new jobs stay comparable. Default weight 0. Evidence: winning direction, level, `job_quote` (verbatim from the posting), `direction_quote` (verbatim from the direction text) |
| Qualifications (optional) | Required education level and certifications vs the profile: all satisfied → 1.0; a missing required certification or lower education → `mismatch` (no gate); none required → `unknown` |

### 7.5 Compensation

1. Determine the **form**: employee types use the annual salary expectation; contractor and freelance use the day-rate expectation. If the user set no expectation for that form → `unknown`.
2. Convert the job pay to the user's form with the recorded assumptions (hourly → day ×8; monthly → annual × `payments_per_year`, see section 5). If the currency differs from the intent's currency → `unknown` (V1; currency conversion is a deferred improvement, section 12).
3. Let `lo`, `hi` be the job range (equal if a single figure), `p = (lo + hi) ÷ 2`, `m` the user's minimum and `t` the target.
   - `hi < m` → `mismatch`, strength 0; **gate** if `reject_below_minimum`.
   - `p ≥ t` → strength 1.0.
   - `p ≤ m` (but `hi ≥ m`) → strength 0.25.
   - otherwise strength = 0.25 + 0.75 × (p − m) ÷ (t − m).
4. No stated pay → `unknown`.

### 7.6 Gates

| Gate | Fires when |
|---|---|
| G1 role | all known role families are `rejected`, or (`matching-v1.6`, ADR-066) the primary one (the first listed that clears the confidence floor) is `rejected` |
| G2 arrangement | mode is `rejected`, or a remote eligibility/time-zone rule fails, or all hybrid/on-site locations are outside the radius, or (`matching-v1.5`, ADR-058) the arrangement is not stated and every placed location is outside the radius. Remote regions come from the model; when it names none, the source's own remote places (`Remote - USA`) are used. (`matching-v1.7`, ADR-068) A country or region with no remote word (`North America`) counts as a remote place when another place of the source carries a remote marker (`Remote`); a city does not. Region groups: `EU`, `EEA`, `EUROPE`, `UK`, `EMEA`, `AMERICAS`/`AMER`, `NORTH AMERICA`, `LATAM`, `APAC`, `WORLD` |
| G3 engagement | all engagement types are `rejected`, or hours are part-time and `part_time` is `rejected` |
| G4 seniority | all allowed levels are `rejected` |
| G5 sector | primary sector is `rejected` |
| G6 employer | employer type is `rejected` |
| G7 language | the job requires a language not in `can_work_in` and `reject_unspoken_required` is on |
| G8 company | the company is in `exclusions.companies` |
| G9 words | an excluded word occurs in the title or description (whole word) |
| G10 pay | stated pay is below the minimum and `reject_below_minimum` is on |
| G11 visa | the user needs visa/relocation help and the job states it is not offered |

A gate never fires on `unknown` data. All fired gates are listed with their reason and evidence; `recommendation` is `not_recommended` if any fired, otherwise `recommended`. The raw weighted score is still computed and shown.

### 7.7 Score

1. `effective_weight = weight ÷ Σ(all weights) × 100` (weights of 0 give effective weight 0 and the dimension is excluded).
2. `contribution = effective_weight × strength`; `unknown` and `mismatch` contribute 0 but their weight stays in the sum (ADR-005, ADR-024).
3. `fit_score = round(Σ contribution)`, clamped 0–100 (round half up).
4. Bands: Excellent 80–100, Strong 65–79, Average 45–64, Low 0–44; Not recommended overrides when gated.
5. Contributions are computed with fixed-point rounding to one decimal; ties in ordering are broken by `first_seen_at` descending then `job_opportunity_id` ascending, so results are reproducible.

**Worked example.** Default weights; strengths: role 1.0, skills 0.8, arrangement 1.0 (remote preferred, EU eligible), engagement 1.0, compensation unknown, seniority 1.0, sector 0.5, company 1.0 → contributions 25 + 12 + 15 + 10 + 0 + 8 + 5 + 7 = **82**, Excellent fit. Raising the compensation weight from 10 to 30 changes the weight sum to 120, so the same job scores **68** (every other contribution shrinks by 100/120 and compensation adds nothing because it is unknown), which is why the weights screen shows an impact preview.

## 8. Evaluation persistence

| Table | Columns |
|---|---|
| `match_evaluation` | `match_evaluation_id`, `job_snapshot_id`, `job_extraction_id`, `profile_revision_id`, `intent_revision_id`, `policy_version`, `direction_basis` (`none` or the hash of the direction judgements used), `fit_score`, `recommendation`, `gates_json`, `weights_json`, `created_at` |
| `score_dimension` | `score_dimension_id`, `match_evaluation_id`, `dimension_key`, `status`, `quality`, `weight`, `effective_weight`, `strength`, `contribution`, `excluded` (weight 0), `evidence_json`, `explanation` |

`direction_judgement` (append-only, ADR-057): `direction_judgement_id`, `job_snapshot_id`, `direction_hash` (SHA-256 of the direction text), `direction_label`, `provider`, `model`, `prompt_version` (`direction-v1`), `level`, `job_quote`, `direction_quote`, `created_at`. A late judgement gives a new evaluation (new `direction_basis`); the old one stays.

`job_summary` (append-only, ADR-059): `job_summary_id`, `job_snapshot_id`, `provider`, `model`, `prompt_version` (`summary-v1`), `status` (`succeeded` or `failed`), `summary_text` (null when failed), `error_class`, `latency_ms`, `created_at`. One successful summary per snapshot, provider, model and prompt version; failed attempts may repeat. A summary is prose for the owner to read, never an input of the score.

`evidence_json` holds the job quote, the profile fact or intent option compared, and for skills the `skill_relation` rows used. Re-scoring an old job with new weights creates a **new** evaluation from the same `job_extraction` and cached relations, with no AI call, unless a skill pair has never been judged.

## 9. Company

| Table | Columns |
|---|---|
| `company` | `company_id`, `canonical_name`, `name_normalised`, `homepage_url`, `careers_url`, `employer_type` (`direct_employer`, `agency_recruiter`, `consultancy_outsourcer`, or null), `employer_type_origin` (`source`, `ai_inference`, `user`), `created_at`, `updated_at` |
| `company_alias` | `company_alias_id`, `company_id`, `alias_normalised` |
| `company_fact` | `company_fact_id`, `company_id`, `fact_key`, `value_json`, `origin` (`source`, `public_dataset`, `ai_inference`, `user`), `source_name`, `source_url`, `retrieved_at`, `licence`, `confidence`, `superseded_at` |
| `source_configuration` | gains `company_id` (one board belongs to one company) |

Fact keys: `homepage`, `description`, `industry`, `employee_count`, `headquarters`, `founded_year`, `legal_entity` (LEI), `technologies`, `stage`. `homepage_url` and `careers_url` on `company` are the current accepted values of those facts.

**Identity and enrichment (ADR-025, R-00171):**
1. A company is created when a board is added; its name comes from the board.
2. Enrichment queries Wikidata (primary), GLEIF, Wikipedia summary (with attribution) and GitHub organisation data.
3. A candidate is accepted automatically only if its official-website domain equals the domain of the known careers/board URL; otherwise it is stored as `unmatched` for the user to confirm or reject in the dossier.
4. Every stored fact keeps source, retrieval date and licence; superseded facts are kept with `superseded_at`.
5. AI-written summaries are facts with origin `ai_inference` and are always displayed with that label.

**Company list** (`GET /companies`): for each company the counts `new_offers_7d/15d/30d` (opportunities first seen in the window) and `relevant_new_offers_*` (same, with a latest evaluation under the active intent at or above the relevance threshold and not `not_recommended`). The default sort is the chosen window, descending; search is by `name_normalised` and aliases.

## 10. Duplicate handling `dedup-v1` (ADR-023)

### 10.1 Records

| Table | Columns |
|---|---|
| `job_posting` | one per source listing, unique `(source_configuration_id, external_job_id)` (exact identity within a source) |
| `job_opportunity` | `job_opportunity_id`, `company_id`, `primary_job_posting_id`, `first_seen_at`, `last_seen_at`, `closed_at` (nullable) |
| `job_opportunity_link` | `job_opportunity_link_id`, `job_opportunity_id`, `job_posting_id`, `state` (`auto`, `possible`, `confirmed`, `rejected`), `similarity`, `features_json`, `method`, `decided_by_user_at`, `created_at` |

A posting with no match gets its own opportunity. The **inbox item is keyed by opportunity** (`job_inbox_item` uses `job_opportunity_id`; decision D7), and evaluation runs on the primary posting's latest snapshot.

### 10.2 Matching rules

Two listings are candidates only if they belong to the **same company** and have **compatible location** (identical normalised location sets, or both remote with intersecting eligibility). Different locations are different opportunities (the same title in several cities is common, as seen in the Greenhouse test data).

Similarity = `0.35 × title_similarity + 0.45 × description_similarity + 0.10 × date_proximity + 0.10 × location_match`, where:
- `title_similarity`: token-set ratio on normalised titles (0–1);
- `description_similarity`: cosine of text embeddings from the local model when available, otherwise Jaccard on 5-word shingles (0–1);
- `date_proximity`: 1 if the posting dates differ by ≤ 14 days, 0.5 if ≤ 30, else 0;
- `location_match`: 1 for identical, 0.5 for overlapping.

| Result | Action |
|---|---|
| similarity ≥ 0.90 and location identical | `auto` link |
| 0.75 ≤ similarity < 0.90 | `possible` link, surfaced for the user |
| below 0.75 | distinct opportunities |

Two listings from the **same source and board** are never auto-linked (several openings with identical text are legitimate); they may be flagged `possible` at similarity ≥ 0.95. The primary posting is the one from the employer's own ATS or careers site (preferred), then the earliest `first_seen_at`. The user can confirm or reject a link; `rejected` pairs are never proposed again. Thresholds and weights are **initial values** to be tuned on synthetic fixtures and real data; they are constants of `dedup-v1`.

## 11. Lifecycle and trends (ADR-022)

### 11.1 Lifecycle

`first_seen_at` is set when a posting appears; `last_seen_at` is updated on each run that still lists it; a posting not listed by two consecutive successful runs of its source sets `closed_at` (a failed run never closes anything). An opportunity is open while any linked posting is open.

### 11.2 Weekly aggregates

| Table | Columns |
|---|---|
| `trend_weekly` | `trend_weekly_id`, `owner_id`, `search_intent_id`, `intent_revision_id`, `week_start`, `term_kind` (`skill`, `role_family`, `sector`, `work_arrangement`, `seniority_level`, `engagement_type`), `term_key`, `taxonomy_version`, `relevance_min_score`, `open_count`, `new_count`, `closed_count`, `relevant_total_open`, `source_set_hash`, `computed_at` |

Computed weekly (and on demand) from extractions and evaluations. **Relevant** means: the opportunity's latest evaluation under the intent has `fit_score ≥ relevance_min_score` (default 45) and is not `not_recommended`.

Three safeguards, because trend charts can mislead:
1. **Share, not only counts.** Adding sources raises counts. The UI shows `open_count ÷ relevant_total_open` by default and marks weeks where `source_set_hash` changed.
2. **Intent changes break comparability.** A change of `intent_revision_id` is shown as a marker on the chart; the UI states the revision used.
3. **Only available history is shown.** The UI states the first available week; longer periods unlock as data accumulates.

Terms are resolved through `replaced_by` so merged taxonomy terms keep one continuous line.

## 12. Limits, non-goals and deferred improvements

Not scored in V1: company size and stage, years of experience required, benefits unless `benefits_wanted` is set, and posting age (a filter). No online geocoding service (offline gazetteer only). The AI never sees the intent or profile during job extraction. Salary conversion assumptions are conservative and always recorded.

**Deferred improvements (backlog, to be done after V1 works):**
1. **Currency conversion** using stored reference exchange rates, so pay in other currencies can be compared instead of being `unknown`.
2. **ESCO mapping** for skills and occupations (`esco_uri` stays nullable).
3. A larger gazetteer for towns below 15,000 inhabitants.
4. Tuning of stance strengths, quality thresholds and duplicate thresholds with real data.

## 13. Owner decisions (recorded 2026-10-08)

| ID | Decision | Outcome |
|---|---|---|
| D1 | Coordinates for hybrid/on-site distance | **Accepted:** offline gazetteer. Licence verified: GeoNames data is CC BY 4.0 (attribution required, shown in the app's About/credits); the `geonamescache` package is MIT. Fields include latitude, longitude and IANA time zone (verified) |
| D2 | Currency conversion | **Accepted for V1:** same currency only, otherwise `unknown`. Conversion is a pending improvement (section 12) |
| D3 | Embeddings for duplicate detection | **Accepted:** local embedding model when available, shingle fallback |
| D4 | Stance strengths 1.0 / 0.5 and quality thresholds 0.75 / 0.25 | **Accepted** as initial `matching-v1` constants |
| D5 | Unlisted role families and sectors score 0 without a gate | **Accepted** |
| D6 | Initial taxonomy lists (section 2.1) | **Accepted** |
| D7 | Inbox keyed by opportunity | **Accepted:** `job_inbox_item` uses `job_opportunity_id`; LLD updated |
| D8 | ESCO mapping | **Deferred**, `esco_uri` nullable |
| D9 | Monthly versus annual pay | **Accepted with change:** employee pay has two linked fields (monthly and annual) and a 12/14-payments choice; annual is canonical; contractor pay is a day rate only (section 4.1) |
| D10 | ADR-027 two-stage AI | **Accepted** |
