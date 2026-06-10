#!/usr/bin/env bash
set -euo pipefail

# status.sh -- one-shot status of the Tokenless KJV model stack.
# Shows KJV bundle (:8091), raw model (:8088), training procs, pid/memory/elapsed.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TOKENLESS_HOME="${TOKENLESS_HOME:-${REPO_ROOT}/ml-training}"
LOG_DIR="${TOKENLESS_HOME}/logs"
KJV_PORT="${KJV_PORT:-8091}"
RAW_PORT="${RAW_PORT:-8088}"

# --- Color (if supported) ---------------------------------------------------
USE_COLOR=0
if [[ -t 1 ]] && command -v tput >/dev/null 2>&1; then
  ncolors="$(tput colors 2>/dev/null || echo 0)"
  if [[ "${ncolors}" =~ ^[0-9]+$ ]] && [[ "${ncolors}" -ge 8 ]]; then
    USE_COLOR=1
    C_GREEN="$(tput setaf 2)"; C_RED="$(tput setaf 1)"
    C_YELLOW="$(tput setaf 3)"; C_BOLD="$(tput bold)"; C_RESET="$(tput sgr0)"
  fi
fi
if [[ "${USE_COLOR}" -eq 0 ]]; then
  C_GREEN=""; C_RED=""; C_YELLOW=""; C_BOLD=""; C_RESET=""
fi

green() { printf '%s%s%s' "${C_GREEN}" "$1" "${C_RESET}"; }
red()   { printf '%s%s%s' "${C_RED}"   "$1" "${C_RESET}"; }
yel()   { printf '%s%s%s' "${C_YELLOW}" "$1" "${C_RESET}"; }
bold()  { printf '%s%s%s' "${C_BOLD}"  "$1" "${C_RESET}"; }

# --- Helpers ----------------------------------------------------------------
http_ok() {
  local url="$1"
  local code
  code="$(curl -fsS -o /dev/null -w '%{http_code}' --max-time 2 "${url}" 2>/dev/null || echo 000)"
  [[ "${code}" == "200" ]]
}

proc_mem_mb() {
  # macOS ps rss is KB
  local pid="$1" rss_kb
  rss_kb="$(ps -o rss= -p "${pid}" 2>/dev/null | tr -d ' ' || true)"
  if [[ -n "${rss_kb:-}" ]] && [[ "${rss_kb}" =~ ^[0-9]+$ ]]; then
    awk -v k="${rss_kb}" 'BEGIN{printf "%.1f", k/1024}'
  else
    echo "-"
  fi
}

proc_elapsed() {
  local pid="$1"
  ps -o etime= -p "${pid}" 2>/dev/null | tr -d ' ' || echo "-"
}

pid_from_file() {
  local pf="$1"
  [[ -f "${pf}" ]] || { echo ""; return; }
  local pid
  pid="$(cat "${pf}" 2>/dev/null || true)"
  if [[ "${pid:-}" =~ ^[0-9]+$ ]] && kill -0 "${pid}" 2>/dev/null; then
    echo "${pid}"
  else
    echo ""
  fi
}

# --- Servers ----------------------------------------------------------------
echo "$(bold "== Tokenless KJV model stack status ==") $(date '+%Y-%m-%d %H:%M:%S')"
echo

printf '%-22s %-8s %-6s %-8s %-9s %-8s %s\n' "PROCESS" "PID" "PORT" "STATUS" "MEM(MB)" "UPTIME" "HEALTH"
printf '%-22s %-8s %-6s %-8s %-9s %-8s %s\n' "----------------------" "--------" "------" "--------" "---------" "--------" "------"

status_row() {
  local name="$1" pidfile="$2" port="$3"
  local url="http://127.0.0.1:${port}/healthz"
  local pid mem up statuslabel
  pid="$(pid_from_file "${pidfile}")"

  if [[ -z "${pid}" ]]; then
    statuslabel="$(red DOWN)"; pid="-"; mem="-"; up="-"
  else
    mem="$(proc_mem_mb "${pid}")"
    up="$(proc_elapsed "${pid}")"
    if http_ok "${url}"; then
      statuslabel="$(green UP)"
    else
      statuslabel="$(yel RUN-NOHLTH)"
    fi
  fi
  printf '%-22s %-8s %-6s %-17s %-9s %-8s %s\n' \
    "${name}" "${pid}" "${port}" "${statuslabel}" "${mem}" "${up}" "${url}"
}

status_row "kjv_bundle_server" "${LOG_DIR}/kjv_bundle_server.pid" "${KJV_PORT}"
status_row "raw_model_server" "${LOG_DIR}/raw_model_server.pid" "${RAW_PORT}"

# --- Training processes -----------------------------------------------------
echo
echo "$(bold "-- training processes --")"
printf '%-28s %-8s %-9s %-8s %s\n' "PROCESS" "PID" "MEM(MB)" "UPTIME" "LOG"
printf '%-28s %-8s %-9s %-8s %s\n' "----------------------------" "--------" "---------" "--------" "----"

train_found=0
if [[ -d "${LOG_DIR}" ]]; then
  shopt -s nullglob
  for pf in "${LOG_DIR}"/*_train.pid "${LOG_DIR}"/queue_*.pid; do
    name="$(basename "${pf}" .pid)"
    pid="$(pid_from_file "${pf}")"
    if [[ -n "${pid}" ]]; then
      mem="$(proc_mem_mb "${pid}")"
      up="$(proc_elapsed "${pid}")"
      log="${LOG_DIR}/${name}.log"
      [[ -f "${log}" ]] || log="-"
      printf '%-28s %-8s %-9s %-8s %s\n' "${name}" "${pid}" "${mem}" "${up}" "${log}"
      train_found=1
    fi
  done
  shopt -u nullglob
fi
if [[ "${train_found}" -eq 0 ]]; then
  echo "  (no training processes running)"
fi

echo
if http_ok "http://127.0.0.1:${KJV_PORT}/healthz"; then
  echo "$(green "KJV runtime healthy on :${KJV_PORT}")"
  exit 0
else
  echo "$(yel "KJV runtime not responding on :${KJV_PORT}")"
  exit 1
fi
