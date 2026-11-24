#!/usr/bin/env bash
# Generate the independent runtime trace on the pinned upstream test suite.
set -euo pipefail

work=$(realpath -m "$1")
tracer=$(realpath "${2:-$(dirname "$0")/../r1c132}")
mkdir -p "$work"
git clone -q --depth 1 --branch 3.1.3 -- https://github.com/pallets/werkzeug.git "$work/src"
[[ $(git -C "$work/src" rev-parse HEAD) == 6389612fd1ee1bd93579eed5026e8fd471d04abd ]]
uv venv --python 3.12 "$work/.venv"
python="$work/.venv/bin/python"
uv pip install --python "$python" -e "$work/src" \
  -r "$work/src/requirements/tests.txt" 'MarkupSafe==3.0.2'
"$python" -c 'from importlib.metadata import distributions; print(*sorted(f"{d.name.lower()}=={d.version}" for d in distributions()), sep="\n")' \
  > "$work/trace-deps.txt"
"$python" --version > "$work/trace-python.txt"
export PYTHONDONTWRITEBYTECODE=1
export R1C132_PKG_ROOT="$work/src/src/werkzeug"

trace_suite() {
  local mode=$1
  shift
  (
    cd "$work/src"
    "$python" -m pytest -q -ra -p no:cacheprovider --timeout=90 \
      --basetemp="$work/tmp-$mode" "$@" tests
  ) > "$work/pytest-$mode.txt" 2>&1
}

for mode in plain traced1 traced2; do
  status=0
  if [[ "$mode" == plain ]]; then
    PYTHONPATH="$work/src/src" trace_suite "$mode" || status=$?
  else
    R1C132_OUT="$work/trace${mode#traced}.json" PYTHONPATH="$work/src/src:$tracer" \
      trace_suite "$mode" -p r1c132_tracer || status=$?
  fi
  printf '%s\n' "$status" > "$work/status-$mode.txt"
  printf '%s rc=%s ' "$mode" "$status"
  tail -n 1 "$work/pytest-$mode.txt"
done
test -s "$work/trace1.json"
test -s "$work/trace2.json"
