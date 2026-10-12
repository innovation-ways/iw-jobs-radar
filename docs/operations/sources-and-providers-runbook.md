# Sources and providers runbook

## Job sources (Sources screen)

- A source is one company's job board. Add it by identifier and choose the board type; the board is
  validated against the public API before it is saved. Types: Greenhouse (the token of
  `boards.greenhouse.io/<token>`), Lever (`jobs.lever.co/<identifier>`), Ashby
  (`jobs.ashbyhq.com/<identifier>`), SmartRecruiters (`jobs.smartrecruiters.com/<identifier>`) and
  Eightfold careers sites (ADR-055), added by the address of the careers site, for example
  `jobs.amdocs.com`.
- Lever and Ashby do not publish the company name: a name is guessed from the identifier, and you
  can type the real one when adding (it cannot be edited afterwards).
- SmartRecruiters lists postings without text, so it reads the details of technical postings only,
  at most 200 per run; a company with more is `partial` (it never closes postings) and a company
  with no open postings is refused as not found. Its default pace is 30 requests a minute. With
  filters on, only your countries are listed, so the 200 details go to postings that can pass.
- Eightfold (Amdocs, Vodafone, Ericsson, ...) uses the careers site's own public JSON API, which is
  not documented and may change; it lists ten postings a page, newest first, and reads the details
  of at most 200 postings per run (`partial` beyond, which never closes postings). Without filters it
  reads every listed posting up to that limit; with filters only the postings whose title fits a
  chosen area, and only your countries plus the site's remote postings are listed (Eightfold's remote work is limited to the posting's own country). Its default pace is 30 requests a minute.
- **Filters on a company board** are off by default (every posting is kept). For a large company
  open **Filters** on its row and tick *Keep only postings that match my areas and location*: only
  postings in the chosen technology areas, remote work open to your countries, or on-site work
  inside your radius are stored (the rest are counted as dropped). Places that cannot be read are
  kept. A new filter applies from the next run and does not close postings already stored.
- A run never blocks on one failing board. The table shows the last outcome and the reason
  (`not_found`, `rate_limited`, `timeout`, `server_error`, `invalid_payload`, `blocked_url`).
- A posting closes only after two consecutive successful runs without it; a failed run never
  closes anything.
- Rate limits are per source (requests per minute); lower them if a board answers `rate_limited`.
- If a board stops working: check the token on the company's careers page, run it alone with its
  Run button, read the reason, then disable it until fixed. Other boards are unaffected.

## Job boards (Sources screen)

A job board publishes the jobs of many companies. Add one with **Add a job board**: pick it from
the catalogue, adjust the filters, press **Check & preview** (it contacts the board and shows how
many postings would be kept), then **Add**. Nothing is saved before the check succeeds.

| Board | Covers | Key | Notes |
|---|---|---|---|
| Arbeitnow | Europe, remote and relocation | none | updated hourly; places are read from the text |
| Jobicy | remote, Europe filter | none | asks for at most one poll an hour |
| Himalayas | remote, eligible countries per job | none | refreshes its data every 24 hours |
| ITJobs.pt | Portugal, IT | free key by email (itjobs.pt/api) | checked against the live service with a real key on 2026-10-12 (collection and offer links work); `workModel` codes are observed, not documented |

- **Where a board looks comes from your profile.** The countries are never typed into a source.
  They are the country of your base location plus the regions where an enabled search intent
  accepts remote work. The Sources screen shows them read-only; change them in **Profile & intent**.
  With no enabled intent a board fails with `configuration` ("Set your base location ... in
  Profile & intent first") before any request.
- **Filters** (technology areas, search terms, posted within N days, most postings per run) decide
  what is stored. Postings left out are counted (`dropped`) and never stored, which keeps the number
  of local-model extractions small. A new filter applies from the next run and does not close
  postings already kept.
- **A board's key** is stored encrypted (it needs `JOBS_RADAR_CREDENTIAL_KEY`), is sent only to
  that board, and is never shown again. **Replace key** checks the new key first; **Remove key**
  also switches the board off. A refused key is reported as `authentication`.
- **Limits.** Each board declares a minimum time between runs. Run now before then is refused and
  the screen says when it is allowed (`too_soon`); a run of all sources skips the board
  (`skipped`, not a failure). A run that stops at "most postings per run" is `partial`: it stores
  what it found, but never closes postings, because it saw only part of the board.
- **Terms.** Every board asks for a link back; each posting shows the board it came from and links
  to it. The terms were read on 2026-10-09 and not reviewed legally (ODR-007). A board whose terms
  forbid storing postings, or that needs HTML scraping, is deliberately not in the catalogue.
- A job board posting and the same job on the company's own board are linked as one opportunity;
  the company board listing is the primary one.
- **Closing takes two complete runs.** A posting that a new filter (or the board) no longer lists
  is closed after two complete runs; a job board allows a run only after its minimum interval (6
  hours for Himalayas and ITJobs.pt), so postings left over from older filters disappear after
  about 12 hours. Turn on the daily schedule to let the worker do it.
- Disable a misbehaving board instead of deleting it; its collected postings stay in the inbox.

## Daily schedule

Set the time and time zone in **Sources**; it is off until you turn it on. The worker creates one
run per day, catches up a missed run for up to 12 hours and fails (then retries once) a run that
a stopped worker left unfinished. `./jobs-radar.sh --logs worker` shows what it did.

## AI providers (AI & privacy screen)

- Default is **No AI**: jobs are collected and shown as "not evaluated"; CV import is unavailable.
- **Job analysis** uses a local model only (Ollama). Install a model, set
  `JOBS_RADAR_ALLOW_LOCAL_PROVIDERS=true` and `JOBS_RADAR_OLLAMA_URL`, add a connection, test it
  and choose it for job analysis. `qwen3:8b` takes about 10 seconds per job.
- **CV import** can use the local model or a remote OpenAI-compatible provider. A remote provider
  needs its key (saved write-only) and your confirmation for each CV; contact details are removed
  before sending unless you turned that off. A failure never falls back to another provider.
- Models that return unusable answers: the proposal list says so and nothing is saved; try again
  or choose another model.

## Company lookups

Wikidata, Wikipedia, GLEIF and GitHub are read without keys. An entity is used automatically only
when its website domain equals a domain already known for the company; otherwise confirm or
reject the candidate in the dossier. A GitHub token (AI & privacy) only raises GitHub's request
limit.

## Opt-in smoke tests

`make smoke` checks a real Greenhouse board, the Arbeitnow, Jobicy and Himalayas job boards,
Wikidata and a local model; set
`JOBS_RADAR_SMOKE_API_URL` and `JOBS_RADAR_SMOKE_API_KEY` to include a cloud provider. They send
no personal data and are never part of the default test run.

## Career directions (ADR-057)

- Write what you are looking for in the Profile screen (**Career directions**, up to 5 texts in English, "+" to add). Saving creates a normal profile revision. They never leave the machine: only the local model reads them.
- In the search intent, give the optional **Career direction** dimension a weight (it is 0 by default). The best fit among your enabled directions counts.
- The worker judges only jobs first seen after you saved the first direction. An older job is judged from its detail ("Assess this job"). Nothing is judged in bulk.
- Try it on a sample before raising the weight: `cd backend && uv run python -m jobs_radar.tools.direction_sample --ids 12,40,77 --what-if career_direction=15,role_responsibilities=10 [--model qwen3.6:27b]` judges those jobs and prints the score before, now and with the what-if weights (never stored).
- In **AI & privacy**, a local connection has an optional **Model for career directions**: a larger local model can judge directions while the smaller one keeps reading jobs. Empty = the job model. On the 30-job sample of 2026-10-10 `qwen3:8b` over-rated unrelated jobs and left an AI-engineer posting unjudged; `qwen3.6:27b` took about 2 s per judgement and separated the cases cleanly.
