#!/usr/bin/env bash
set -euo pipefail

# stop_all.sh -- graceful shutdown of all PID-tracked processes under $TOKENLESS_HOME/logs

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRAINING_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
TOKENLESS_HOME="${TOKENLESS_HOME:-${TRAINING_DIR}}"
LOG_DIR="${TOKENLESS_HOME}/logs"

if [[ ! -d "${LOG_DIR}" ]]; then
  echo "Nothing to do: ${LOG_DIR} does not exist."
  exit 0
fi

shopt -s nullglob
pidfiles=( "${LOG_DIR}"/*.pid )
shopt -u nullglob

if [[ ${#pidfiles[@]} -eq 0 ]]; then
  echo "No PID files in ${LOG_DIR}."
  exit 0
fi

killed=0
stale=0

for pf in "${pidfiles[@]}"; do
  name="$(basename "${pf}" .pid)"
  pid="$(cat "${pf}" 2>/dev/null || true)"

  if [[ -z "${pid:-}" ]] || ! [[ "${pid}" =~ ^[0-9]+$ ]]; then
    echo "  stale (empty/invalid): ${name}"
    rm -f "${pf}"; stale=$((stale+1)); continue
  fi

  if ! kill -0 "${pid}" 2>/dev/null; then
    echo "  stale (pid ${pid} gone): ${name}"
    rm -f "${pf}"; stale=$((stale+1)); continue
  fi

  echo "  SIGTERM -> ${name} (pid=${pid})"
  kill -TERM "${pid}" 2>/dev/null || true

  gone=0
  for _ in 1 2 3 4 5; do
    if ! kill -0 "${pid}" 2>/dev/null; then gone=1; break; fi
    sleep 1
  done

  if [[ "${gone}" -eq 0 ]]; then
    echo "  SIGKILL -> ${name} (pid=${pid}) (did not exit in 5s)"
    kill -KILL "${pid}" 2>/dev/null || true
  fi

  rm -f "${pf}"
  killed=$((killed+1))
done

echo
echo "== stop_all summary =="
echo "  killed       : ${killed}"
echo "  stale cleaned: ${stale}"
