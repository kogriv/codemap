"""R1-C112 truth for dead code: rust-analyzer's references to each item a tool called dead (recipe_rust.md D7).

    python research/tools/_rust/truth_refs.py <checkout> <items.json> > refs.json

`items.json` is a list of {"file", "line", "name"} (1-based line of the item as the tool reported it). For each item
the declaration is looked up within 3 lines of the reported one (`fn|struct|enum|trait|type|const|static|mod NAME`
or `macro_rules! NAME`), and `textDocument/references` is asked without the declaration. Each reference is classed
as test (a path under `tests/`, `benches/` or `examples/`, or a line after the file's first `#[cfg(test)]`) or
production. A method inside `impl Trait for Type` is marked `trait_impl`: it cannot be deleted while the impl
stands, whatever its references say, because calls through `dyn` and generics resolve to the trait's declaration.
The enclosing impl comes from rust-analyzer's `textDocument/documentSymbol` (an indentation scan was fooled by
raw strings at column 0). `cfg_variants` counts other declarations of the same name in the same file and the same enclosing item: a
`#[cfg(windows)]` twin is inactive for rust-analyzer on this platform and has no references here.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from truth_ra import LSP, pos, rel  # noqa: E402

DECL = r"\b(?:fn|struct|enum|trait|type|const|static|mod|union)\s+(?P<name>{n})\b|\bmacro_rules!\s*(?P<m>{n})\b"


def first_cfg_test(lines: list[str]) -> int | None:
    for i, line in enumerate(lines):
        if line.strip().startswith("#[cfg(test)]"):
            return i
    return None


def enclosing(symbols: list[dict], line: int, chain: tuple = ()) -> tuple:
    """Names of the document symbols enclosing a 0-based line, outermost first."""
    for sym in symbols or []:
        r = sym.get("range") or sym.get("location", {}).get("range")
        if r and r["start"]["line"] <= line <= r["end"]["line"]:
            return enclosing(sym.get("children", []), line, chain + (sym["name"],))
    return chain


def trait_impl(chain: tuple) -> bool:
    # rust-analyzer names an impl block "impl Trait for Type"; the method itself is the last element.
    return any(re.match(r"impl\b.*\bfor\b", n) for n in chain[:-1][-1:])


def main(argv):
    root = Path(argv[1]).resolve()
    items = json.loads(Path(argv[2]).read_text())
    cache: dict[str, list[str]] = {}
    symcache: dict = {}

    def text(f: str) -> list[str]:
        if f not in cache:
            cache[f] = (root / f).read_text(encoding="utf-8").splitlines()
        return cache[f]

    lsp = LSP(root)
    # Hierarchical symbols: without this rust-analyzer answers documentSymbol with a flat list, no impl nesting.
    lsp.start({"documentSymbol": {"hierarchicalDocumentSymbolSupport": True}})
    out = []
    for it in items:
        f, ln, name = it["file"], int(it["line"]), it["name"]
        lines = text(f)
        pat = re.compile(DECL.format(n=re.escape(name)))
        hit = None
        for i in sorted(range(max(0, ln - 4), min(len(lines), ln + 3)), key=lambda i: abs(i - (ln - 1))):
            m = pat.search(lines[i])
            if m:
                hit = (i, m.start("name") if m.group("name") else m.start("m"))
                break
        rec = {**it}
        if hit is None:
            rec["error"] = "declaration not found near the reported line"
            out.append(rec)
            continue
        i, col = hit
        try:
            refs = lsp.request("textDocument/references",
                               {**pos(root / f, i, col), "context": {"includeDeclaration": False}}) or []
        except RuntimeError as e:  # a file outside every crate's module tree (included by `#[path]`, a script)
            rec["error"] = f"rust-analyzer: {e}"[:200]
            out.append(rec)
            continue
        prod, test = [], []
        for r in refs:
            rf = rel(root, r["uri"]) if r["uri"].startswith(root.as_uri()) else r["uri"]
            rl = r["range"]["start"]["line"]
            cft = first_cfg_test(text(rf)) if not rf.startswith("file:") else None
            is_test = bool(re.search(r"(^|/)(tests|benches|examples)/", rf)) or (cft is not None and rl > cft)
            (test if is_test else prod).append(f"{rf}:{rl + 1}")
        if f not in symcache:
            symcache[f] = lsp.request("textDocument/documentSymbol", {"textDocument": {"uri": (root / f).as_uri()}})
        chain = enclosing(symcache[f], i)
        twins = sum(1 for j, line in enumerate(lines)
                    if j != i and pat.search(line) and enclosing(symcache[f], j)[:-1] == chain[:-1])
        rec.update({"decl_line": i + 1, "trait_impl": trait_impl(chain), "enclosing": list(chain[:-1]),
                    "cfg_variants": twins, "refs_prod": sorted(prod),
                    "refs_test": sorted(test)})
        out.append(rec)
    lsp.stop()
    json.dump(out, sys.stdout, indent=1, sort_keys=True)
    print()


if __name__ == "__main__":
    main(sys.argv)
