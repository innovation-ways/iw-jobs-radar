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
- Notifications outside the app, other source types (Lever, Ashby), a larger place gazetteer and
  skill taxonomies such as ESCO are not included; see `ai-dev/docs/13` section 12.
- Licence: the repository carries the GPL-3.0 text it was created with; the project is for the
  owner's personal use and is not published (ODR-007). Decide the licence again before any release.
