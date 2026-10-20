"""Domain packs: one JSON file per field of work (ADR-080).

A pack lists the role families and sectors of a field, so that someone who is not a software
engineer starts with a vocabulary that fits their search. The files are package data: they travel
inside the backend image and are loaded into the database at start-up
(``jobs_radar.services.packs``). The format is ``jobs_radar.schemas.pack.PackFile``; how to write
one is in ``docs/packs.md``.
"""
