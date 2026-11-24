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
    if [ -z "${CODEMAP_FULL:-}" ] && [ -s {{graph_sh}} ] && [ -n "$(find .codemap/last_full -mmin -1440 2>/dev/null)" ]; then
      kind=incremental
      cp {{graph_sh}} {{graph_next_sh}}
      cp {{graph_sh}}.meta.json {{graph_next_sh}}.meta.json
      nice -n 19 $C build {{package_sh}} --deep --repeat 2 {{build_args}} --incremental -o {{graph_next_sh}} --recipe-output {{graph_sh}} >/dev/null 2>"$LOG.err" &
    else
      kind=full
      nice -n 19 $C build {{package_sh}} --deep --repeat 2 {{build_args}} -o {{graph_next_sh}} --recipe-output {{graph_sh}} >/dev/null 2>"$LOG.err" &
    fi
    bpid=$!
    wait "$bpid"; brc=$?
    if [ "$brc" -eq 0 ] &&
      mv {{graph_next_sh}}.meta.json {{graph_sh}}.meta.json 2>>"$LOG.err" &&
      mv {{graph_next_sh}} {{graph_sh}} 2>>"$LOG.err"; then
      [ "$kind" = full ] && touch .codemap/last_full
      $C devkit index --root "$ROOT" >/dev/null 2>>"$LOG.err"
      echo "$(date -Is) $(git log --oneline -1 | cut -c1-60) $kind ok $(( $(date +%s)-start ))s" >> "$LOG"
    else
      echo "$(date -Is) FAILED, see rebuild.log.err" >> "$LOG"
    fi
    [ -e "$ROOT/.codemap/rebuild.again" ] || break
  done
) 9>"$ROOT/.codemap/rebuild.lock" </dev/null >/dev/null 2>&1 &
