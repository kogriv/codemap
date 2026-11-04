#!/usr/bin/env bash
# Gate probes for import-linter (card research/tools/import-linter.md §0.4). Usage: import_linter_probes.sh LINT_IMPORTS_BIN WORKDIR
# Each probe is a fresh copy of a three-layer fixture package `gp` (high > mid > low) with one change and one config.
set -u; L=$1; W=$2; rm -rf $W; mkdir -p $W; cd $W
base() {  # $1 = probe dir
  mkdir -p $1/gp/high $1/gp/mid $1/gp/low
  touch $1/gp/__init__.py $1/gp/high/__init__.py $1/gp/mid/__init__.py $1/gp/low/__init__.py
  printf 'class H:\n    pass\n' > $1/gp/high/h.py
  printf 'from gp.low.l import f\n' > $1/gp/mid/m.py
  printf 'def f():\n    return 1\n' > $1/gp/low/l.py
}
LAYERS='[importlinter]
root_package = gp

[importlinter:contract:layers]
name = gp layers
type = layers
containers = gp
layers =
    high
    mid
    low
'
FORB='[importlinter]
root_package = gp

[importlinter:contract:forb]
name = low must not import high
type = forbidden
source_modules = gp.low
'
run() {  # $1 = probe name; prints exit code and the first informative lines
  (cd $1 && "$L" --no-cache > out.txt 2>&1; echo "$1 rc=$? :: $(grep -v '^\s*$' out.txt | grep -iv '^=\+$\|^-\+$\|import linter' | head -4 | tr '\n' ' ' | cut -c1-230)")
}
p() { base $1; printf '%s' "$2" > $1/.importlinter; }

p G0c "$LAYERS"; run G0c
p G0 "$LAYERS"; printf 'from gp.high.h import H\n' >> G0/gp/low/l.py; run G0
p G1 "$LAYERS"; printf '\n\ndef g():\n    from gp.high.h import H\n    return H\n' >> G1/gp/low/l.py; run G1
p G2 "$LAYERS"; printf 'from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from gp.high.h import H\n' >> G2/gp/low/l.py; run G2
p G2b "$(printf '%s' "$LAYERS" | sed 's/^root_package = gp$/root_package = gp\nexclude_type_checking_imports = True/')"; printf 'from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from gp.high.h import H\n' >> G2b/gp/low/l.py; run G2b
p G3 "$LAYERS"; printf 'import gp.high.h\n' >> G3/gp/low/l.py; run G3
p G4 "$LAYERS"; printf 'from ..high import h\n' > G4/gp/low/__init__.py; run G4
p G5c "$LAYERS
exhaustive = True
"; mkdir -p G5c/gp/extra; touch G5c/gp/extra/__init__.py; run G5c
p G5 "$LAYERS
exhaustiv = True
"; mkdir -p G5/gp/extra; touch G5/gp/extra/__init__.py; run G5
p G6 "$FORB
forbiden_modules = gp.high
"; printf 'from gp.high.h import H\n' >> G6/gp/low/l.py; run G6
p G7c "$FORB
forbidden_modules = gp.high
"; printf 'from gp.high.h import H\n' >> G7c/gp/low/l.py; run G7c
p G7 "$FORB
forbidden_modules = gp.hihg
"; printf 'from gp.high.h import H\n' >> G7/gp/low/l.py; run G7
p G8 "$(printf '%s' "$FORB" | sed 's/source_modules = gp.low/source_modules = gp.lwo/')
forbidden_modules = gp.high
"; printf 'from gp.high.h import H\n' >> G8/gp/low/l.py; run G8
p G9 "$(printf '%s' "$LAYERS" | sed 's/^    high$/    hihg/')"; run G9
p G10 "$LAYERS
exhaustive = maybe
"; run G10
p G11 '[importlinter]
root_package = gp
'; run G11
p G13 "$(printf '%s' "$LAYERS" | sed 's/^type = layers$/type = layer/')"; run G13
p G14 "$(printf '%s' "$LAYERS" | sed 's/^root_package = gp$/root_pakage = gp/')"; run G14
p G15 "$LAYERS
ignore_imports =
    gp.low.l -> gp.hihg.h
"; run G15
echo "== G12: the cache (default on), clean run, then a violation added, then a second run"
base G12; printf '%s' "$LAYERS" > G12/.importlinter
(cd G12 && "$L" > out1.txt 2>&1; echo "G12 first rc=$?"; sleep 1; printf 'from gp.high.h import H\n' >> gp/low/l.py; "$L" > out2.txt 2>&1; echo "G12 after edit rc=$? :: $(grep -i 'broken\|kept' out2.txt | head -2 | tr '\n' ' ')")
echo PROBES_DONE
