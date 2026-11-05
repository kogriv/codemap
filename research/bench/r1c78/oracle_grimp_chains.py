"""R1-C78 oracle: which forbidden pairs of bquant have an import chain, by grimp (no codemap code).

Design ``docs/design/forbidden_chains.md`` A8. grimp's graph matched codemap's truth set on this tree edge for
edge (``research/tools/import-linter.md`` §1), and shares no code with codemap, so its shortest chains are the
independent answer to "does ``from`` reach ``to``, and in how many hops".

    uv run --isolated --no-project --with grimp==3.18 python oracle_grimp_chains.py BQUANT_CHECKOUT OUT.json

BQUANT_CHECKOUT is a bquant checkout at ``aca0718``. The script copies its ``bquant/`` package once per tree
(as is, M1, M2, M3 — the import-linter card's mutations of ``core/config.py``) and never edits the checkout.
TYPE_CHECKING imports are included (grimp's default), as codemap counts every import scope.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# bquant's codemap.toml at aca0718, `forbidden`, in file order.
PAIRS = [("core", "analysis"), ("core", "indicators"), ("core", "data"), ("core", "visualization"),
         ("data", "indicators"), ("data", "analysis"), ("indicators", "analysis"),
         ("indicators", "visualization")]

MUTATIONS = {
    "base": None,
    "M1_module_level": "\nimport bquant.analysis\n",
    "M2_function_local": "\n\ndef _r1c78_m2():\n    import bquant.analysis\n    return bquant.analysis\n",
    "M3_type_checking": "\nfrom typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import bquant.analysis\n",
}

CHAINS = r"""
import json, sys, grimp
pairs = json.loads(sys.argv[2])
g = grimp.build_graph("bquant", cache_dir=None)
out = {}
for frm, to in pairs:
    c = g.find_shortest_chain(importer=f"bquant.{frm}", imported=f"bquant.{to}", as_packages=True)
    out[f"{frm}->{to}"] = {"chain": list(c) if c else None, "hops": (len(c) - 1) if c else None}
print(json.dumps(out))
"""


def main() -> None:
    checkout, out_path = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
    rev = subprocess.run(["git", "-C", str(checkout), "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    result = {"bquant": rev, "grimp": None, "trees": {}}
    for name, extra in MUTATIONS.items():
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(checkout / "bquant", Path(tmp) / "bquant")
            if extra:
                with open(Path(tmp) / "bquant" / "core" / "config.py", "a") as f:
                    f.write(extra)
            r = subprocess.run([sys.executable, "-c", CHAINS, tmp, json.dumps(PAIRS)],
                               capture_output=True, text=True, cwd=tmp, env={"PYTHONPATH": tmp, "PATH": "/usr/bin:/bin"})
            if r.returncode:
                raise SystemExit(r.stderr)
            chains = json.loads(r.stdout)
        result["trees"][name] = {
            "broken": sorted(k for k, v in chains.items() if v["chain"]),
            "chains": chains,
        }
    import grimp
    result["grimp"] = getattr(grimp, "__version__", None)
    out_path.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    for name, t in result["trees"].items():
        print(f"{name:20} {len(t['broken'])} broken: {', '.join(t['broken']) or '-'}")


if __name__ == "__main__":
    main()
