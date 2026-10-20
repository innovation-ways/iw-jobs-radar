# Domain packs

A **pack** is a ready-made list of role families and sectors for one field of work (ADR-080). Jobs
Radar sorts every job into these role families and sectors, and your search intent takes a stance on
each (preferred, acceptable or rejected). A software engineer and an electrician therefore need
different lists, and the packs give each of them a complete starting point.

## Using packs

- Open **Packs** in the sidebar and switch on the fields you search in. You can use several at once.
- A pack that is switched on offers its role families and sectors in **Profile & intent** and to the
  AI that reads job postings. A pack that is off offers nothing.
- Switching a pack off **deletes nothing**. Saved searches that mention its terms keep working, and
  jobs already analysed are not analysed again. Switching a pack on does not re-analyse old jobs
  either; it applies to the jobs collected from then on.
- **Vocabulary** lets you add your own role families and sectors, rename any term, switch a term off
  and merge two terms. Terms you add are always offered, whatever packs are on.
- Prefer to start from scratch? Leave every pack off and add your own terms in Vocabulary.

The packs that ship today are: Software, data and IT; Construction and skilled trades; Installation,
maintenance and repair; Manufacturing and production; Logistics, transport and warehousing;
Healthcare and social care; Retail, sales and customer service; Hospitality, food and tourism;
Office, finance, legal and HR; Education and public services.

## Where they live

One JSON file per pack in `backend/src/jobs_radar/packs/`. They are package data, so they are inside
the backend image that is published on GHCR. When the API starts it loads them into the database
(`JOBS_RADAR_LOAD_PACKS`, on by default). Loading is safe to repeat and safe after an upgrade:

- it only **adds** terms and pack memberships;
- it never rewrites a label, so a term you renamed keeps your name when a newer pack arrives;
- a term that a pack stops listing is **switched off**, never deleted, so history stays valid;
- terms you added yourself are never touched.

A term can belong to several packs (for example `customer_support`). It is offered while at least one
of them is on. A term in no pack (`other`, and the terms you add) is always offered.

## Writing a pack

```json
{
  "schema_version": 1,
  "key": "construction_trades",
  "version": 1,
  "name": "Construction and skilled trades",
  "description": "Electricians, plumbers, carpenters, welders, builders and site roles.",
  "role_families": [
    { "key": "electrician", "label": "Electrician" },
    { "key": "plumber_pipefitter", "label": "Plumber / pipefitter" }
  ],
  "sectors": [{ "key": "construction", "label": "Construction" }]
}
```

Rules, all checked by tests (`backend/tests/unit/schemas/test_pack_schema.py` and
`backend/tests/unit/test_pack_files.py`):

- The file is named after the pack `key`. Keys are lowercase letters, digits and underscores.
- Term keys are stable: once a key is published it is never renamed or reused for something else,
  because saved searches and analysed jobs refer to it. Add a new key instead.
- A key has **one label in every pack**. To reuse a term another pack already has, copy its key and
  label exactly.
- A pack needs at least 10 role families and 5 sectors, so nobody has to add terms to get started.
  English labels only for now.
- Unknown fields are rejected. Do not list `other`: it belongs to no pack.
- Raise `version` when you change a pack.

### Areas and noise: the job-board pre-filter

A pack can also say which postings of a job board belong to its field. `areas` are groups of
keywords ("electrical", "plumbing and heating"); `noise` lists words that rule a posting out
(talent pools, for example). The owner chooses areas in the filters of a board (Sources), and the
areas on offer are those of the packs that are switched on.

```json
"areas": [
  { "key": "electrical", "label": "Electrical",
    "keywords": ["electrician*", "electrical", "wiring", "switchboard*"] }
],
"noise": ["talent pool*", "spontaneous application*", "unpaid*"]
```

Keywords are **plain text, never regular expressions**: letters, digits, spaces and `+ # . & '`.

- A keyword matches whole words, ignoring case. `electrical` does not match `electricals`.
- A trailing `*` lets it match any ending: `electrician*` matches `electrician` and `electricians`.
- Hyphens, underscores and slashes count as spaces: `back-end` equals `back end`.
- A phrase of several words matches those words in a row: `site supervisor*`.
- Text with pattern characters (`(`, `[`, `|`, `\`) is refused when the pack is loaded.
- Two packs that define an area with the same key share it: its keywords are joined.

### Credentials

A pack lists the licences and certifications of its field. They become canonical skills of kind
`credential`, so a posting that asks for "a valid category B licence" and a profile that holds
"Driving licence (category B)" are recognised as the same thing.

```json
"credentials": [
  { "name": "Driving licence (category B)",
    "aliases": ["driving licence b", "category b licence", "b licence"] }
]
```

- The name is what the owner sees; aliases are other ways it is written (matched ignoring case and
  punctuation). An alias that another skill already answers to is not taken over.
- A credential that already exists, for example from an imported CV, is kept as it is and gains the
  pack's aliases. Loading is repeatable.
- A credential written in two packs needs the same name and aliases in both (tests check it).
- A pack needs at least 3 credentials.

In the profile they are listed under "Licences and certifications". A posting can name several; the
qualifications score is the share the owner holds, and an option in the search intent ("Rule out jobs
that require a licence or certification I do not hold") turns a missing required one into a hard gate
(G12, off by default).

### Defaults for a new search

`defaults` says what a first search intent starts with for someone in this field. They are only
suggestions: the setup assistant shows them, and every one can be changed in Profile & intent.

```json
"defaults": {
  "work_arrangements": { "onsite": "preferred", "hybrid": "acceptable", "remote": "rejected" },
  "schedules": { "day": "preferred", "night": "acceptable", "weekends": "acceptable" },
  "travel_levels": { "frequent": "acceptable" },
  "weights": { "qualifications": 12, "schedule_travel": 8, "work_arrangement_location": 20 },
  "reject_missing_credentials": true
}
```

- Stances are `preferred`, `acceptable` or `rejected`; options left out stay acceptable. The options
  are the application's own (`remote`, `hybrid`, `onsite`; `day`, `night`, `rotating_shifts`,
  `weekends`, `on_call`; `none`, `occasional`, `frequent`), not the pack's.
- `weights` are relative weights (0 to 40) of the scoring dimensions; those left out keep the
  usual ones. At least one must be above 0.
- A group where every option is rejected is refused.
- When several packs are on, the suggestions of the **first one switched on** are used (the main
  field); the others add vocabulary only.

An area needs at least 4 keywords and a pack at least 4 areas (tests check it). Areas and noise are
read from the pack files; nothing about them is stored in the database, so a newer pack improves the
filter without a migration.

## First-run setup and analysing jobs again

A new installation (no profile and no pack switched on) opens a short setup: choose the fields of
work, say who you are (headline, place, experience, licences) and create a first search made from the
packs' suggestions. It can be skipped, and nobody who already has a profile sees it.

A pack or an upgrade can add things the analysis asks jobs for (licences, working pattern, travel).
Jobs analysed before that keep their old analysis; nothing is analysed again by itself, because it
costs local-model time and changes little for most people. **Packs → Analyse open jobs again** says
how many open jobs have only an old analysis and about how long the new one takes, and queues them
when you confirm. Jobs you ignored or archived are left alone.
