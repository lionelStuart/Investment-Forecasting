#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8765}"
DB_PATH="${DB_PATH:-$ROOT_DIR/data/investment_forecasting.sqlite3}"
DEFAULT_PYTHON_BIN="python3"
if [[ -x "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3" ]]; then
  DEFAULT_PYTHON_BIN="/Library/Frameworks/Python.framework/Versions/3.14/bin/python3"
fi
PYTHON_BIN="${PYTHON_BIN:-$DEFAULT_PYTHON_BIN}"
PYTHON_BIN="$(command -v "$PYTHON_BIN")"
LOG_DIR="${LOG_DIR:-$ROOT_DIR/.runtime}"
PID_FILE="$LOG_DIR/web.pid"
LOG_FILE="$LOG_DIR/web.log"
LABEL="${LAUNCHD_LABEL:-local.investment-forecasting.web}"
PLIST_FILE="$LOG_DIR/$LABEL.plist"

mkdir -p "$LOG_DIR" "$(dirname "$DB_PATH")"

health_check() {
  local attempt
  for attempt in $(seq 1 30); do
    if curl -fsS "http://$HOST:$PORT/" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.5
  done
  return 1
}

print_db_summary() {
  DB_PATH="$DB_PATH" "$PYTHON_BIN" - <<'PY' || true
import os
import sqlite3
from pathlib import Path

db_path = Path(os.environ["DB_PATH"])
tables = [
    "assets",
    "price_daily",
    "fund_holdings",
    "features_daily",
    "model_predictions",
    "daily_advice",
    "market_snapshots",
    "macro_observations",
    "capital_flow_observations",
]

if not db_path.exists():
    print(f"db_status=missing path={db_path}")
    raise SystemExit(0)

with sqlite3.connect(db_path) as conn:
    counts = {}
    for table in tables:
        try:
            counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except sqlite3.Error:
            counts[table] = "n/a"
    latest_advice = None
    try:
        latest_advice = conn.execute("SELECT MAX(advice_date) FROM daily_advice").fetchone()[0]
    except sqlite3.Error:
        pass

print("db_status=" + " ".join(f"{key}={value}" for key, value in counts.items()))
if latest_advice:
    print(f"latest_advice={latest_advice}")
if counts.get("assets") == 0 or counts.get("price_daily") == 0:
    print("warning=database_has_no_assets_or_prices")
PY
}

stop_port_listener() {
  local pids
  pids="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    kill $pids 2>/dev/null || true
    sleep 1
  fi
}

write_launchd_plist() {
  cat > "$PLIST_FILE" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>WorkingDirectory</key>
  <string>$ROOT_DIR</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PYTHONPATH</key>
    <string>$ROOT_DIR/src</string>
  </dict>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON_BIN</string>
    <string>-m</string>
    <string>investment_forecasting.cli</string>
    <string>web</string>
    <string>run</string>
    <string>--db</string>
    <string>$DB_PATH</string>
    <string>--host</string>
    <string>$HOST</string>
    <string>--port</string>
    <string>$PORT</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$LOG_FILE</string>
  <key>StandardErrorPath</key>
  <string>$LOG_FILE</string>
</dict>
</plist>
PLIST
}

restart_with_launchctl() {
  local domain="gui/$(id -u)"
  write_launchd_plist
  launchctl bootout "$domain/$LABEL" >/dev/null 2>&1 || true
  stop_port_listener
  launchctl bootstrap "$domain" "$PLIST_FILE"
  launchctl kickstart -k "$domain/$LABEL"
  if ! health_check; then
    echo "Web service failed health check. Log: $LOG_FILE" >&2
    tail -80 "$LOG_FILE" >&2 || true
    return 1
  fi
  echo "launchctl service restarted: $LABEL"
  echo "url=http://$HOST:$PORT"
  echo "db=$DB_PATH"
  echo "log=$LOG_FILE"
  print_db_summary
}

restart_with_nohup() {
  if [[ -f "$PID_FILE" ]]; then
    local old_pid
    old_pid="$(cat "$PID_FILE")"
    if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
      kill "$old_pid" 2>/dev/null || true
      sleep 1
    fi
  fi
  stop_port_listener
  (
    cd "$ROOT_DIR"
    export PYTHONPATH="$ROOT_DIR/src"
    exec nohup "$PYTHON_BIN" -m investment_forecasting.cli web run \
      --db "$DB_PATH" \
      --host "$HOST" \
      --port "$PORT" \
      >> "$LOG_FILE" 2>&1 < /dev/null
  ) &
  echo "$!" > "$PID_FILE"
  if ! health_check; then
    echo "Web service failed health check. Log: $LOG_FILE" >&2
    tail -80 "$LOG_FILE" >&2 || true
    return 1
  fi
  echo "nohup service restarted: pid=$(cat "$PID_FILE")"
  echo "url=http://$HOST:$PORT"
  echo "db=$DB_PATH"
  echo "log=$LOG_FILE"
  print_db_summary
}

if command -v launchctl >/dev/null 2>&1 && [[ "$(uname -s)" == "Darwin" ]]; then
  restart_with_launchctl
else
  restart_with_nohup
fi
