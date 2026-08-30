#!/usr/bin/env bash
# THE launcher for this study. The determinism flags are LAUNCH-time properties and
# invisible over RPC, so a server started any other way answers perfectly normally and
# quietly makes every measurement noisier. See the carla-determinism package's RULES.md:
#   D-3 -notexturestreaming   dominant render entropy source, 168x in the steering study
#   D-5 -quality-level=Epic   a determinism result, not a visual preference (High is worse)
set -uo pipefail
cd "$(dirname "$0")/.."
PORT=${CARLA_PORT:-2000}
CARLA_ROOT=${CARLA_ROOT:-$HOME/carla}
LOG=${CARLA_LOG:-$PWD/results/carla_server.log}
mkdir -p "$(dirname "$LOG")"
( cd "$CARLA_ROOT" && setsid nohup ./CarlaUE4.sh -carla-rpc-port="$PORT" \
    -RenderOffScreen -quality-level=Epic -notexturestreaming >>"$LOG" 2>&1 < /dev/null & )
for i in $(seq 1 60); do
  ss -ltn 2>/dev/null | grep -q ":$PORT" && break
  sleep 5
done
sleep 10
python3 -m carla_determinism --port "$PORT" || {
  echo "FATAL: the server on $PORT violates the determinism rules (above)."; exit 1; }
