# iw-jobs-radar

Jobs Radar — a local-first, single-user job-market radar. It collects jobs from permitted public sources,
extracts what matters with an AI model (local by default), scores each job against your profile and
search intent with an explainable deterministic rule set, and keeps a personal inbox and market trends.

## Quick start

```bash
./jobs-radar.sh --quick-start     # needs Docker, uv, Node 22 + pnpm (corepack)
./jobs-radar.sh --health
# open http://127.0.0.1:5180
```

Design and decisions live in `ai-dev/docs/` (start with `00 - Implementation Pack Index.md`);
the build plan is `ai-dev/docs/14 - Implementation Guide.md`. Working rules and commands for
contributors and AI agents are in `CLAUDE.md`.

The application has no authentication in V1: keep it on loopback or a trusted LAN.
