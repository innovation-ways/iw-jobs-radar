#!/usr/bin/env bash
# =============================================================================
# jobs-radar.sh — Jobs Radar development environment launcher (ADR-018)
#
# Interactive:  ./jobs-radar.sh
# CLI:          ./jobs-radar.sh --init-env | --quick-start | --quick-stop | --health | ...
#
# AI agents: use CLI flags. `--health` exits 0 only when everything that is running is healthy.
# Services managed by Docker Compose: db, api, worker. The frontend runs outside Docker (ADR-019).
# =============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

FRONTEND_DIR="$SCRIPT_DIR/frontend"
FRONTEND_PID_FILE="$SCRIPT_DIR/.frontend.pid"
FRONTEND_LOG_FILE="$SCRIPT_DIR/logs/frontend.log"
SERVICES=(db api worker)
DEFAULT_WAIT_TIMEOUT=180

# corepack installs the pnpm shim here (see CLAUDE.md); make sure it is found.
export PATH="$HOME/.local/bin:$PATH"

# --- output helpers ---------------------------------------------------------
RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'; CYAN=$'\033[0;36m'; BOLD=$'\033[1m'; NC=$'\033[0m'
ok()   { echo -e "  ${GREEN}✓${NC}  $1"; }
err()  { echo -e "  ${RED}✗${NC}  $1" >&2; }
warn() { echo -e "  ${YELLOW}!${NC}  $1"; }
info() { echo -e "  ${CYAN}→${NC}  $1"; }
header() { echo -e "\n${BOLD}$1${NC}"; }

# --- environment ------------------------------------------------------------
# Loads .env without overriding variables already set by the caller (explicit env wins).
load_env() {
  [[ -f .env ]] || return 0
  local line key value
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ "$line" =~ ^[[:space:]]*(#|$) ]] && continue
    line="$(echo "$line" | sed 's/[[:space:]]#.*$//')"
    [[ "$line" =~ ^([A-Za-z_][A-Za-z_0-9]*)=(.*)$ ]] || continue
    key="${BASH_REMATCH[1]}"; value="${BASH_REMATCH[2]}"
    [[ -v "$key" ]] || export "$key=$value"
  done < .env
}

api_port()      { echo "${JOBS_RADAR_API_PORT:-8100}"; }
frontend_port() { echo "${JOBS_RADAR_FRONTEND_PORT:-5180}"; }
bind_addr()     { echo "${JOBS_RADAR_API_BIND:-127.0.0.1}"; }

COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.dev.yml)
compose() { docker compose "${COMPOSE_FILES[@]}" "$@"; }

require_env_file() {
  if [[ ! -f .env ]]; then
    err ".env not found. Run ./jobs-radar.sh --init-env first."
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
  local name port busy=0
  for pair in "API:$(api_port)" "DB:${JOBS_RADAR_DB_PORT:-5440}"; do
    name="${pair%%:*}"; port="${pair##*:}"
    # A port already published by this project's own containers is fine.
    if ss -ltn 2>/dev/null | grep -q ":${port} " && ! compose ps --format '{{.Ports}}' 2>/dev/null | grep -q ":${port}->"; then
      err "$name port $port is already in use. Change it in .env."
      busy=1
    fi
  done
  return $busy
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
show_status() { compose ps; local pid; pid="$(frontend_pid)"
  if [[ -n "$pid" ]]; then ok "frontend running (pid $pid) on port $(frontend_port)"; else info "frontend not running"; fi; }

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
  # setsid puts the dev server in its own process group so the whole tree can be stopped.
  (cd "$FRONTEND_DIR" && JOBS_RADAR_API_PORT="$(api_port)" nohup setsid pnpm dev \
      --host "$(bind_addr)" --port "$(frontend_port)" --strictPort >"$FRONTEND_LOG_FILE" 2>&1 &
   echo $! >"$FRONTEND_PID_FILE")
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
  kill -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null
  rm -f "$FRONTEND_PID_FILE"; ok "frontend stopped."
}

frontend_clean() {
  frontend_stop
  rm -rf "$FRONTEND_DIR/node_modules/.vite" "$FRONTEND_DIR/.vite"
  [[ -d "$FRONTEND_DIR" ]] && (cd "$FRONTEND_DIR" && pnpm install --frozen-lockfile)
  frontend_start
}

# --- compound actions ----------------------------------------------------------
quick_start() { init_env; start_services; wait_healthy "${1:-$DEFAULT_WAIT_TIMEOUT}" && frontend_start; }
quick_stop()  { frontend_stop; compose stop; }

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
  cat <<EOF
Jobs Radar launcher

Usage: ./jobs-radar.sh [option]      (no option: interactive menu)

Setup
  --init-env [--force]       Create .env with a random DB password and credential key
Whole stack
  --quick-start              Init env if needed, start db/api/worker, wait healthy, start frontend
  --quick-stop               Stop frontend and containers
  --health                   Deep health check; exit 0 only if everything running is healthy
  --wait-healthy [--timeout N]
  --status                   Containers and frontend state
Services (db | api | worker; omit to apply to all)
  --start [svc]  --stop [svc]  --restart [svc]  --rebuild [svc]
  --logs <svc|frontend> [--lines N] [--follow]
Database
  --db-migrate               Run Alembic migrations (api container)
Frontend (runs outside Docker)
  --frontend-start | --frontend-stop | --frontend-clean
Danger
  --nuclear-reset [--yes]    Remove containers and the database volume
  --help
EOF
}

# --- interactive menu ---------------------------------------------------------------
menu() {
  while true; do
    header "Jobs Radar"
    cat <<EOF
  1) Quick start        2) Quick stop        3) Health check     4) Status
  5) Logs (api)         6) Logs (worker)     7) Migrate DB       8) Frontend start
  9) Frontend stop      0) Quit
EOF
    read -r -p "  > " choice
    case "$choice" in
      1) quick_start ;; 2) quick_stop ;; 3) health_deep ;; 4) show_status ;;
      5) show_logs api 50 ;; 6) show_logs worker 50 ;; 7) db_migrate ;;
      8) frontend_start ;; 9) frontend_stop ;; 0|q) exit 0 ;;
      *) warn "Unknown option." ;;
    esac
  done
}

# --- main ---------------------------------------------------------------------------------
main() {
  load_env
  local cmd="${1:-}"; shift || true
  case "$cmd" in
    "")               menu ;;
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
    --frontend-start) frontend_start ;;
    --frontend-stop)  frontend_stop ;;
    --frontend-clean) frontend_clean ;;
    --nuclear-reset)  nuclear_reset "${1:-}" ;;
    *) err "Unknown option: $cmd"; usage; exit 1 ;;
  esac
}

main "$@"
