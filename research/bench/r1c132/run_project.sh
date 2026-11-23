#!/bin/bash
# R1-C132: one project end to end. Usage: run_project.sh <name> <workdir> [<bench dir>]
# Clones the pinned tag, checks the commit, installs it with its test deps in a Python 3.12 venv, runs the
# suite without the tracer and twice with it (C6, C3), builds fast and deep graphs with codmap 0.0.47 from PyPI,
# compares. Everything lands in <workdir>/<name>/.
set -euo pipefail
NAME=$1; WORK=$(realpath -m "$2"); BENCH=$(realpath "${3:-$(dirname "$0")}")
CODMAP=0.0.47
case $NAME in
  more-itertools) REPO=more-itertools/more-itertools TAG=v11.2.1 SHA=4aeb4338ae1407d8da9723e86da99efeb446f719 PKG=more_itertools DEPS="pytest" ;;
  click)          REPO=pallets/click TAG=8.5.1 SHA=cf19179e8e2fd54c601378cec9e0d21bb12b6fb1 PKG=src/click DEPS="pytest" ;;
  rich)           REPO=Textualize/rich TAG=v15.0.0 SHA=6ac483cbea39cab124dfd3483bba70ffafb71050 PKG=rich DEPS="pytest attrs" ;;
  markdown-it-py) REPO=executablebooks/markdown-it-py TAG=v4.3.0 SHA=d504583a458edfa399ee800074244fceec288862 PKG=markdown_it DEPS="pytest pytest-regressions pytest-datadir linkify-it-py" ;;
  jinja)          REPO=pallets/jinja TAG=3.1.6 SHA=15206881c006c79667fe5154fe80c01c65410679 PKG=src/jinja2 DEPS="pytest trio" ;;
  *) echo "unknown project $NAME" >&2; exit 2 ;;
esac
D=$WORK/$NAME; mkdir -p "$D"; cd "$D"
log() { echo "$(date -Is) $*" | tee -a run.log; }
[ -d src ] || git clone -q --depth 1 --branch "$TAG" "https://github.com/$REPO.git" src
got=$(git -C src rev-parse HEAD); [ "$got" = "$SHA" ] || { log "commit $got is not the pinned $SHA"; exit 3; }
[ -d venv ] || uv venv -q -p 3.12 venv
uv pip install -q -p venv/bin/python -e src $DEPS
CM=$WORK/codmap-$CODMAP
[ -d "$CM" ] || { uv venv -q -p 3.12 "$CM" && uv pip install -q -p "$CM/bin/python" "codmap==$CODMAP"; }
log "python $(venv/bin/python -V 2>&1); codmap $("$CM/bin/codemap" --version)"
PY=venv/bin/python
ROOT=$(realpath src/$PKG)
SRCDIR=$(dirname "$ROOT")
run_tests() {  # $1 label, rest: extra args
  local label=$1; shift
  (cd src && "$D/$PY" -m pytest -q -p no:cacheprovider -o addopts= "$@" tests > "$D/pytest-$label.txt" 2>&1) || true
  log "pytest $label: $(tail -1 "pytest-$label.txt")"
}
export PYTHONDONTWRITEBYTECODE=1
run_tests plain
for i in 1 2; do
  R1C132_PKG_ROOT=$ROOT R1C132_OUT=$D/trace$i.json PYTHONPATH=$BENCH run_tests traced$i -p r1c132_tracer
done
"$CM/bin/codemap" build "$ROOT" -o fast.json > build-fast.txt 2>&1
"$CM/bin/codemap" build "$ROOT" --deep --repeat 3 -o deep.json > build-deep.txt 2>&1
for t in fast deep; do
  "$CM/bin/python" "$BENCH/compare.py" --graph $t.json --trace trace1.json trace2.json --src "$SRCDIR" --out cmp-$t.json > cmp-$t.txt
  log "compare $t: $(tr '\n' ' ' < cmp-$t.txt)"
done
"$CM/bin/python" "$BENCH/compare.py" --graph deep.json --trace trace1.json trace2.json --src "$SRCDIR" --determinism > determinism.txt
log "determinism: $(cat determinism.txt)"
