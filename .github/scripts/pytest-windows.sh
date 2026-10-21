#!/usr/bin/env bash
# pytest for the Windows runner, made so the step always ends with its output:
#
#   .github/scripts/pytest-windows.sh <limit-seconds> [pytest args...]
#
# On Windows a hung test run never ended the step: the runner's own time limit
# and a cancel didn't take, and the log never came back. Here pytest's output
# goes to a file, so no process it leaves behind can hold the step's output
# open, and pytest is stopped if it runs past the limit. A single test that
# runs past two minutes prints every thread's stack and ends pytest.
set -u
limit="$1"
shift
log="$(mktemp)"
start=$(date +%s)
py=.venv/Scripts/python.exe
[ -x "$py" ] || py=.venv/bin/python  # to try it on Linux or macOS
timeout --kill-after=15 "$limit" "$py" -m pytest -v -p no:cacheprovider --durations=10 \
  -o faulthandler_timeout=120 -o faulthandler_exit_on_timeout=true "$@" >"$log" 2>&1
status=$?
cat "$log"
echo "pytest exited with code $status after $(( $(date +%s) - start ))s"
if [ "$status" = 124 ] || [ "$status" = 137 ]; then
  echo "::error::pytest ran past ${limit}s and was stopped; the end of the output above shows where it was"
fi
if command -v tasklist >/dev/null; then
  echo "Python processes still running:"
  tasklist //FI "IMAGENAME eq python.exe"
fi
exit "$status"
