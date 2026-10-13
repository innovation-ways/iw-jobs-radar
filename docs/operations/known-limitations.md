# Known limitations of this version

- No authentication: keep the app on this machine or a trusted network.
- Scanned PDFs are not read (no OCR); save the CV with text or as `.txt`.
- Pay is compared in the same currency only; no currency conversion.
- Locations are resolved offline for cities above about 15,000 inhabitants; smaller places stay
  unresolved.
- A fit score explains the match with your stated profile and intent; it does not predict hiring.
- Small local models can miss details or bend the output format; every extraction keeps its quotes
  and bad answers are discarded field by field.
- Duplicate detection links only same-company listings from different sources.
- Trend history before the first computation is a backfill from today's evaluations.
- Companies whose boards are only on a job-board host cannot be matched automatically to public
  datasets; confirm the candidate in the dossier.
- Job boards read only the first postings of a feed, newest first, up to the per-run limit; a very
  large board (Himalayas) is read country by country, so a first run can take several minutes.
  Technology areas are matched by keywords in titles and tags, so the filter is loose on purpose.
- Arbeitnow and Jobicy do not state who may apply: a posting whose place cannot be read is kept
  and judged later. Jobicy is read through its `europe`, `anywhere` and country slugs only.
- ITJobs.pt (Portugal) was checked with a real key on 2026-10-12: collection succeeds, the offer links
  open, and remote work is read from `workModel` (0 on site, 1 remote, 2 hybrid) or from the words
  "remote" or "remoto". Those codes are an observation, not documented by the service.
- Company board places are free text ("Hybrid - Lisbon / Madrid"): the location filter reads
  what it can and keeps what it cannot, so some out-of-reach postings still reach the inbox.
- A job board posting is not deleted from the list of sources; disable the board instead.
- Company boards of other applicant tracking systems (Workable, Recruitee, Teamtailor) are not
  included; the identifier of a Lever, Ashby or SmartRecruiters board must be found by the owner
  on the company's careers address.
- Notifications outside the app, a larger place gazetteer and
  skill taxonomies such as ESCO are not included.
- Licence: Apache-2.0 (`LICENSE`, `NOTICE`). Terms of the job sources are in `docs/legal/data-sources.md`;
  the project is for personal use and collected postings must not be republished.
