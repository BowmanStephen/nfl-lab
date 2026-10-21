#!/usr/bin/env bash
# Start an isolated static server for public/. Writes URL + PID into VERIFY_RUN_DIR.
# Usage: serve.sh start|stop|status
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
PUBLIC="${ROOT}/public"
ACTION="${1:-start}"

if [[ -z "${VERIFY_RUN_DIR:-}" ]]; then
  RUN_ID="${VERIFY_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)-$$}"
  VERIFY_RUN_DIR="${ROOT}/.cursor/skills/verify-nfl-lab/runs/${RUN_ID}"
  export VERIFY_RUN_DIR
fi
mkdir -p "$VERIFY_RUN_DIR"

PID_FILE="${VERIFY_RUN_DIR}/serve.pid"
URL_FILE="${VERIFY_RUN_DIR}/serve.url"
LOG_FILE="${VERIFY_RUN_DIR}/serve.log"
PORT_FILE="${VERIFY_RUN_DIR}/serve.port"

start_server() {
  if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "serve already running: $(cat "$URL_FILE") (pid $(cat "$PID_FILE"))"
    return 0
  fi

  # Bind ephemeral port on loopback only.
  # Python writes the chosen port to PORT_FILE once listen succeeds.
  # Do not keep a caller's command-substitution pipeline open for the server's lifetime.
  python3 - "$PUBLIC" "$PORT_FILE" "$LOG_FILE" >>"$LOG_FILE" 2>&1 <<'PY' &
import http.server, socketserver, sys, pathlib
root, port_file, log_path = sys.argv[1:4]
class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=root, **kwargs)
    def log_message(self, fmt, *args):
        with open(log_path, "a") as fh:
            fh.write("%s - %s\n" % (self.log_date_time_string(), fmt % args))

class ReuseTCPServer(socketserver.TCPServer):
    allow_reuse_address = True

with ReuseTCPServer(("127.0.0.1", 0), Handler) as httpd:
    port = httpd.server_address[1]
    pathlib.Path(port_file).write_text(str(port) + "\n")
    httpd.serve_forever()
PY
  pid=$!
  echo "$pid" > "$PID_FILE"

  # Wait for port file
  for _ in $(seq 1 50); do
    if [[ -f "$PORT_FILE" ]]; then
      break
    fi
    sleep 0.1
  done
  [[ -f "$PORT_FILE" ]] || { kill "$pid" 2>/dev/null || true; echo "serve failed to bind" >&2; exit 1; }

  port="$(tr -d '[:space:]' < "$PORT_FILE")"
  url="http://127.0.0.1:${port}"
  echo "$url" > "$URL_FILE"

  # Ready probe
  for _ in $(seq 1 50); do
    code="$(curl -s -o /dev/null -w '%{http_code}' "${url}/index.html" || true)"
    if [[ "$code" == "200" ]]; then
      echo "VERIFY_RUN_DIR=${VERIFY_RUN_DIR}"
      echo "VERIFY_URL=${url}"
      echo "serve ready: ${url} (pid ${pid})"
      return 0
    fi
    sleep 0.1
  done
  kill "$pid" 2>/dev/null || true
  echo "serve never returned 200; see ${LOG_FILE}" >&2
  exit 1
}

stop_server() {
  if [[ -f "$PID_FILE" ]]; then
    pid="$(cat "$PID_FILE")"
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      # wait briefly
      for _ in $(seq 1 20); do
        kill -0 "$pid" 2>/dev/null || break
        sleep 0.1
      done
      if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null || true
      fi
      echo "stopped serve pid ${pid}"
    else
      echo "serve pid ${pid} already dead"
    fi
    rm -f "$PID_FILE" "$URL_FILE" "$PORT_FILE"
  else
    echo "no serve.pid in ${VERIFY_RUN_DIR}"
  fi
}

status_server() {
  if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "up pid=$(cat "$PID_FILE") url=$(cat "$URL_FILE")"
    exit 0
  fi
  echo "down"
  exit 1
}

case "$ACTION" in
  start) start_server ;;
  stop) stop_server ;;
  status) status_server ;;
  *) echo "usage: serve.sh start|stop|status" >&2; exit 2 ;;
esac
