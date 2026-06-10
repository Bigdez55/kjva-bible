#!/usr/bin/env bash
set -euo pipefail

# start_all.sh -- Tokenless KJV runtime launcher
# Primary entry: serve_kjv_bundle.py on :8091 (exact citations + retrieval chat)
# Optional: --with-raw starts serve_raw_model.py on :8088
# Idempotent: kills any existing instance before relaunch.

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPTS_DIR}/../.." && pwd)"
TOKENLESS_HOME="${TOKENLESS_HOME:-${REPO_ROOT}/ml-training}"
VENV="${TOKENLESS_HOME}/.venv"
LOG_DIR="${TOKENLESS_HOME}/logs"

KJV_PORT=8091
RAW_PORT=8088
WITH_RAW=0
BUNDLE_DIR="${TOKENLESS_HOME}/exports/kjv_tokenless_v1_active"

for arg in "$@"; do
  case "$arg" in
    --with-raw) WITH_RAW=1 ;;
    --port=*)   KJV_PORT="${arg#--port=}" ;;
    --bundle-dir=*) BUNDLE_DIR="${arg#--bundle-dir=}" ;;
    -h|--help)
      echo "Usage: $0 [--with-raw] [--port=N] [--bundle-dir=PATH]"
      exit 0 ;;
    *) echo "Unknown arg: $arg" >&2; exit 2 ;;
  esac
done

# --- Pre-flight -------------------------------------------------------------
if [[ ! -d "${VENV}" ]]; then
  echo "ERROR: venv not found at ${VENV}" >&2
  echo "       Create it with: python3.12 -m venv ${VENV}" >&2
  exit 1
fi
if [[ ! -x "${VENV}/bin/python" ]]; then
  echo "ERROR: ${VENV}/bin/python is not executable" >&2
  exit 1
fi

mkdir -p "${LOG_DIR}"

# --- Helpers ----------------------------------------------------------------
kill_by_pidfile() {
  local pidfile="$1"
  [[ -f "${pidfile}" ]] || return 0
  local pid
  pid="$(cat "${pidfile}" 2>/dev/null || true)"
  if [[ -n "${pid:-}" ]] && kill -0 "${pid}" 2>/dev/null; then
    echo "  killing existing pid=${pid} (${pidfile##*/})"
    kill -TERM "${pid}" 2>/dev/null || true
    for _ in 1 2 3 4 5; do
      kill -0 "${pid}" 2>/dev/null || break
      sleep 1
    done
    kill -0 "${pid}" 2>/dev/null && kill -KILL "${pid}" 2>/dev/null || true
  fi
  rm -f "${pidfile}"
}

wait_health() {
  local url="$1" tries="${2:-15}"
  for _ in $(seq 1 "${tries}"); do
    if curl -fsS -o /dev/null -w '%{http_code}' "${url}" 2>/dev/null | grep -q '^200$'; then
      return 0
    fi
    sleep 1
  done
  return 1
}

start_server() {
  local name="$1" script="$2" port="$3"
  shift 3
  local pidfile="${LOG_DIR}/${name}.pid"
  local logfile="${LOG_DIR}/${name}.log"

  kill_by_pidfile "${pidfile}"

  echo "  starting ${name} on :${port}"
  (
    cd "${SCRIPTS_DIR}"
    nohup "${VENV}/bin/python" "${SCRIPTS_DIR}/${script}" "$@" --port "${port}" \
      >>"${logfile}" 2>&1 &
    echo $! > "${pidfile}"
  )
  sleep 1
  local pid
  pid="$(cat "${pidfile}")"
  if ! kill -0 "${pid}" 2>/dev/null; then
    echo "ERROR: ${name} died immediately. Tail of ${logfile}:" >&2
    tail -n 20 "${logfile}" >&2 || true
    return 1
  fi
}

# --- Launch -----------------------------------------------------------------
echo "== start_all =="
start_server "kjv_bundle_server" "serve_kjv_bundle.py" "${KJV_PORT}" --bundle-dir "${BUNDLE_DIR}"

if [[ "${WITH_RAW}" -eq 1 ]]; then
  start_server "raw_model_server" "serve_raw_model.py" "${RAW_PORT}" --export "${BUNDLE_DIR}"
fi

# --- Health wait ------------------------------------------------------------
KJV_URL="http://127.0.0.1:${KJV_PORT}/healthz"
RAW_URL="http://127.0.0.1:${RAW_PORT}/healthz"

echo "  waiting for KJV bundle /healthz ..."
KJV_OK=0; wait_health "${KJV_URL}" 15 && KJV_OK=1 || true

RAW_OK="n/a"
if [[ "${WITH_RAW}" -eq 1 ]]; then
  echo "  waiting for raw model /healthz ..."
  RAW_OK=0; wait_health "${RAW_URL}" 15 && RAW_OK=1 || true
fi

# --- Status table -----------------------------------------------------------
printf '\n%-22s %-8s %-6s %-8s %s\n' "PROCESS" "PID" "PORT" "STATUS" "HEALTH"
printf '%-22s %-8s %-6s %-8s %s\n' "----------------------" "--------" "------" "--------" "------"

kjv_pid="$(cat "${LOG_DIR}/kjv_bundle_server.pid" 2>/dev/null || echo '-')"
kjv_stat=$([[ "${KJV_OK}" -eq 1 ]] && echo "UP" || echo "DOWN")
printf '%-22s %-8s %-6s %-8s %s\n' "kjv_bundle_server" "${kjv_pid}" "${KJV_PORT}" "${kjv_stat}" "${KJV_URL}"

if [[ "${WITH_RAW}" -eq 1 ]]; then
  raw_pid="$(cat "${LOG_DIR}/raw_model_server.pid" 2>/dev/null || echo '-')"
  raw_stat=$([[ "${RAW_OK}" -eq 1 ]] && echo "UP" || echo "DOWN")
  printf '%-22s %-8s %-6s %-8s %s\n' "raw_model_server" "${raw_pid}" "${RAW_PORT}" "${raw_stat}" "${RAW_URL}"
fi

echo
if [[ "${KJV_OK}" -eq 1 ]] && { [[ "${WITH_RAW}" -eq 0 ]] || [[ "${RAW_OK}" -eq 1 ]]; }; then
  echo "OK: stack is healthy."
  exit 0
fi
echo "FAIL: one or more servers unhealthy. See ${LOG_DIR}/*.log" >&2
exit 1
