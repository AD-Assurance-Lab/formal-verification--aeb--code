#!/usr/bin/env bash
# THE launcher for this study. The determinism flags are LAUNCH-time properties and
# invisible over RPC, so a server started any other way answers perfectly normally and
# quietly makes every measurement noisier. See the carla-determinism package's RULES.md:
#   D-3 -notexturestreaming   dominant render entropy source, 168x in the steering study
#   D-5 -quality-level=Epic   a determinism result, not a visual preference (High is worse)
#
# IT REFUSES TO LAUNCH ONTO AN OCCUPIED PORT, and that is the important part. This has
# now failed twice the same way. The 2026-08-30 A12 rebuild launched while another
# study's server held 3000: the new server died with "bind: Address already in use", the
# old one kept answering, the determinism preflight passed against IT, and the first job
# sat until its 600 s client timeout. On 2026-09-06 a relaunch six seconds after pkill
# did it again -- CARLA had not finished shutting down, the new server segfaulted on the
# bind, and the job chain measured on a server this script had not configured and did not
# know the age of. Both times the script printed "determinism preflight OK".
#
# Usage:  bash tools/carla_launch.sh          # refuses if $CARLA_PORT is taken
#         CARLA_TAKEOVER=1 bash tools/carla_launch.sh   # stop what is there, then launch
set -uo pipefail
cd "$(dirname "$0")/.."
PORT=${CARLA_PORT:-2000}
CARLA_ROOT=${CARLA_ROOT:-$HOME/carla}
LOG=${CARLA_LOG:-$PWD/results/carla_server.log}
mkdir -p "$(dirname "$LOG")"

port_busy() { ss -ltn 2>/dev/null | grep -q ":$PORT[[:space:]]"; }

if port_busy; then
  if [ "${CARLA_TAKEOVER:-0}" != "1" ]; then
    echo "FATAL: something is already listening on $PORT. Refusing to launch."
    echo "  A second server cannot bind it, so this script would exit believing it had"
    echo "  started a server while every measurement went to a server it did not"
    echo "  configure. Whoever owns that one may be mid-run."
    ss -ltnp 2>/dev/null | grep ":$PORT[[:space:]]" || true
    echo "  If it is yours and idle:  CARLA_TAKEOVER=1 bash tools/carla_launch.sh"
    exit 1
  fi
  echo "==> CARLA_TAKEOVER: stopping whatever holds $PORT"
  pkill -f "[C]arlaUE4" || true
  # CARLA does not release the port promptly on SIGTERM. Six seconds was not enough on
  # 2026-09-06; wait for the socket itself rather than for a duration.
  for _ in $(seq 1 30); do port_busy || break; sleep 2; done
  if port_busy; then
    echo "    SIGTERM did not clear it after 60 s; SIGKILL"
    pkill -9 -f "[C]arlaUE4" || true
    for _ in $(seq 1 20); do port_busy || break; sleep 2; done
  fi
  if port_busy; then
    echo "FATAL: $PORT is still bound. Not launching."; exit 1
  fi
fi

( cd "$CARLA_ROOT" && setsid nohup ./CarlaUE4.sh -carla-rpc-port="$PORT" \
    -RenderOffScreen -quality-level=Epic -notexturestreaming >>"$LOG" 2>&1 < /dev/null & )
for i in $(seq 1 60); do
  port_busy && break
  sleep 5
done
if ! port_busy; then
  echo "FATAL: no server came up on $PORT within 300 s. Tail of $LOG:"
  tail -20 "$LOG"; exit 1
fi
sleep 10

# The server on the port must be the one THIS script started with THESE flags. The
# preflight reads /proc for the flags, but a running server that already carries them --
# someone else's, mid-run -- would pass it just as happily.
SRV_PID=$(ss -ltnp 2>/dev/null | grep ":$PORT[[:space:]]" | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)
if [ -n "$SRV_PID" ]; then
  SRV_AGE=$(ps -o etimes= -p "$SRV_PID" 2>/dev/null | tr -d ' ')
  echo "  server pid $SRV_PID on port $PORT, ${SRV_AGE:-?} s old"
  if [ -n "${SRV_AGE:-}" ] && [ "$SRV_AGE" -gt 300 ]; then
    echo "FATAL: that server is ${SRV_AGE}s old, so it is not the one just launched."
    echo "  Measuring on it would violate R-SIM-1 and the run would not know."
    exit 1
  fi
fi

python3 -m carla_determinism --port "$PORT" || {
  echo "FATAL: the server on $PORT violates the determinism rules (above)."; exit 1; }
