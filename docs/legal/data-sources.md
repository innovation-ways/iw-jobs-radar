# Data sources: terms and obligations

Jobs Radar reads public job data on the owner's own machine. It does not redistribute that data, but
each source has conditions you must respect. This page records what each source asks for and what
the application does about it. **Review it again when you add a source or before running the
application as a service for other people.** Last reviewed: 2026-10-13.

## Job boards (catalogue, `adapters/sources/catalogue.py`)

| Board | Access | What the terms say | What Jobs Radar does |
|---|---|---|---|
| Arbeitnow | Free public API, no key | The announcement states no terms, rate limits or attribution rule. Contact: `contact at arbeitnow.com` | Polls at most once an hour (6 requests a minute), shows "Jobs from Arbeitnow" and links to the original posting |
| Jobicy | Free, no key | Poll at most once an hour; keep Jobicy as the source and the canonical job URL; do not present listings as your own postings; no spam networks or misleading job databases | Minimum 60 minutes between runs, source attribution and original link kept |
| Himalayas | Free, no key | Visible link back to himalayas.app and a mention that the data comes from Himalayas, wherever the data is displayed; data refreshes every 24 hours; rate limited (429) | Minimum 6 hours between runs, attribution text shown with the data |
| We Work Remotely | Public RSS feeds, no key | The API terms (`weworkremotely.com/api-terms-and-guidelines`) are reported to forbid scraping, copying, saving or storing the data and to require applying through the board's site; the page blocks automated readers, so it was **not read** by the project | Minimum 60 minutes between runs, ten feed requests a run, link back and attribution kept. **Owner decision (ADR-072): used for personal, local use only; do not redistribute the stored postings** |
| Working Nomads | Free public JSON, no key | No usage terms were found on the site or the feed | Minimum 60 minutes between runs, link to the original posting and attribution text kept (ADR-074) |
| Remote OK | Free public API, no key | API notice: link back to the posting on Remote OK with a follow link, name Remote OK as the source, do not use its logo without permission | Minimum 60 minutes between runs, attribution text and original link shown, no logo (ADR-074) |
| ITJobs.pt | Free API key requested by email | The published pages state no usage terms, rate limit or attribution rule (contact `itjobs@itjobs.pt`) | Key is encrypted and write-only; minimum 6 hours between runs. **Confirm the terms with ITJobs.pt when you receive your key** |

The application enforces the minimum interval between runs (`409 too_soon`) and never lets you type
a board URL: only these catalogue entries exist.

## Company boards (one company per source)

| System | Access |
|---|---|
| Greenhouse Job Board API, Lever Postings API, Ashby public job-posting API, SmartRecruiters Posting API | Public, unauthenticated endpoints that companies publish so their vacancies can be shown elsewhere |
| Eightfold careers sites | The site's own JSON API, **not documented** for third parties and subject to change. Use at your own discretion, keep the default pace and prefer the company's terms if they forbid automated access |

## A company's own careers page (ADR-070)

For a company that publishes on no known system, Jobs Radar may read the company's own careers
site: its sitemap and posting pages (structured `JobPosting` data), or the listing page through
selectors you approved. Only pages on the company's own domain are read, `robots.txt` is honoured
(a refusal stops the source and is never worked around), requests are spaced (at most one a second
by default) and bounded in number per run. Page text is used only to extract the postings; nothing
is republished. If a site's terms forbid automated reading, do not follow it with a source: follow
it by hand.

These were checked against each vendor's public documentation during development; re-check them
before relying on a source commercially. Every outbound request identifies the application in the
`User-Agent` header and goes through the SSRF guard with a per-source rate limit.

## Company enrichment (optional)

| Source | Licence | Handling |
|---|---|---|
| Wikidata | CC0 | Facts stored with source, date and licence |
| Wikipedia summaries | CC BY-SA 4.0 | Stored with attribution; share-alike applies if you republish the text |
| GLEIF | CC0 | Stored with source, date and licence |
| GitHub organisation data | GitHub REST API terms | Optional token; stored with source and date |
| GeoNames (offline, via `geonamescache`) | CC BY 4.0 | Credited in the application |

## Your responsibility

- Jobs Radar is for **personal use**. Do not republish collected postings or build a public job
  database from them.
- Respect each site's terms, robots rules and rate limits, and do not raise the rate limits beyond
  what a source allows.
- Job text and the profile you enter stay on your machine. AI analysis of jobs is local-only; CV
  import may use a remote AI provider only after your per-document consent and with contact details
  redacted.
