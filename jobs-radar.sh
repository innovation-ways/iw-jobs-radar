#!/usr/bin/env bash
# =============================================================================
# jobs-radar.sh — Jobs Radar development environment launcher (ADR-018)
#
# Interactive menu:  ./jobs-radar.sh
# CLI:               ./jobs-radar.sh --help
#
# AI agents: use CLI flags. `--health` exits 0 only when everything that is running is healthy.
# Output is plain text (no colour codes) unless it goes to a terminal; FORCE_COLOR=1 forces colour
# and NO_COLOR=1 disables it.
# Services managed by Docker Compose: db, api, worker. The frontend runs outside Docker (ADR-019).
# =============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

ENV_FILE="${JOBS_RADAR_ENV_FILE:-.env}"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
FRONTEND_PID_FILE="$SCRIPT_DIR/.frontend.pid"
FRONTEND_LOG_FILE="$SCRIPT_DIR/logs/frontend.log"
SERVICES=(db api worker)
DEFAULT_WAIT_TIMEOUT=180

# corepack installs the pnpm shim here (see CLAUDE.md); make sure it is found.
export PATH="$HOME/.local/bin:$PATH"

# --- colour and output helpers ------------------------------------------------
if [[ -z "${NO_COLOR:-}" && ( -n "${FORCE_COLOR:-}" || -t 1 ) ]]; then
  RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'; BLUE=$'\033[0;34m'
  CYAN=$'\033[0;36m'; BOLD=$'\033[1m'; DIM=$'\033[2m'; NC=$'\033[0m'
else
  RED=""; GREEN=""; YELLOW=""; BLUE=""; CYAN=""; BOLD=""; DIM=""; NC=""
fi
INTERACTIVE=0   # set to 1 by the menu: then actions pause so their output is not wiped

ok()     { echo -e "  ${GREEN}✓${NC}  $1"; }
err()    { echo -e "  ${RED}✗${NC}  $1" >&2; }
warn()   { echo -e "  ${YELLOW}!${NC}  $1"; }
info()   { echo -e "  ${CYAN}→${NC}  $1"; }
dim()    { echo -e "  ${DIM}$1${NC}"; }
header() { echo -e "\n${BOLD}${BLUE}=== $1 ===${NC}\n"; }

pause() {
  [[ "$INTERACTIVE" == 1 ]] || return 0
  echo ""
  read -r -p "  ${DIM}Press Enter to continue...${NC}" _
}

# --- environment ------------------------------------------------------------
# Loads the env file without overriding variables already set by the caller (explicit env wins).
load_env() {
  [[ -f "$ENV_FILE" ]] || return 0
  local line key value
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ "$line" =~ ^[[:space:]]*(#|$) ]] && continue
    line="$(echo "$line" | sed 's/[[:space:]]*#.*$//')"
    [[ "$line" =~ ^([A-Za-z_][A-Za-z_0-9]*)=(.*)$ ]] || continue
    key="${BASH_REMATCH[1]}"; value="${BASH_REMATCH[2]}"
    [[ -v "$key" ]] || export "$key=$value"
  done < "$ENV_FILE"
}

api_port()      { echo "${JOBS_RADAR_API_PORT:-8100}"; }
frontend_port() { echo "${JOBS_RADAR_FRONTEND_PORT:-5180}"; }
db_port()       { echo "${JOBS_RADAR_DB_PORT:-5440}"; }
bind_addr()     { echo "${JOBS_RADAR_API_BIND:-127.0.0.1}"; }
db_bind()       { echo "${JOBS_RADAR_DB_BIND:-127.0.0.1}"; }

COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.dev.yml)
compose() { docker compose "${COMPOSE_FILES[@]}" "$@"; }

require_env_file() {
  if [[ ! -f "$ENV_FILE" ]]; then
    err "$ENV_FILE not found. Run ./jobs-radar.sh --init-env first."
    exit 1
  fi
}

init_env() {
  local force="${1:-}"
  if [[ -f .env && "$force" != "--force" ]]; then
    warn ".env already exists; not overwriting (use --init-env --force to replace it)."
    return 0
  fi
  [[ -f .env.example ]] || { err ".env.example is missing."; exit 1; }
  local password key
  password="$(head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 24)"
  # A Fernet key is 32 random bytes, url-safe base64 encoded (ADR-033).
  key="$(head -c 32 /dev/urandom | base64 | tr '+/' '-_')"
  sed -e "s|^JOBS_RADAR_DB_PASSWORD=.*|JOBS_RADAR_DB_PASSWORD=${password}|" \
      -e "s|^JOBS_RADAR_CREDENTIAL_KEY=.*|JOBS_RADAR_CREDENTIAL_KEY=${key}|" \
      .env.example > .env
  chmod 600 .env
  ok ".env created with a random database password and credential key."
  warn "Back up JOBS_RADAR_CREDENTIAL_KEY separately: stored credentials cannot be recovered without it."
}

check_dependencies() {
  local missing=0 cmd
  for cmd in docker curl; do
    command -v "$cmd" >/dev/null 2>&1 || { err "$cmd is required but not installed."; missing=1; }
  done
  docker compose version >/dev/null 2>&1 || { err "Docker Compose v2 is required."; missing=1; }
  return $missing
}

check_ports() {
  local name port busy=0 pair
  for pair in "API:$(api_port)" "DB:$(db_port)"; do
    name="${pair%%:*}"; port="${pair##*:}"
    # A port already published by this project's own containers is fine.
    if ss -ltn 2>/dev/null | grep -q ":${port} " && ! compose ps --format '{{.Ports}}' 2>/dev/null | grep -q ":${port}->"; then
      err "$name port $port is already in use. Change it in .env."
      busy=1
    fi
  done
  return $busy
}

# --- addresses -----------------------------------------------------------------
exposed() { [[ "$1" != "127.0.0.1" && "$1" != "localhost" ]]; }

show_urls() {
  load_env
  local fe api db host
  fe="$(frontend_port)"; api="$(api_port)"; db="$(db_port)"; host="$(hostname 2>/dev/null || echo this-machine)"
  header "Addresses"
  echo -e "  ${BOLD}Web app${NC}       ${CYAN}http://127.0.0.1:${fe}${NC}"
  echo -e "  ${BOLD}API docs${NC}      ${CYAN}http://127.0.0.1:${api}/docs${NC}"
  echo -e "  ${BOLD}API health${NC}    ${CYAN}http://127.0.0.1:${api}/healthz${NC}   (readiness: /readyz)"
  echo -e "  ${BOLD}Database${NC}      ${CYAN}postgresql://${JOBS_RADAR_DB_USER:-jobs_radar}@127.0.0.1:${db}/${JOBS_RADAR_DB_NAME:-jobs_radar}${NC}   (password: JOBS_RADAR_DB_PASSWORD in .env)"
  echo ""
  if exposed "$(bind_addr)"; then
    ok "App and API are reachable from the network:"
    echo -e "       ${CYAN}http://${host}:${fe}${NC}   ${CYAN}http://${host}:${api}/docs${NC}"
  else
    dim "App and API: this machine only. Set JOBS_RADAR_API_BIND=0.0.0.0 in .env to reach them from the network."
  fi
  if exposed "$(db_bind)"; then
    ok "Database is reachable from the network: ${host}:${db}  (prefer an SSH tunnel when you can)"
  else
    dim "Database: this machine only. Set JOBS_RADAR_DB_BIND=0.0.0.0 in .env to connect from another computer."
  fi
}

# --- MCP server for AI agents (ADR-078) ----------------------------------------
# True only for the word "true", exactly like the server itself (anything else is off).
mcp_flag() { local v="${!1:-}"; v="${v//[[:space:]]/}"; [[ "${v,,}" == "true" ]]; }

show_mcp() {
  load_env
  header "MCP server (AI agents)"
  if ! mcp_flag JOBS_RADAR_MCP_ENABLED; then
    info "Off: no agent can use it."
    echo -e "  To turn it on, set ${BOLD}JOBS_RADAR_MCP_ENABLED=true${NC} in .env, then run this again."
    dim "Add JOBS_RADAR_MCP_ALLOW_WRITES=true as well to let an agent change your inbox (shortlist, ignore, ...)."
    dim "Read docs/operations/mcp-server.md first: an agent that reads Jobs Radar sees your profile."
    return 0
  fi
  local api="${JOBS_RADAR_MCP_API_URL:-http://127.0.0.1:$(api_port)}"
  ok "On. The server reads the API at ${api}"
  if mcp_flag JOBS_RADAR_MCP_ALLOW_WRITES; then
    warn "Write tools are ON: an agent can change your inbox and queue collections."
  else
    ok "Read-only: the write tools do not exist (JOBS_RADAR_MCP_ALLOW_WRITES is not true)."
  fi
  warn "No authentication. What a tool returns goes to the model behind your agent: your profile too."
  local dir="$SCRIPT_DIR/backend"
  echo ""
  echo -e "  ${BOLD}Claude Code${NC} (stored in your own Claude settings, not in this repository):"
  echo -e "    ${CYAN}claude mcp add jobs-radar --scope local -- uv run --directory ${dir} --extra mcp python -m jobs_radar.mcp_server${NC}"
  echo ""
  echo -e "  ${BOLD}Any other MCP client${NC} (stdio): command and arguments"
  echo -e "    ${CYAN}uv run --directory ${dir} --extra mcp python -m jobs_radar.mcp_server${NC}"
  echo -e "    ${DIM}JSON: {\"mcpServers\": {\"jobs-radar\": {\"command\": \"uv\", \"args\": [\"run\", \"--directory\", \"${dir}\", \"--extra\", \"mcp\", \"python\", \"-m\", \"jobs_radar.mcp_server\"]}}}${NC}"
  echo ""
  dim "The API must be running (./jobs-radar.sh --quick-start). Details: docs/operations/mcp-server.md"
}

# --- docker services ---------------------------------------------------------
valid_service() { local s; for s in "${SERVICES[@]}"; do [[ "$s" == "$1" ]] && return 0; done; return 1; }

service_args() {
  local svc="${1:-}"
  if [[ -n "$svc" ]]; then
    valid_service "$svc" || { err "Unknown service '$svc'. Valid: ${SERVICES[*]}"; exit 1; }
    echo "$svc"
  fi
}

start_services() { require_env_file; load_env; check_dependencies || exit 1; check_ports || exit 1
  local args; args="$(service_args "${1:-}")"; compose up -d --build $args; }
stop_services()    { local args; args="$(service_args "${1:-}")"; compose stop $args; }
restart_services() { local args; args="$(service_args "${1:-}")"; compose restart $args; }
rebuild_services() { require_env_file; load_env; local args; args="$(service_args "${1:-}")"
  compose build --no-cache $args && compose up -d $args; }

# One coloured line per component: ▲ healthy/running, ▼ stopped or unhealthy.
state_badge() {
  case "$1" in
    healthy|running) echo -e "${GREEN}▲ $1${NC}" ;;
    stopped|exited)  echo -e "${RED}▼ $1${NC}" ;;
    *)               echo -e "${YELLOW}▼ $1${NC}" ;;
  esac
}

# Prints "<name> <coloured badge> <extra>" with the badge padded by its visible width.
status_row() {
  local name="$1" state="$2" extra="$3" width=14
  printf "  %-10s " "$name"
  echo -en "$(state_badge "$state")"
  printf "%*s%s\n" $(( width - ${#state} - 2 )) "" "$extra"
}

show_status() {
  load_env
  header "Status"
  printf "  ${BOLD}%-10s %-14s %s${NC}\n" "Component" "State" "Ports"
  local svc state ports pid
  for svc in "${SERVICES[@]}"; do
    state="$(container_health "$svc")"
    ports="$(compose ps --format '{{.Ports}}' "$svc" 2>/dev/null | head -1)"
    status_row "$svc" "$state" "${ports:--}"
  done
  pid="$(frontend_pid)"
  if [[ -n "$pid" ]]; then status_row frontend running "pid $pid, port $(frontend_port)"; else status_row frontend stopped "-"; fi
}

# Compact one-line status used by the menu banner.
status_line() {
  local svc state line=""
  for svc in "${SERVICES[@]}"; do
    state="$(container_health "$svc")"
    if [[ "$state" == "healthy" || "$state" == "running" ]]; then line+="${GREEN}▲ ${svc}${NC}  "; else line+="${RED}▼ ${svc}${NC}  "; fi
  done
  if [[ -n "$(frontend_pid)" ]]; then line+="${GREEN}▲ frontend${NC}"; else line+="${RED}▼ frontend${NC}"; fi
  echo -e "$line"
}

show_logs() {
  local svc="${1:-}" lines="${2:-100}" follow="${3:-}"
  if [[ "$svc" == "frontend" ]]; then
    [[ -f "$FRONTEND_LOG_FILE" ]] && tail -n "$lines" ${follow:+-f} "$FRONTEND_LOG_FILE" || warn "No frontend log yet."
    return
  fi
  local args; args="$(service_args "$svc")"
  compose logs --tail "$lines" ${follow:+-f} $args
}

db_migrate() { require_env_file; load_env; compose exec -T api alembic upgrade head; }

db_shell() {
  require_env_file; load_env
  info "Opening psql as ${JOBS_RADAR_DB_USER:-jobs_radar} (type \\q to leave)"
  compose exec db psql -U "${JOBS_RADAR_DB_USER:-jobs_radar}" -d "${JOBS_RADAR_DB_NAME:-jobs_radar}"
}

# --- health ------------------------------------------------------------------
container_health() {   # prints healthy | unhealthy | running | stopped
  local cid status
  cid="$(compose ps -q "$1" 2>/dev/null)"
  [[ -n "$cid" ]] || { echo stopped; return; }
  status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid" 2>/dev/null)"
  echo "${status:-stopped}"
}

http_ok() { curl -fsS -m 5 -o /dev/null "$1" 2>/dev/null; }

health_deep() {
  load_env
  local failed=0 svc state
  header "Services"
  for svc in "${SERVICES[@]}"; do
    state="$(container_health "$svc")"
    if [[ "$state" == "healthy" || "$state" == "running" ]]; then ok "$svc: $state"; else err "$svc: $state"; failed=1; fi
  done
  header "HTTP"
  local base="http://127.0.0.1:$(api_port)"
  if http_ok "$base/healthz"; then ok "api /healthz"; else err "api /healthz unreachable at $base"; failed=1; fi
  local ready; ready="$(curl -sS -m 5 "$base/readyz" 2>/dev/null || true)"
  if echo "$ready" | grep -q '"status":"ready"'; then ok "api /readyz ready"; else err "api /readyz: ${ready:-no response}"; failed=1; fi
  header "Frontend"
  if [[ -n "$(frontend_pid)" ]]; then
    if http_ok "http://127.0.0.1:$(frontend_port)/"; then ok "frontend responding on port $(frontend_port)"; else err "frontend not responding"; failed=1; fi
  else
    info "frontend not started (not required for this check)"
  fi
  return $failed
}

wait_healthy() {
  local timeout="${1:-$DEFAULT_WAIT_TIMEOUT}" start now
  start="$(date +%s)"
  info "Waiting up to ${timeout}s for the stack to become healthy..."
  while true; do
    if health_deep >/dev/null 2>&1; then ok "Stack is healthy."; return 0; fi
    now="$(date +%s)"
    if (( now - start >= timeout )); then err "Timed out after ${timeout}s."; health_deep || true; return 1; fi
    sleep 3
  done
}

# --- frontend (runs outside Docker) -------------------------------------------
frontend_pid() {
  [[ -f "$FRONTEND_PID_FILE" ]] || return 0
  local pid; pid="$(cat "$FRONTEND_PID_FILE")"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then echo "$pid"; else rm -f "$FRONTEND_PID_FILE"; fi
}

frontend_start() {
  load_env
  [[ -d "$FRONTEND_DIR" && -f "$FRONTEND_DIR/package.json" ]] || { warn "frontend/ is not set up yet."; return 0; }
  command -v pnpm >/dev/null 2>&1 || { err "pnpm not found. Run: corepack enable --install-directory ~/.local/bin pnpm"; return 1; }
  if [[ -n "$(frontend_pid)" ]]; then ok "frontend already running."; return 0; fi
  [[ -d "$FRONTEND_DIR/node_modules" ]] || (cd "$FRONTEND_DIR" && pnpm install --frozen-lockfile) || return 1
  mkdir -p "$(dirname "$FRONTEND_LOG_FILE")"
  # The whole group is redirected so this script never holds a caller's pipe open, and setsid
  # makes the dev server a session leader so the entire process tree can be stopped (see
  # frontend_stop). `exec` keeps the recorded PID equal to the server process.
  (cd "$FRONTEND_DIR" && JOBS_RADAR_API_PORT="$(api_port)" exec setsid pnpm dev \
      --host "$(bind_addr)" --port "$(frontend_port)" --strictPort) \
      >"$FRONTEND_LOG_FILE" 2>&1 </dev/null &
  echo $! >"$FRONTEND_PID_FILE"
  sleep 1
  local i
  for i in $(seq 1 30); do
    http_ok "http://127.0.0.1:$(frontend_port)/" && { ok "frontend running on port $(frontend_port)"; return 0; }
    sleep 1
  done
  err "frontend did not start; see $FRONTEND_LOG_FILE"; return 1
}

frontend_stop() {
  local pid; pid="$(frontend_pid)"
  if [[ -z "$pid" ]]; then info "frontend not running."; return 0; fi
  # Signal the whole process group (pnpm, its shell and vite), then make sure it is gone.
  kill -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null
  local i
  for i in 1 2 3 4 5 6 7 8 9 10; do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
  kill -0 "$pid" 2>/dev/null && kill -9 -- "-$pid" 2>/dev/null
  rm -f "$FRONTEND_PID_FILE"; ok "frontend stopped."
}

frontend_clean() {
  frontend_stop
  rm -rf "$FRONTEND_DIR/node_modules/.vite" "$FRONTEND_DIR/.vite"
  [[ -d "$FRONTEND_DIR" ]] && (cd "$FRONTEND_DIR" && pnpm install --frozen-lockfile)
  frontend_start
}

# --- demo (fictional data, own database and ports; the real data is never touched) ---------
# One command starts everything the demo needs: PostgreSQL (Docker), the demo database, an idle
# worker (heartbeat only: the real worker must never run against the demo database, it would try
# to collect the invented boards), the API on 8101 and the UI on 5181. Processes run detached with
# their own session so --demo-stop can stop the whole tree.
DEMO_DIR="$SCRIPT_DIR/.demo"
DEMO_ENV=(JOBS_RADAR_DB_NAME=jobs_radar_demo JOBS_RADAR_API_PORT=8101 JOBS_RADAR_FRONTEND_PORT=5181)
DEMO_PROCESSES=(worker api frontend)

# demo_spawn <name> <directory> <command...>: start one detached demo process and record its PID.
demo_spawn() {
  local name="$1" dir="$2"; shift 2
  mkdir -p "$DEMO_DIR" "$SCRIPT_DIR/logs"
  (cd "$dir" && exec env "${DEMO_ENV[@]}" setsid "$@") \
      >"$SCRIPT_DIR/logs/demo-$name.log" 2>&1 </dev/null &
  echo $! >"$DEMO_DIR/$name.pid"
}

demo_stop() {
  local name pid i stopped=0
  for name in "${DEMO_PROCESSES[@]}"; do
    [[ -f "$DEMO_DIR/$name.pid" ]] || continue
    pid="$(cat "$DEMO_DIR/$name.pid")"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null
      for i in 1 2 3 4 5 6 7 8 9 10; do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
      kill -0 "$pid" 2>/dev/null && kill -9 -- "-$pid" 2>/dev/null
      stopped=1
    fi
    rm -f "$DEMO_DIR/$name.pid"
  done
  if (( stopped )); then ok "demo stopped (PostgreSQL keeps running; --quick-stop stops it)."; else info "demo not running."; fi
}

demo_start() {
  init_env; load_env
  check_dependencies || return 1
  command -v uv >/dev/null 2>&1 || { err "uv is required (https://docs.astral.sh/uv/)."; return 1; }
  command -v pnpm >/dev/null 2>&1 || { err "pnpm not found. Run: corepack enable --install-directory ~/.local/bin pnpm"; return 1; }
  demo_stop >/dev/null
  info "starting PostgreSQL ..."
  compose up -d --wait db || { err "PostgreSQL did not become healthy."; return 1; }
  info "building the demo database (jobs_radar_demo is dropped and recreated) ..."
  (cd "$SCRIPT_DIR/backend" && env "${DEMO_ENV[@]}" uv run python -m jobs_radar.tools.demo_seed --reset) \
    || { err "demo seed failed."; return 1; }
  [[ -d "$FRONTEND_DIR/node_modules" ]] || (cd "$FRONTEND_DIR" && pnpm install --frozen-lockfile) || return 1
  demo_spawn worker "$SCRIPT_DIR/backend" uv run python -m jobs_radar.demo.idle_worker
  demo_spawn api "$SCRIPT_DIR/backend" env \
    'JOBS_RADAR_CORS_ORIGINS=["http://127.0.0.1:5181","http://localhost:5181"]' \
    uv run uvicorn jobs_radar.api.app:create_app --factory --host 127.0.0.1 --port 8101
  demo_spawn frontend "$FRONTEND_DIR" pnpm dev --host 127.0.0.1 --port 5181 --strictPort
  local i
  for i in $(seq 1 60); do
    http_ok "http://127.0.0.1:8101/healthz" && http_ok "http://127.0.0.1:5181/" && {
      ok "demo running: ${BOLD}http://localhost:5181${NC}  (invented persona, companies and postings)"
      dim "Stop it with: ./jobs-radar.sh --demo-stop      Logs: logs/demo-*.log"
      return 0
    }
    sleep 1
  done
  err "the demo did not come up; see logs/demo-*.log"; return 1
}

# --- tests and quality (thin wrappers around `make`, see `make help`) ----------
run_make() { header "make $*"; make "$@"; local rc=$?; echo ""; if (( rc == 0 )); then ok "make $* passed"; else err "make $* failed (exit $rc)"; fi; return $rc; }

run_tests() {
  case "${1:-}" in
    unit)        run_make test-unit ;;
    integration) run_make test-integration ;;
    backend)     run_make test ;;
    frontend)    run_make test-frontend ;;
    e2e)         run_make test-e2e ;;
    quality)     run_make quality && run_make quality-frontend ;;
    all)         run_make check ;;
    "")          menu_tests ;;
    *) err "Unknown test scope '$1'. Valid: unit, integration, backend, frontend, e2e, quality, all"; exit 1 ;;
  esac
}

# --- compound actions ----------------------------------------------------------
quick_start() { init_env; start_services; wait_healthy "${1:-$DEFAULT_WAIT_TIMEOUT}" && frontend_start; }
quick_stop()  { frontend_stop; compose stop; }

confirm() {
  local prompt="${1:-Are you sure?}" answer
  read -r -p "  ${YELLOW}${prompt} [y/N]${NC} " answer
  [[ "$answer" =~ ^[yY]([eE][sS])?$ ]]
}

nuclear_reset() {
  warn "This removes ALL containers AND the database volume for this project. Data will be lost."
  if [[ "${1:-}" != "--yes" ]]; then
    read -r -p "  Type 'reset' to continue: " answer
    [[ "$answer" == "reset" ]] || { info "Cancelled."; return 1; }
  fi
  frontend_stop; compose down -v --remove-orphans; ok "Environment reset."
}

# --- usage ----------------------------------------------------------------------
usage() {
  echo -e "${BOLD}${BLUE}Jobs Radar launcher${NC}"
  echo -e "${DIM}Usage: ./jobs-radar.sh [option]      (no option: interactive menu)${NC}"
  local title="${BOLD}${YELLOW}" c="${GREEN}" n="${NC}"
  echo -e "\n${title}Setup${n}"
  echo -e "  ${c}--init-env [--force]${n}      Create .env with a random DB password and credential key"
  echo -e "\n${title}Whole stack${n}"
  echo -e "  ${c}--quick-start${n}             Init env if needed, start db/api/worker, wait healthy, start frontend"
  echo -e "  ${c}--quick-stop${n}              Stop frontend and containers"
  echo -e "  ${c}--status${n}                  What is running (table)"
  echo -e "  ${c}--health${n}                  Deep check; exit 0 only if everything running is healthy"
  echo -e "  ${c}--wait-healthy [--timeout N]${n}"
  echo -e "  ${c}--urls${n}                    Addresses of the app, API docs and database"
  echo -e "\n${title}Services${n} (db | api | worker; omit the name to apply to all)"
  echo -e "  ${c}--start [svc]  --stop [svc]  --restart [svc]  --rebuild [svc]${n}"
  echo -e "  ${c}--logs <svc|frontend> [--lines N] [--follow]${n}"
  echo -e "\n${title}Database${n}"
  echo -e "  ${c}--db-migrate${n}              Run Alembic migrations (api container)"
  echo -e "  ${c}--psql${n}                    Open a psql shell on the database"
  echo -e "  ${c}--backup${n}  ${c}--restore-drill${n}   Back up the database + key into backups/; prove the latest dump"
  echo -e "\n${title}Frontend${n} (runs outside Docker)"
  echo -e "  ${c}--frontend-start${n}  ${c}--frontend-stop${n}  ${c}--frontend-clean${n}"
  echo -e "\n${title}Tests and quality${n} (same as the make targets; see 'make help')"
  echo -e "  ${c}--tests [unit|integration|backend|frontend|e2e|quality|all]${n}   No scope: pick from a menu"
  echo -e "\n${title}Demo${n} (invented data, own database and ports 8101/5181; no network, no AI needed)"
  echo -e "  ${c}--demo${n}                    Start PostgreSQL, build the demo database, start worker/API/UI"
  echo -e "  ${c}--demo-stop${n}               Stop the demo processes"
  echo -e "\n${title}AI agents${n}"
  echo -e "  ${c}--mcp${n}                     MCP server: is it on, and how to connect Claude Code or another agent"
  echo -e "\n${title}Danger${n}"
  echo -e "  ${c}--nuclear-reset [--yes]${n}   Remove containers and the database volume"
  echo -e "  ${c}--help${n}"
}

# --- interactive menus ------------------------------------------------------------
pick_service() {   # echoes the chosen service name, returns 1 on cancel
  local prompt="${1:-Which service?}" choice
  echo -e "\n  ${BOLD}${prompt}${NC}" >&2
  echo -e "    ${CYAN}1)${NC} db   ${CYAN}2)${NC} api   ${CYAN}3)${NC} worker   ${CYAN}4)${NC} frontend   ${CYAN}0)${NC} cancel" >&2
  read -r -p "  Choice: " choice
  case "$choice" in 1) echo db ;; 2) echo api ;; 3) echo worker ;; 4) echo frontend ;; *) return 1 ;; esac
}

menu_stack() {
  while true; do
    header "Start and stop"
    echo -e "  ${CYAN}1)${NC} Quick start (everything, wait until healthy)"
    echo -e "  ${CYAN}2)${NC} Quick stop"
    echo -e "  ${CYAN}3)${NC} Restart everything"
    echo -e "  ${CYAN}4)${NC} Start one service    ${CYAN}5)${NC} Stop one service"
    echo -e "  ${CYAN}6)${NC} Restart one service  ${CYAN}7)${NC} Rebuild one service (no cache)"
    echo -e "  ${CYAN}0)${NC} Back"
    read -r -p "  Choice: " choice
    local svc
    case "$choice" in
      1) quick_start; pause ;;
      2) quick_stop; pause ;;
      3) quick_stop; quick_start; pause ;;
      4) svc="$(pick_service 'Start which?')" && { [[ "$svc" == frontend ]] && frontend_start || start_services "$svc"; }; pause ;;
      5) svc="$(pick_service 'Stop which?')" && { [[ "$svc" == frontend ]] && frontend_stop || stop_services "$svc"; }; pause ;;
      6) svc="$(pick_service 'Restart which?')" && { [[ "$svc" == frontend ]] && { frontend_stop; frontend_start; } || restart_services "$svc"; }; pause ;;
      7) svc="$(pick_service 'Rebuild which?')" && { [[ "$svc" == frontend ]] && frontend_clean || rebuild_services "$svc"; }; pause ;;
      0|b|B) return ;;
      *) warn "Invalid choice" ;;
    esac
  done
}

menu_health() {
  while true; do
    header "Health and status"
    echo -e "  ${CYAN}1)${NC} Status table   ${CYAN}2)${NC} Deep health check   ${CYAN}3)${NC} Addresses   ${CYAN}0)${NC} Back"
    read -r -p "  Choice: " choice
    case "$choice" in
      1) show_status; pause ;; 2) health_deep; pause ;; 3) show_urls; pause ;; 0|b|B) return ;;
      *) warn "Invalid choice" ;;
    esac
  done
}

menu_frontend() {
  while true; do
    header "Frontend (Vite, outside Docker)"
    echo -e "  ${CYAN}1)${NC} Start   ${CYAN}2)${NC} Stop   ${CYAN}3)${NC} Clean cache + reinstall + start   ${CYAN}0)${NC} Back"
    read -r -p "  Choice: " choice
    case "$choice" in
      1) frontend_start; pause ;; 2) frontend_stop; pause ;; 3) frontend_clean; pause ;; 0|b|B) return ;;
      *) warn "Invalid choice" ;;
    esac
  done
}

menu_database() {
  while true; do
    header "Database"
    echo -e "  ${CYAN}1)${NC} Run migrations   ${CYAN}2)${NC} Open psql shell   ${CYAN}3)${NC} Reset everything (DELETES DATA)   ${CYAN}0)${NC} Back"
    read -r -p "  Choice: " choice
    case "$choice" in
      1) db_migrate; pause ;;
      2) db_shell ;;
      3) nuclear_reset; pause ;;
      0|b|B) return ;;
      *) warn "Invalid choice" ;;
    esac
  done
}

menu_logs() {
  header "Logs"
  local svc; svc="$(pick_service 'Logs of which service?')" || return 0
  read -r -p "  Follow live? [y/N] " follow
  if [[ "$follow" =~ ^[yY] ]]; then show_logs "$svc" 50 1; else show_logs "$svc" 100; pause; fi
}

menu_tests() {
  while true; do
    header "Tests and quality"
    echo -e "  ${CYAN}1)${NC} Backend unit tests (fast)          ${CYAN}2)${NC} Backend integration tests (Docker)"
    echo -e "  ${CYAN}3)${NC} All backend tests                  ${CYAN}4)${NC} Frontend tests"
    echo -e "  ${CYAN}5)${NC} Browser end-to-end tests (app must be running)"
    echo -e "  ${CYAN}6)${NC} Quality gates (backend + frontend) ${CYAN}7)${NC} Everything: quality + all tests"
    echo -e "  ${CYAN}8)${NC} Show all make commands             ${CYAN}0)${NC} Back"
    read -r -p "  Choice: " choice
    case "$choice" in
      1) run_tests unit; pause ;; 2) run_tests integration; pause ;; 3) run_tests backend; pause ;;
      4) run_tests frontend; pause ;; 5) run_tests e2e; pause ;; 6) run_tests quality; pause ;;
      7) run_tests all; pause ;; 8) make help; pause ;; 0|b|B) return ;;
      *) warn "Invalid choice" ;;
    esac
  done
}

menu_main() {
  INTERACTIVE=1
  while true; do
    clear
    echo -e "${BOLD}${BLUE}"
    echo "  ╔══════════════════════════════════════╗"
    echo "  ║   Jobs Radar — Dev Environment       ║"
    echo "  ║   by Innovation Ways                 ║"
    echo "  ╚══════════════════════════════════════╝"
    echo -e "${NC}"
    echo -e "  Status: $(status_line)"
    echo ""
    echo -e "  ${CYAN}1)${NC} Start / stop"
    echo -e "  ${CYAN}2)${NC} Health & status"
    echo -e "  ${CYAN}3)${NC} Frontend"
    echo -e "  ${CYAN}4)${NC} Database"
    echo -e "  ${CYAN}5)${NC} Logs"
    echo -e "  ${CYAN}6)${NC} Tests & quality"
    echo -e "  ${CYAN}7)${NC} Addresses (URLs)"
    echo -e "  ${CYAN}8)${NC} AI agents (MCP server)"
    echo -e "  ${CYAN}0)${NC} Exit"
    echo ""
    read -r -p "  Choice: " choice
    case "$choice" in
      1) menu_stack ;; 2) menu_health ;; 3) menu_frontend ;; 4) menu_database ;;
      5) menu_logs ;; 6) menu_tests ;; 7) show_urls; pause ;; 8) show_mcp; pause ;;
      0|q|Q|exit|quit) echo ""; exit 0 ;;
      *) warn "Invalid choice" ;;
    esac
  done
}

# --- main ---------------------------------------------------------------------------------
main() {
  load_env
  local cmd="${1:-}"; shift || true
  case "$cmd" in
    "")               menu_main ;;
    --help|-h)        usage ;;
    --init-env)       init_env "${1:-}" ;;
    --quick-start)    quick_start ;;
    --quick-stop)     quick_stop ;;
    --start)          start_services "${1:-}" ;;
    --stop)           stop_services "${1:-}" ;;
    --restart)        restart_services "${1:-}" ;;
    --rebuild)        rebuild_services "${1:-}" ;;
    --status)         show_status ;;
    --health)         health_deep ;;
    --urls)           show_urls ;;
    --mcp)            show_mcp ;;
    --wait-healthy)
      local t="$DEFAULT_WAIT_TIMEOUT"
      [[ "${1:-}" == "--timeout" ]] && t="${2:-$DEFAULT_WAIT_TIMEOUT}"
      wait_healthy "$t" ;;
    --logs)
      local svc="${1:-}" lines=100 follow=""
      shift || true
      while [[ $# -gt 0 ]]; do
        case "$1" in --lines) lines="${2:-100}"; shift ;; --follow) follow=1 ;; esac
        shift
      done
      [[ -n "$svc" ]] || { err "--logs needs a service (db|api|worker|frontend)"; exit 1; }
      show_logs "$svc" "$lines" "$follow" ;;
    --db-migrate)     db_migrate ;;
    --psql)           db_shell ;;
    --backup)         make backup ;;
    --restore-drill)  make restore-drill ;;
    --tests)          run_tests "${1:-}" ;;
    --frontend-start) frontend_start ;;
    --frontend-stop)  frontend_stop ;;
    --frontend-clean) frontend_clean ;;
    --demo)           demo_start ;;
    --demo-stop)      demo_stop ;;
    --nuclear-reset)  nuclear_reset "${1:-}" ;;
    *) err "Unknown option: $cmd"; usage; exit 1 ;;
  esac
}

main "$@"
