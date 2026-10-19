# MCP server: let an AI agent use Jobs Radar

Jobs Radar can be read, and optionally triaged, by an AI agent through the
[Model Context Protocol](https://modelcontextprotocol.io) (MCP): Claude Code, a desktop assistant,
or a chat client that runs a local model. You ask in plain language ("which new offers fit best and
why?"), the agent calls Jobs Radar's tools and answers from your data. Decision: ADR-078; design
and tests: [`docs/design/mcp-server.md`](../design/mcp-server.md).

**It is off by default.** Nothing runs, and no agent can reach anything, until you turn it on.

## Read this first: privacy and trust

- **There is no authentication**, like the rest of Jobs Radar (ADR-009). The MCP server is started
  by your agent's client on your machine (over stdio, no network port) and talks to your own API.
- **What a tool returns is sent to the model behind the agent.** The profile and the search intents
  are returned in full (employers, education, pay expectations, free-text notes), together with the
  jobs, scores, your triage decisions and company data. With a **cloud agent** (for example Claude)
  all of that leaves your machine and is handled under that provider's terms. With a **local
  agent** (a model running on your computer behind an MCP-capable client) it does not. Choose the
  client accordingly, and leave the server off when you are not using it.
  This is different from Jobs Radar's own AI: job analysis is still local only (ADR-046); what you
  show your own agent is your choice.
- **Job and company text is written by third parties** and could try to give your agent
  instructions (prompt injection). The server returns such text only inside fields named
  `untrusted_*`, wrapped in `<untrusted-source-text>` markers and truncated, and tells the agent to
  treat it as data. Job titles and company names are short and are not wrapped. Keep your client's
  confirmation prompts on, especially if you enable the write tools.
- **Never exposed through MCP:** AI provider settings and credentials, source credentials, CV
  upload and document text, deletion, edits to the profile, intents, sources or scoring weights.

## Turn it on

In the untracked `.env` (`./jobs-radar.sh --init-env` creates it; the variables are in
`.env.example`):

```bash
JOBS_RADAR_MCP_ENABLED=true         # master switch; only the word "true" turns it on
JOBS_RADAR_MCP_ALLOW_WRITES=false   # optional second switch, see "Write tools"
```

Then `./jobs-radar.sh --mcp` (or `make mcp-config`) shows the state and the exact command to
connect, with the path of your checkout. The API must be running (`./jobs-radar.sh --quick-start`).
If the switch is off, the server prints one line to stderr and exits with status 2: the client
shows it as a server that failed to start.

To turn it off again, set `JOBS_RADAR_MCP_ENABLED=false` (or remove the line).

## Connect an agent

The server is a command that speaks MCP over stdio. It needs `uv` (already a prerequisite).

**Claude Code** (stored in your own Claude settings, not in this repository):

```bash
claude mcp add jobs-radar --scope local -- \
  uv run --directory /path/to/iw-jobs-radar/backend --extra mcp python -m jobs_radar.mcp_server
```

`./jobs-radar.sh --mcp` prints this line with your real path. Check with `claude mcp list`.

**Any other client that supports stdio MCP servers**, including clients that run a local model:
register a server named `jobs-radar` with the command `uv` and the arguments
`run --directory /path/to/iw-jobs-radar/backend --extra mcp python -m jobs_radar.mcp_server`. Most
clients take a JSON entry like this one:

```json
{"mcpServers": {"jobs-radar": {"command": "uv",
  "args": ["run", "--directory", "/path/to/iw-jobs-radar/backend", "--extra", "mcp",
           "python", "-m", "jobs_radar.mcp_server"]}}}
```

Do not commit client configuration to the repository (`.mcp.json` is git-ignored).

**Another API address.** By default the server calls `http://127.0.0.1:<JOBS_RADAR_API_PORT>`. To
point it elsewhere (for example the demo on port 8101, or an API on the LAN), set
`JOBS_RADAR_MCP_API_URL` in the client's `env` entry for the server, or in `.env`. The process
environment wins over `.env`; the server reads nothing from `.env` except `JOBS_RADAR_MCP_*` and
`JOBS_RADAR_API_PORT`, so your database password and credential key are never loaded by it.

## What you can ask

- "What is waiting for review? Show me the five best fits and say why each one fits."
- "Why did job 123 score 62? Which dimension cost the most points, and what is the evidence?"
- "Which jobs have a gate that fired, and for which hard constraint?"
- "Which skills are growing among the jobs relevant to me over the last 12 weeks?"
- "Which sources failed in the last run, and why?"
- "Tell me about this company: what do we know, and what are they hiring for?"
- "Summarise today's digest."
- With writes on: "Shortlist the two best offers and ignore the ones below 40 with reason 'not my stack'."

## Tools

All read tools are annotated read-only. `limit` values are capped, and long text is truncated, so a
reply never floods the agent.

| Tool | What it returns |
|---|---|
| `get_status` | Is Jobs Radar up, the worker and queues, how many jobs wait for review, the best fit |
| `list_inbox` | The inbox, best fit first; filters for tab, fit, company, source, text, engagement, pay stated, set aside; pages with `next_cursor`. Rows carry `job_inbox_item_id` and `version` |
| `get_job` | One job: key facts, technologies, score per dimension with the quoted evidence and explanation, gates, history, and the description in `untrusted_description` |
| `get_daily_digest` | New high-fit jobs, changed shortlisted jobs, sources that need attention |
| `get_career_profile` | Your profile, in full, as stored |
| `list_search_intents` | Your search intents in full: stances, weights, pay expectations |
| `list_sources` | Every source with its status; only whether a key is saved, never the key |
| `list_collection_runs` | Recent runs and the outcome of each source |
| `list_companies`, `get_company` | Companies with open offers; a dossier with facts, their source and licence, boards and offers |
| `get_trends` | Weekly shares of the relevant jobs for skills, role families, sectors and more |

### Write tools

Present only when **both** `JOBS_RADAR_MCP_ENABLED=true` and `JOBS_RADAR_MCP_ALLOW_WRITES=true`.
With the second switch off the tools do not exist at all.

| Tool | Effect |
|---|---|
| `inbox_action` | Open, mark unread, shortlist, unshortlist, ignore, restore, archive or record an application for one job. Needs the `version` the agent just read; a stale one fails and changes nothing. Every change is logged in the job's history and can be undone |
| `start_collection` | Queue a run of every enabled source, as the Sources button does; the worker runs it |
| `summarise_job` | Ask the local model for the job's AI summary (stored). Needs a configured local model |

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| The client says the server failed to start | The switch is off. Set `JOBS_RADAR_MCP_ENABLED=true` in `.env`; `./jobs-radar.sh --mcp` shows the state |
| Tools answer `api_unreachable` | The API is not running or the address is wrong: `./jobs-radar.sh --quick-start`, check `JOBS_RADAR_MCP_API_URL` |
| `conflict` when shortlisting | The job changed since the agent read it; it must read the job again and retry with the new `version` |
| `get_trends` says to create a search intent | Create one in Profile & intent first; trends cover the jobs relevant to an intent |
| The first start is slow | `uv run` installs the extra on first use; later starts are quick |
| Check the configuration | `make config-check` reports whether the server is on, and warns when writes are allowed |

Logs go to the client's log of the server (stderr). They contain the tool name and errors, never
your job text, profile or tool arguments.
