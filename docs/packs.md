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

Keywords for the job-board pre-filter, credentials, and suggested defaults will be added to the
format in later steps of ADR-080; the validator rejects them until then.
