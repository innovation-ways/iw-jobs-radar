# Sources and providers runbook

## Job sources (Sources screen)

- A source is one company's job board. Add it by token; the board is validated against the public
  API before it is saved. The first type is the Greenhouse Job Board API.
- A run never blocks on one failing board. The table shows the last outcome and the reason
  (`not_found`, `rate_limited`, `timeout`, `server_error`, `invalid_payload`, `blocked_url`).
- A posting closes only after two consecutive successful runs without it; a failed run never
  closes anything.
- Rate limits are per source (requests per minute); lower them if a board answers `rate_limited`.
- If a board stops working: check the token on the company's careers page, run it alone with its
  Run button, read the reason, then disable it until fixed. Other boards are unaffected.

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

`make smoke` checks a real Greenhouse board, Wikidata and a local model; set
`JOBS_RADAR_SMOKE_API_URL` and `JOBS_RADAR_SMOKE_API_KEY` to include a cloud provider. They send
no personal data and are never part of the default test run.
