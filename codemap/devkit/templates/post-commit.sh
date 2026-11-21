#!/bin/bash
# codemap-devkit:post-commit v{{devkit_version}} — managed by the codemap devkit; local, not in the repository.
# Rebuilds the codemap graph after every commit, in the background, so the MCP server (`serve --watch`)
# answers about the tree as committed. One build at a time (flock); a commit during a build queues one more
# pass. Incremental, with a full build when the last one is older than a day (an incremental --deep chain
# carries the earlier jedi sample forward). CODEMAP_FULL=1 forces a full build. The build runs in its own
# process group, so a signal to this loop takes the build and its workers down too.
ROOT=$(git rev-parse --show-toplevel)
C={{pin_assign}}
mkdir -p "$ROOT/.codemap/devkit"
LOG="$ROOT/.codemap/rebuild.log"
(
  flock -n 9 || { touch "$ROOT/.codemap/rebuild.again"; exit 0; }
  set -m
  bpid=""
  trap '[ -n "$bpid" ] && kill -TERM -- "-$bpid" 2>/dev/null; echo "$(date -Is) stopped by a signal" >> "$LOG"; exit 143' TERM INT HUP
  while :; do
    rm -f "$ROOT/.codemap/rebuild.again"
    cd "$ROOT" && start=$(date +%s)
    if [ -z "${CODEMAP_FULL:-}" ] && [ -s {{graph}} ] && [ -n "$(find .codemap/last_full -mmin -1440 2>/dev/null)" ]; then
      kind=incremental
      cp {{graph}} {{graph_next}}
      cp {{graph}}.meta.json {{graph_next}}.meta.json
      nice -n 19 $C build {{package}} --deep --repeat 2 {{build_args}} --incremental -o {{graph_next}} >/dev/null 2>"$LOG.err" &
    else
      kind=full
      nice -n 19 $C build {{package}} --deep --repeat 2 {{build_args}} -o {{graph_next}} >/dev/null 2>"$LOG.err" &
    fi
    bpid=$!
    wait "$bpid"; brc=$?
    if [ "$brc" -eq 0 ]; then
      mv {{graph_next}}.meta.json {{graph}}.meta.json
      mv {{graph_next}} {{graph}}
      [ "$kind" = full ] && touch .codemap/last_full
      $C devkit index --root "$ROOT" >/dev/null 2>>"$LOG.err"
      echo "$(date -Is) $(git log --oneline -1 | cut -c1-60) $kind ok $(( $(date +%s)-start ))s" >> "$LOG"
    else
      echo "$(date -Is) FAILED, see rebuild.log.err" >> "$LOG"
    fi
    [ -e "$ROOT/.codemap/rebuild.again" ] || break
  done
) 9>"$ROOT/.codemap/rebuild.lock" </dev/null >/dev/null 2>&1 &
