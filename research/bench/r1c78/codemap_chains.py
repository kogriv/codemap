"""R1-C78 acceptance A8: codemap's indirect `forbidden` on bquant, against the grimp oracle.

    python codemap_chains.py BQUANT_CHECKOUT ORACLE.json OUT.json

Same trees as ``oracle_grimp_chains.py`` (as is, M1, M2, M3 on ``core/config.py``). bquant's own
``[architecture]`` is read from the checkout and every ``forbidden`` item is made ``indirect``. For each tree:
which rules break, which forbidden items break, and the shortest witness per broken item, in hops. Compared
with the oracle's pairs and hop counts. Prints the rendered verdict for M1 too (the docs example).
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

from codemap.arch import check_contract, parse_contract
from codemap.extract import extract
from codemap.query import Query
from codemap.serve.check import render_check
from codemap.tomlio import read_toml

sys.path.insert(0, str(Path(__file__).parent))
from oracle_grimp_chains import MUTATIONS  # noqa: E402  (the same trees, by construction)


def hops(v, frm: str, q) -> int:
    if any(q._layer_of(u) == frm for u, _ in v.edges):
        return 1                                    # a direct edge: the witness is the edge itself
    return min(line.count(" → ") for line in v.modules if " → " in line)


def main() -> None:
    checkout, oracle_path, out_path = Path(sys.argv[1]).resolve(), Path(sys.argv[2]), Path(sys.argv[3])
    oracle = json.loads(oracle_path.read_text())
    data, err = read_toml(checkout / "codemap.toml")
    assert not err, err
    section = dict(data["architecture"])
    section["forbidden"] = [{**it, "indirect": True} for it in section["forbidden"]]
    contract = parse_contract(section)
    assert contract.error is None, contract.error
    result, ok = {"trees": {}}, True
    for name, extra in MUTATIONS.items():
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(checkout / "bquant", Path(tmp) / "bquant")
            if extra:
                with open(Path(tmp) / "bquant" / "core" / "config.py", "a") as f:
                    f.write(extra)
            q = Query(extract(str(Path(tmp) / "bquant")))
            vs = check_contract(q, contract)
            if name == "M1_module_level":
                result["m1_rendered"] = render_check(q, contract, vs)
        broken = {}
        for v in vs:
            if v.rule == "forbidden":
                frm = v.summary.split("`")[1]
                to = v.summary.split("`")[3]
                broken[f"{frm}->{to}"] = hops(v, frm, q)
        want = {k: oracle["trees"][name]["chains"][k]["hops"] for k in oracle["trees"][name]["broken"]}
        agree = broken == want
        ok &= agree
        result["trees"][name] = {"rules": sorted({v.rule for v in vs}), "forbidden_broken": broken,
                                 "oracle": want, "agree": agree}
        print(f"{name:20} rules={sorted({v.rule for v in vs})} forbidden={broken} oracle={want} "
              f"{'AGREE' if agree else 'DIFFER'}")
    result["all_agree"] = ok
    out_path.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    print("\n" + result["m1_rendered"])


if __name__ == "__main__":
    main()
