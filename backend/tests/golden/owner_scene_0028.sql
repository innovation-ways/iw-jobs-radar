--
-- PostgreSQL database dump
--


-- Dumped from database version 18.6 (Debian 18.6-1.pgdg13+2)
-- Dumped by pg_dump version 18.6 (Debian 18.6-1.pgdg13+2)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Data for Name: owner; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

SET SESSION AUTHORIZATION DEFAULT;

ALTER TABLE public.owner DISABLE TRIGGER ALL;

INSERT INTO public.owner (owner_id, display_name, updated_at, created_at) VALUES (1, 'Local owner', '2026-10-20 11:47:07.93018+00', '2026-10-20 11:47:07.93018+00');


ALTER TABLE public.owner ENABLE TRIGGER ALL;

--
-- Data for Name: career_profile; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.career_profile DISABLE TRIGGER ALL;

INSERT INTO public.career_profile (career_profile_id, owner_id, title, visibility, current_profile_revision_id, version, updated_at, created_at) VALUES (1, 1, 'Profile-0d4991bc', 'private', 1, 1, '2026-10-20 11:47:08.061091+00', '2026-10-20 11:47:08.061091+00');


ALTER TABLE public.career_profile ENABLE TRIGGER ALL;

--
-- Data for Name: company; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.company DISABLE TRIGGER ALL;

INSERT INTO public.company (company_id, canonical_name, name_normalised, homepage_url, careers_url, employer_type, employer_type_origin, updated_at, created_at, enriched_at) VALUES (1, 'Synthetic Co-4ee1be7f', 'synthetic co-4ee1be7f', NULL, NULL, NULL, NULL, '2026-10-20 11:47:08.061091+00', '2026-10-20 11:47:08.061091+00', NULL);


ALTER TABLE public.company ENABLE TRIGGER ALL;

--
-- Data for Name: source_configuration; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.source_configuration DISABLE TRIGGER ALL;

INSERT INTO public.source_configuration (source_configuration_id, owner_id, company_id, source_type, external_identifier, display_name, url, enabled, rate_limit_per_minute, config_json, credential_ciphertext, credential_updated_at, etag, version, updated_at, created_at) VALUES (1, 1, 1, 'greenhouse', 'board-8121fc5e', 'Synthetic Co-4ee1be7f', 'https://boards.example.test/v1/boards/board-8121fc5e/jobs', true, 6, '{}', NULL, NULL, NULL, 1, '2026-10-20 11:47:08.061091+00', '2026-10-20 11:47:08.061091+00');


ALTER TABLE public.source_configuration ENABLE TRIGGER ALL;

--
-- Data for Name: job_posting; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.job_posting DISABLE TRIGGER ALL;

INSERT INTO public.job_posting (job_posting_id, source_configuration_id, company_id, external_job_id, source_type, source_url, title, current_content_hash, first_seen_at, last_seen_at, closed_at, updated_at, created_at) VALUES (1, 1, 1, 'job-1accc985', 'greenhouse', 'https://jobs.example.test/1', 'Senior AI Solutions Engineer', 'sha256:6db0fc61ce8860dac1bce49c75c61c9b8fadfba6cb99b401e99fde5aa189810f', '2026-10-08 12:00:00+00', '2026-10-08 12:00:00+00', NULL, '2026-10-20 11:47:08.061091+00', '2026-10-20 11:47:08.061091+00');


ALTER TABLE public.job_posting ENABLE TRIGGER ALL;

--
-- Data for Name: job_snapshot; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.job_snapshot DISABLE TRIGGER ALL;

INSERT INTO public.job_snapshot (job_snapshot_id, job_posting_id, content_hash, fetched_at, raw_payload_json, normalised_json, created_at) VALUES (1, 1, 'sha256:6db0fc61ce8860dac1bce49c75c61c9b8fadfba6cb99b401e99fde5aa189810f', '2026-10-08 12:00:00+00', '{"id": "job-1accc985"}', '{"title": "Senior AI Solutions Engineer", "skills": {"required": [{"skill_id": 17, "importance": "must"}], "preferred": [{"skill_id": 52, "importance": "nice"}]}, "source": {"url": "https://jobs.example.test/4461450008", "language": "en", "apply_url": "https://jobs.example.test/4461450008/apply", "source_type": "greenhouse", "external_job_id": "4461450008"}, "sectors": {"status": "known", "primary": "enterprise_it", "secondary": ["finance_banking"]}, "employer": {"type": {"value": "direct_employer", "status": "known"}, "company_id": 9}, "posted_at": "2026-10-06T08:00:00Z", "seniority": {"levels": ["senior"], "status": "known", "years_required_min": 8}, "employment": {"hours": {"value": "full_time", "status": "known"}, "types": [{"value": "contractor_b2b", "status": "known"}]}, "compensation": {"status": "unknown"}, "role_families": [{"key": "ai_solutions_engineering", "confidence": 0.93}], "valid_through": null, "schema_version": 1, "description_text": "Design and evaluate LLM-powered features. Fully remote within EU time zones.", "visa_sponsorship": {"status": "unknown", "offered": null}, "work_arrangement": {"mode": {"value": "remote", "status": "known"}, "locations": [{"raw": "Remote - EU", "city": "", "region": "EU", "country": "", "latitude": null, "longitude": null}], "remote_eligibility": {"status": "known", "regions": ["EU"], "anywhere": false, "countries": [], "timezone_offset_range_hours": [0, 2]}}, "benefits_mentioned": ["flexible_hours"], "education_required": {"level": "bachelor", "status": "known"}, "languages_required": [{"level": "C1", "language": "en"}]}', '2026-10-20 11:47:08.061091+00');


ALTER TABLE public.job_snapshot ENABLE TRIGGER ALL;

--
-- Data for Name: profile_revision; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.profile_revision DISABLE TRIGGER ALL;

INSERT INTO public.profile_revision (profile_revision_id, career_profile_id, revision_number, facts_json, privacy_json, change_summary, created_at) VALUES (1, 1, 1, '{"skills": [{"level": "expert", "years": 10.0, "skill_id": 17, "provenance": {"origin": "document", "accepted_at": "2026-10-08T10:00:00Z", "evidence_id": 41}}, {"level": "advanced", "years": 4.0, "skill_id": 18, "provenance": {"origin": "manual", "accepted_at": null, "evidence_id": null}}], "headline": "AI solutions and integration engineer", "education": [{"field": "Computer Science", "level": "msc", "provenance": {"origin": "manual", "accepted_at": null, "evidence_id": null}}], "languages": [{"level": "native", "language": "pt"}, {"level": "C1", "language": "en"}], "directions": [], "experience": [{"end": "2024-06", "start": "2019-01", "title": "Solutions Architect", "sectors": ["telecom", "enterprise_it"], "summary": "Led integration of machine-learning features into telecom platforms.", "provenance": {"origin": "manual", "accepted_at": null, "evidence_id": null}, "organisation": "Example Corp"}], "base_location": {"place": "Lisbon, Portugal", "country": "PT", "latitude": 38.72, "timezone": "Europe/Lisbon", "longitude": -9.14}, "certifications": [{"name": "Example Certification", "year": 2022, "provenance": {"origin": "manual", "accepted_at": null, "evidence_id": null}}], "schema_version": 1, "years_experience": 12}', '{"schema_version": 1, "allow_cloud_processing": false, "redact_contact_details": true}', NULL, '2026-10-20 11:47:08.061091+00');


ALTER TABLE public.profile_revision ENABLE TRIGGER ALL;

--
-- Data for Name: application_draft; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.application_draft DISABLE TRIGGER ALL;



ALTER TABLE public.application_draft ENABLE TRIGGER ALL;

--
-- Data for Name: audit_event; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.audit_event DISABLE TRIGGER ALL;

INSERT INTO public.audit_event (audit_event_id, owner_id, action, subject_type, metadata_json, created_at) VALUES (1, 1, 'synthetic', 'test', '{}', '2026-10-20 11:47:08.061091+00');


ALTER TABLE public.audit_event ENABLE TRIGGER ALL;

--
-- Data for Name: collection_run; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.collection_run DISABLE TRIGGER ALL;

INSERT INTO public.collection_run (collection_run_id, owner_id, trigger, status, scheduled_for, requested_at, started_at, finished_at, error_class, worker_name, version, updated_at, created_at, source_configuration_id) VALUES (1, 1, 'manual', 'succeeded', NULL, '2026-10-20 11:47:08.061091+00', NULL, NULL, NULL, NULL, 1, '2026-10-20 11:47:08.061091+00', '2026-10-20 11:47:08.061091+00', NULL);


ALTER TABLE public.collection_run ENABLE TRIGGER ALL;

--
-- Data for Name: company_alias; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.company_alias DISABLE TRIGGER ALL;



ALTER TABLE public.company_alias ENABLE TRIGGER ALL;

--
-- Data for Name: company_enrichment_candidate; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.company_enrichment_candidate DISABLE TRIGGER ALL;



ALTER TABLE public.company_enrichment_candidate ENABLE TRIGGER ALL;

--
-- Data for Name: company_fact; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.company_fact DISABLE TRIGGER ALL;



ALTER TABLE public.company_fact ENABLE TRIGGER ALL;

--
-- Data for Name: company_follow; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.company_follow DISABLE TRIGGER ALL;



ALTER TABLE public.company_follow ENABLE TRIGGER ALL;

--
-- Data for Name: company_ignore; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.company_ignore DISABLE TRIGGER ALL;



ALTER TABLE public.company_ignore ENABLE TRIGGER ALL;

--
-- Data for Name: direction_judgement; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.direction_judgement DISABLE TRIGGER ALL;



ALTER TABLE public.direction_judgement ENABLE TRIGGER ALL;

--
-- Data for Name: document; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.document DISABLE TRIGGER ALL;



ALTER TABLE public.document ENABLE TRIGGER ALL;

--
-- Data for Name: evidence; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.evidence DISABLE TRIGGER ALL;

INSERT INTO public.evidence (evidence_id, owner_id, origin, document_id, excerpt, confidence, accepted_at, created_at) VALUES (1, 1, 'manual', NULL, NULL, NULL, '2026-10-08 12:00:00+00', '2026-10-20 11:47:08.061091+00');


ALTER TABLE public.evidence ENABLE TRIGGER ALL;

--
-- Data for Name: job_opportunity; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.job_opportunity DISABLE TRIGGER ALL;

INSERT INTO public.job_opportunity (job_opportunity_id, company_id, primary_job_posting_id, first_seen_at, last_seen_at, closed_at, updated_at, created_at) VALUES (1, 1, 1, '2026-10-08 12:00:00+00', '2026-10-08 12:00:00+00', NULL, '2026-10-20 11:47:08.061091+00', '2026-10-20 11:47:08.061091+00');


ALTER TABLE public.job_opportunity ENABLE TRIGGER ALL;

--
-- Data for Name: job_inbox_item; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.job_inbox_item DISABLE TRIGGER ALL;

INSERT INTO public.job_inbox_item (job_inbox_item_id, owner_id, job_opportunity_id, state, is_shortlisted, read_at, ignore_reason, note, applied_at, application_url, version, updated_at, created_at) VALUES (1, 1, 1, 'unread', false, NULL, NULL, NULL, NULL, NULL, 1, '2026-10-20 11:47:08.061091+00', '2026-10-20 11:47:08.061091+00');


ALTER TABLE public.job_inbox_item ENABLE TRIGGER ALL;

--
-- Data for Name: inbox_event; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.inbox_event DISABLE TRIGGER ALL;

INSERT INTO public.inbox_event (inbox_event_id, job_inbox_item_id, action, actor, from_state, to_state, metadata_json, created_at) VALUES (1, 1, 'surface_new', 'system', NULL, 'unread', '{}', '2026-10-20 11:47:08.061091+00');


ALTER TABLE public.inbox_event ENABLE TRIGGER ALL;

--
-- Data for Name: integration_credential; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.integration_credential DISABLE TRIGGER ALL;



ALTER TABLE public.integration_credential ENABLE TRIGGER ALL;

--
-- Data for Name: search_intent; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.search_intent DISABLE TRIGGER ALL;

INSERT INTO public.search_intent (search_intent_id, owner_id, career_profile_id, title, enabled, current_intent_revision_id, version, updated_at, created_at) VALUES (1, 1, 1, 'Intent-e70b2a58', true, 1, 1, '2026-10-20 11:47:08.061091+00', '2026-10-20 11:47:08.061091+00');


ALTER TABLE public.search_intent ENABLE TRIGGER ALL;

--
-- Data for Name: intent_revision; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.intent_revision DISABLE TRIGGER ALL;

INSERT INTO public.intent_revision (intent_revision_id, search_intent_id, revision_number, intent_json, change_summary, created_at) VALUES (1, 1, 1, '{"title": "AI & telecom billing — remote first", "filters": {"max_posting_age_days": null, "needs_visa_or_relocation": false}, "stances": {"hours": {"part_time": "rejected"}, "sectors": [{"key": "telecom", "stance": "preferred"}, {"key": "enterprise_it", "stance": "preferred"}, {"key": "finance_banking", "stance": "acceptable"}, {"key": "gambling", "stance": "rejected"}], "role_families": [{"key": "ai_solutions_engineering", "stance": "preferred"}, {"key": "telecom_billing_bss_oss", "stance": "preferred"}, {"key": "software_engineering_general", "stance": "acceptable"}, {"key": "data_analysis", "stance": "rejected"}, {"key": "sales_account_management", "stance": "rejected"}], "employer_types": [{"key": "direct_employer", "stance": "preferred"}, {"key": "agency_recruiter", "stance": "acceptable"}, {"key": "consultancy_outsourcer", "stance": "acceptable"}], "engagement_types": [{"key": "employee_permanent", "stance": "acceptable"}, {"key": "employee_fixed_term", "stance": "acceptable"}, {"key": "contractor_b2b", "stance": "preferred"}, {"key": "freelance", "stance": "preferred"}, {"key": "internship", "stance": "rejected"}], "seniority_levels": [{"key": "intern", "stance": "rejected"}, {"key": "junior", "stance": "rejected"}, {"key": "mid", "stance": "acceptable"}, {"key": "senior", "stance": "preferred"}, {"key": "staff_principal", "stance": "preferred"}, {"key": "management", "stance": "acceptable"}, {"key": "executive", "stance": "acceptable"}], "work_arrangements": [{"key": "remote", "stance": "preferred"}, {"key": "hybrid", "stance": "acceptable"}, {"key": "onsite", "stance": "acceptable"}]}, "weights": {"compensation": 10, "domain_sector": 10, "qualifications": 0, "company_profile": 7, "career_direction": 0, "engagement_terms": 10, "skills_technology": 15, "benefits_flexibility": 0, "seniority_experience": 8, "role_responsibilities": 25, "work_arrangement_location": 15}, "keywords": ["LLM", "RAG", "billing", "charging", "mediation"], "languages": {"can_work_in": ["pt", "en"], "reject_unspoken_required": true}, "exclusions": {"words": ["unpaid", "internship"], "companies": ["Harbor Systems"]}, "work_rules": {"remote": {"timezone": "Europe/Lisbon", "eligible_regions": ["EU", "UK"], "timezone_tolerance_hours": 2}, "onsite_hybrid": {"latitude": 38.72, "longitude": -9.14, "radius_km": 40, "base_place": "Lisbon, Portugal"}}, "compensation": {"employee_pay": {"currency": "EUR", "annual_target": 75000.0, "annual_minimum": 60000.0, "payments_per_year": 14}, "contractor_day_rate": {"target": 550.0, "minimum": 450.0, "currency": "EUR"}, "reject_below_minimum": true}, "schema_version": 1, "alert_threshold": 65, "benefits_wanted": []}', NULL, '2026-10-20 11:47:08.061091+00');


ALTER TABLE public.intent_revision ENABLE TRIGGER ALL;

--
-- Data for Name: job_change_event; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.job_change_event DISABLE TRIGGER ALL;

INSERT INTO public.job_change_event (job_change_event_id, job_posting_id, from_job_snapshot_id, to_job_snapshot_id, changed_fields, is_material, created_at) VALUES (1, 1, NULL, 1, '["title"]', true, '2026-10-20 11:47:08.061091+00');


ALTER TABLE public.job_change_event ENABLE TRIGGER ALL;

--
-- Data for Name: taxonomy_version; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.taxonomy_version DISABLE TRIGGER ALL;

INSERT INTO public.taxonomy_version (taxonomy_version_id, description, created_at) VALUES (1, 'seed', '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_version (taxonomy_version_id, description, created_at) VALUES (2, 'non-technical role families (ADR-060)', '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_version (taxonomy_version_id, description, created_at) VALUES (3, 'agency contract engagement type (ADR-073)', '2026-10-20 11:47:07.93018+00');


ALTER TABLE public.taxonomy_version ENABLE TRIGGER ALL;

--
-- Data for Name: job_extraction; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.job_extraction DISABLE TRIGGER ALL;

INSERT INTO public.job_extraction (job_extraction_id, job_snapshot_id, status, provider, model, prompt_version, taxonomy_version_id, truncated, attributes_json, error_class, attempts, latency_ms, claimed_at, completed_at, created_at, failure_json) VALUES (1, 1, 'succeeded', 'ollama', 'model-15dfd054', 'extract-v2', 1, false, '{}', NULL, 1, NULL, NULL, NULL, '2026-10-20 11:47:08.061091+00', NULL);


ALTER TABLE public.job_extraction ENABLE TRIGGER ALL;

--
-- Data for Name: job_opportunity_link; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.job_opportunity_link DISABLE TRIGGER ALL;

INSERT INTO public.job_opportunity_link (job_opportunity_link_id, job_opportunity_id, job_posting_id, state, similarity, features_json, method, decided_by_user_at, updated_at, created_at) VALUES (1, 1, 1, 'auto', 1.0000, '{}', 'dedup-v1', NULL, '2026-10-20 11:47:08.061091+00', '2026-10-20 11:47:08.061091+00');


ALTER TABLE public.job_opportunity_link ENABLE TRIGGER ALL;

--
-- Data for Name: job_summary; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.job_summary DISABLE TRIGGER ALL;



ALTER TABLE public.job_summary ENABLE TRIGGER ALL;

--
-- Data for Name: match_evaluation; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.match_evaluation DISABLE TRIGGER ALL;

INSERT INTO public.match_evaluation (match_evaluation_id, job_snapshot_id, job_extraction_id, profile_revision_id, intent_revision_id, policy_version, job_source_hash, fit_score, recommendation, gates_json, weights_json, created_at, direction_basis) VALUES (1, 1, 1, 1, 1, 'matching-v1', 'sha256:6db0fc61ce8860dac1bce49c75c61c9b8fadfba6cb99b401e99fde5aa189810f', 82, 'recommended', '[]', '{}', '2026-10-20 11:47:08.061091+00', 'none');


ALTER TABLE public.match_evaluation ENABLE TRIGGER ALL;

--
-- Data for Name: page_reader_configuration; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.page_reader_configuration DISABLE TRIGGER ALL;



ALTER TABLE public.page_reader_configuration ENABLE TRIGGER ALL;

--
-- Data for Name: privacy_setting; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.privacy_setting DISABLE TRIGGER ALL;



ALTER TABLE public.privacy_setting ENABLE TRIGGER ALL;

--
-- Data for Name: profile_proposal; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.profile_proposal DISABLE TRIGGER ALL;



ALTER TABLE public.profile_proposal ENABLE TRIGGER ALL;

--
-- Data for Name: proposal_item; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.proposal_item DISABLE TRIGGER ALL;



ALTER TABLE public.proposal_item ENABLE TRIGGER ALL;

--
-- Data for Name: provider_connection; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.provider_connection DISABLE TRIGGER ALL;



ALTER TABLE public.provider_connection ENABLE TRIGGER ALL;

--
-- Data for Name: schedule_setting; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.schedule_setting DISABLE TRIGGER ALL;



ALTER TABLE public.schedule_setting ENABLE TRIGGER ALL;

--
-- Data for Name: score_dimension; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.score_dimension DISABLE TRIGGER ALL;

INSERT INTO public.score_dimension (score_dimension_id, match_evaluation_id, dimension_key, status, quality, weight, effective_weight, strength, contribution, excluded, evidence_json, explanation, created_at) VALUES (1, 1, 'skills_technology', 'match', 'strong', 15, 15.0000, 0.8000, 12.0000, false, '{}', 'Synthetic explanation.', '2026-10-20 11:47:08.061091+00');


ALTER TABLE public.score_dimension ENABLE TRIGGER ALL;

--
-- Data for Name: skill; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.skill DISABLE TRIGGER ALL;



ALTER TABLE public.skill ENABLE TRIGGER ALL;

--
-- Data for Name: skill_alias; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.skill_alias DISABLE TRIGGER ALL;



ALTER TABLE public.skill_alias ENABLE TRIGGER ALL;

--
-- Data for Name: skill_candidate; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.skill_candidate DISABLE TRIGGER ALL;



ALTER TABLE public.skill_candidate ENABLE TRIGGER ALL;

--
-- Data for Name: skill_relation; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.skill_relation DISABLE TRIGGER ALL;



ALTER TABLE public.skill_relation ENABLE TRIGGER ALL;

--
-- Data for Name: source_run_result; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.source_run_result DISABLE TRIGGER ALL;

INSERT INTO public.source_run_result (source_run_result_id, collection_run_id, source_configuration_id, started_at, finished_at, outcome, collected_count, new_count, updated_count, deduplicated_count, closed_count, http_status, error_class, error_message, duration_ms, created_at, dropped_count) VALUES (1, 1, 1, '2026-10-08 12:00:00+00', '2026-10-08 12:00:00+00', 'success', 0, 0, 0, 0, 0, NULL, NULL, NULL, 10, '2026-10-20 11:47:08.061091+00', 0);


ALTER TABLE public.source_run_result ENABLE TRIGGER ALL;

--
-- Data for Name: taxonomy_term; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.taxonomy_term DISABLE TRIGGER ALL;

INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (1, 'role_family', 'ai_solutions_engineering', 'AI solutions engineering', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (2, 'role_family', 'ai_ml_engineering', 'AI / ML engineering', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (3, 'role_family', 'data_engineering', 'Data engineering', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (4, 'role_family', 'data_analysis', 'Data analysis', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (5, 'role_family', 'software_engineering_general', 'Software engineering general', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (6, 'role_family', 'backend_engineering', 'Backend engineering', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (7, 'role_family', 'frontend_engineering', 'Frontend engineering', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (8, 'role_family', 'devops_platform', 'DevOps / platform', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (9, 'role_family', 'solutions_architecture', 'Solutions architecture', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (10, 'role_family', 'enterprise_architecture', 'Enterprise architecture', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (11, 'role_family', 'telecom_billing_bss_oss', 'Telecom billing (BSS/OSS)', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (12, 'role_family', 'product_management', 'Product management', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (13, 'role_family', 'project_programme_management', 'Project and programme management', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (14, 'role_family', 'consulting_integration', 'Consulting integration', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (15, 'role_family', 'ai_governance_risk', 'AI governance and risk', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (16, 'role_family', 'security', 'Security', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (17, 'role_family', 'qa_testing', 'QA and testing', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (18, 'role_family', 'sales_account_management', 'Sales account management', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (19, 'role_family', 'customer_support', 'Customer support', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (20, 'role_family', 'other', 'Other', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (21, 'sector', 'telecom', 'Telecom', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (22, 'sector', 'enterprise_it', 'Enterprise IT', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (23, 'sector', 'software_saas', 'Software / SaaS', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (24, 'sector', 'finance_banking', 'Finance and banking', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (25, 'sector', 'insurance', 'Insurance', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (26, 'sector', 'public_sector', 'Public sector', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (27, 'sector', 'healthcare', 'Healthcare', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (28, 'sector', 'retail_ecommerce', 'Retail and e-commerce', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (29, 'sector', 'manufacturing_industrial', 'Manufacturing and industrial', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (30, 'sector', 'energy_utilities', 'Energy and utilities', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (31, 'sector', 'logistics_transport', 'Logistics and transport', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (32, 'sector', 'media_entertainment', 'Media and entertainment', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (33, 'sector', 'education', 'Education', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (34, 'sector', 'consulting_services', 'Consulting services', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (35, 'sector', 'gambling', 'Gambling', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (36, 'sector', 'defence_aerospace', 'Defence and aerospace', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (37, 'sector', 'other', 'Other', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (38, 'seniority_level', 'intern', 'Intern', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (39, 'seniority_level', 'junior', 'Junior', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (40, 'seniority_level', 'mid', 'Mid', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (41, 'seniority_level', 'senior', 'Senior', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (42, 'seniority_level', 'staff_principal', 'Staff / Principal', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (43, 'seniority_level', 'management', 'Management', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (44, 'seniority_level', 'executive', 'Executive', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (45, 'engagement_type', 'employee_permanent', 'Permanent employee', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (46, 'engagement_type', 'employee_fixed_term', 'Fixed-term employee', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (47, 'engagement_type', 'contractor_b2b', 'Contractor / B2B', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (48, 'engagement_type', 'freelance', 'Freelance', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (49, 'engagement_type', 'internship', 'Internship', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (50, 'work_arrangement', 'remote', 'Remote', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (51, 'work_arrangement', 'hybrid', 'Hybrid', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (52, 'work_arrangement', 'onsite', 'On-site', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (53, 'employer_type', 'direct_employer', 'Direct employer', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (54, 'employer_type', 'agency_recruiter', 'Agency / recruiter', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (55, 'employer_type', 'consultancy_outsourcer', 'Consultancy / outsourcer', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (56, 'benefit', 'equity', 'Equity', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (57, 'benefit', 'bonus', 'Bonus', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (58, 'benefit', 'learning_budget', 'Learning budget', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (59, 'benefit', 'flexible_hours', 'Flexible hours', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (60, 'benefit', 'four_day_week', 'Four-day week', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (61, 'benefit', 'health_insurance', 'Health insurance', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (62, 'benefit', 'extra_leave', 'Extra leave', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (63, 'benefit', 'relocation_support', 'Relocation support', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (64, 'benefit', 'home_office_budget', 'Home office budget', 'seed', NULL, 1, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (65, 'role_family', 'finance_accounting', 'Finance and accounting', 'seed', NULL, 2, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (66, 'role_family', 'legal_compliance', 'Legal and compliance', 'seed', NULL, 2, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (67, 'role_family', 'hr_recruiting', 'HR and recruiting', 'seed', NULL, 2, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (68, 'role_family', 'marketing_communications', 'Marketing and communications', 'seed', NULL, 2, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (69, 'role_family', 'operations_admin', 'Operations and administration', 'seed', NULL, 2, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (70, 'role_family', 'design_creative', 'Design and creative', 'seed', NULL, 2, '2026-10-20 11:47:07.93018+00');
INSERT INTO public.taxonomy_term (taxonomy_term_id, kind, term_key, label, origin, replaced_by_taxonomy_term_id, introduced_in_taxonomy_version_id, created_at) VALUES (71, 'engagement_type', 'contractor_agency', 'Contract via agency', 'seed', NULL, 3, '2026-10-20 11:47:07.93018+00');


ALTER TABLE public.taxonomy_term ENABLE TRIGGER ALL;

--
-- Data for Name: trend_weekly; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.trend_weekly DISABLE TRIGGER ALL;



ALTER TABLE public.trend_weekly ENABLE TRIGGER ALL;

--
-- Data for Name: worker_heartbeat; Type: TABLE DATA; Schema: public; Owner: jobs_radar_test
--

ALTER TABLE public.worker_heartbeat DISABLE TRIGGER ALL;



ALTER TABLE public.worker_heartbeat ENABLE TRIGGER ALL;

--
-- Name: application_draft_application_draft_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.application_draft_application_draft_id_seq', 1, false);


--
-- Name: audit_event_audit_event_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.audit_event_audit_event_id_seq', 1, true);


--
-- Name: career_profile_career_profile_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.career_profile_career_profile_id_seq', 1, true);


--
-- Name: collection_run_collection_run_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.collection_run_collection_run_id_seq', 1, true);


--
-- Name: company_alias_company_alias_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.company_alias_company_alias_id_seq', 1, false);


--
-- Name: company_company_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.company_company_id_seq', 1, true);


--
-- Name: company_enrichment_candidate_company_enrichment_candidate_i_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.company_enrichment_candidate_company_enrichment_candidate_i_seq', 1, false);


--
-- Name: company_fact_company_fact_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.company_fact_company_fact_id_seq', 1, false);


--
-- Name: company_follow_company_follow_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.company_follow_company_follow_id_seq', 1, false);


--
-- Name: company_ignore_company_ignore_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.company_ignore_company_ignore_id_seq', 1, false);


--
-- Name: direction_judgement_direction_judgement_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.direction_judgement_direction_judgement_id_seq', 1, false);


--
-- Name: document_document_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.document_document_id_seq', 1, false);


--
-- Name: evidence_evidence_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.evidence_evidence_id_seq', 1, true);


--
-- Name: inbox_event_inbox_event_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.inbox_event_inbox_event_id_seq', 1, true);


--
-- Name: integration_credential_integration_credential_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.integration_credential_integration_credential_id_seq', 1, false);


--
-- Name: intent_revision_intent_revision_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.intent_revision_intent_revision_id_seq', 1, true);


--
-- Name: job_change_event_job_change_event_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.job_change_event_job_change_event_id_seq', 1, true);


--
-- Name: job_extraction_job_extraction_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.job_extraction_job_extraction_id_seq', 1, true);


--
-- Name: job_inbox_item_job_inbox_item_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.job_inbox_item_job_inbox_item_id_seq', 1, true);


--
-- Name: job_opportunity_job_opportunity_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.job_opportunity_job_opportunity_id_seq', 1, true);


--
-- Name: job_opportunity_link_job_opportunity_link_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.job_opportunity_link_job_opportunity_link_id_seq', 1, true);


--
-- Name: job_posting_job_posting_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.job_posting_job_posting_id_seq', 1, true);


--
-- Name: job_snapshot_job_snapshot_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.job_snapshot_job_snapshot_id_seq', 1, true);


--
-- Name: job_summary_job_summary_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.job_summary_job_summary_id_seq', 1, false);


--
-- Name: match_evaluation_match_evaluation_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.match_evaluation_match_evaluation_id_seq', 1, true);


--
-- Name: owner_owner_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.owner_owner_id_seq', 1, true);


--
-- Name: page_reader_configuration_page_reader_configuration_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.page_reader_configuration_page_reader_configuration_id_seq', 1, false);


--
-- Name: privacy_setting_privacy_setting_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.privacy_setting_privacy_setting_id_seq', 1, false);


--
-- Name: profile_proposal_profile_proposal_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.profile_proposal_profile_proposal_id_seq', 1, false);


--
-- Name: profile_revision_profile_revision_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.profile_revision_profile_revision_id_seq', 1, true);


--
-- Name: proposal_item_proposal_item_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.proposal_item_proposal_item_id_seq', 1, false);


--
-- Name: provider_connection_provider_connection_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.provider_connection_provider_connection_id_seq', 1, false);


--
-- Name: schedule_setting_schedule_setting_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.schedule_setting_schedule_setting_id_seq', 1, false);


--
-- Name: score_dimension_score_dimension_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.score_dimension_score_dimension_id_seq', 1, true);


--
-- Name: search_intent_search_intent_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.search_intent_search_intent_id_seq', 1, true);


--
-- Name: skill_alias_skill_alias_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.skill_alias_skill_alias_id_seq', 1, false);


--
-- Name: skill_candidate_skill_candidate_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.skill_candidate_skill_candidate_id_seq', 1, false);


--
-- Name: skill_relation_skill_relation_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.skill_relation_skill_relation_id_seq', 1, false);


--
-- Name: skill_skill_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.skill_skill_id_seq', 1, false);


--
-- Name: source_configuration_source_configuration_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.source_configuration_source_configuration_id_seq', 1, true);


--
-- Name: source_run_result_source_run_result_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.source_run_result_source_run_result_id_seq', 1, true);


--
-- Name: taxonomy_term_taxonomy_term_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.taxonomy_term_taxonomy_term_id_seq', 71, true);


--
-- Name: taxonomy_version_taxonomy_version_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.taxonomy_version_taxonomy_version_id_seq', 3, true);


--
-- Name: trend_weekly_trend_weekly_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.trend_weekly_trend_weekly_id_seq', 1, false);


--
-- Name: worker_heartbeat_worker_heartbeat_id_seq; Type: SEQUENCE SET; Schema: public; Owner: jobs_radar_test
--

SELECT pg_catalog.setval('public.worker_heartbeat_worker_heartbeat_id_seq', 1, false);


--
-- PostgreSQL database dump complete
--


