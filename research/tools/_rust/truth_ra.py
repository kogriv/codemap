"""R1-C111 truth: rust-analyzer's answers to the R1/R2/R3/R5 questions over LSP (docs/design/recipe_rust.md D3).

    python research/tools/_rust/truth_ra.py <ripgrep checkout at the pinned commit> > truth.json

Speaks LSP over stdio to `rust-analyzer`, waits until the server reports itself quiescent, then asks:
- R1 `workspace/symbol` for each name (all symbols, workspace scope), kept only on an exact name match;
- R2 `callHierarchy/incomingCalls` at the definition of each target (`textDocument/references` for a macro);
- R3 the same, once more, for every caller found in R2;
- R5 `textDocument/implementation` at each trait's name.
Positions are found from the source text (the line declaring the item); the script fails loudly if a
declaration is not found exactly once. Output is sorted, with paths relative to the root, so two runs diff.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import tomllib
from pathlib import Path
from queue import Empty, Queue

HERE = Path(__file__).resolve().parent


class LSP:
    def __init__(self, root: Path):
        self.root = root
        self.p = subprocess.Popen(["rust-analyzer"], cwd=root, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL)
        self.n = 0
        self.replies: dict[int, Queue] = {}
        self.quiescent = threading.Event()
        threading.Thread(target=self._read, daemon=True).start()

    def _send(self, obj):
        body = json.dumps(obj).encode()
        self.p.stdin.write(f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
        self.p.stdin.flush()

    def _read(self):
        f = self.p.stdout
        while True:
            line = f.readline()
            if not line:
                return
            length = 0
            while line.strip():
                if line.lower().startswith(b"content-length:"):
                    length = int(line.split(b":")[1])
                line = f.readline()
            msg = json.loads(f.read(length))
            if "id" in msg and "method" not in msg:
                self.replies.setdefault(msg["id"], Queue()).put(msg)
            elif msg.get("method") == "experimental/serverStatus":
                if msg["params"].get("quiescent"):
                    self.quiescent.set()
            elif "id" in msg and "method" in msg:  # server request: answer null
                self._send({"jsonrpc": "2.0", "id": msg["id"], "result": None})

    def request(self, method, params, timeout=600):
        self.n += 1
        i = self.n
        q = self.replies.setdefault(i, Queue())
        self._send({"jsonrpc": "2.0", "id": i, "method": method, "params": params})
        try:
            msg = q.get(timeout=timeout)
        except Empty:
            raise TimeoutError(method) from None
        if "error" in msg:
            raise RuntimeError(f"{method}: {msg['error']}")
        return msg.get("result")

    def notify(self, method, params):
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def start(self):
        self.request("initialize", {
            "processId": os.getpid(), "rootUri": self.root.as_uri(),
            "capabilities": {"experimental": {"serverStatusNotification": True},
                             "textDocument": {"callHierarchy": {}, "implementation": {}, "references": {}},
                             "window": {"workDoneProgress": True}},
            "initializationOptions": {"workspace": {"symbol": {"search": {"kind": "all_symbols",
                                                                         "scope": "workspace", "limit": 1000}}},
                                      "cachePriming": {"enable": True}, "checkOnSave": False},
        })
        self.notify("initialized", {})
        if not self.quiescent.wait(1800):
            raise TimeoutError("rust-analyzer never became quiescent")

    def stop(self):
        try:
            self.request("shutdown", None, timeout=30)
            self.notify("exit", None)
        finally:
            self.p.wait(timeout=30)


def rel(root: Path, uri: str) -> str:
    return str(Path(uri.removeprefix("file://")).relative_to(root))


def find_decl(root: Path, pattern: str, path_hint: str) -> tuple[Path, int, int]:
    hits = []
    for f in sorted(root.glob(path_hint)):
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines()):
            m = re.search(pattern, line)
            if m:
                hits.append((f, i, m.start("name")))
    if len(hits) != 1:
        raise SystemExit(f"declaration {pattern!r} in {path_hint}: {len(hits)} hits, need exactly 1: {hits}")
    return hits[0]


# Where each pre-registered target is declared: (regex with a `name` group, glob under the root).
DECLS = {
    "grep_searcher::Sink::matched": (r"^\s{4}fn (?P<name>matched)\b", "crates/searcher/src/sink.rs", "Sink"),
    "grep_matcher::Matcher::find_at": (r"^\s{4}fn (?P<name>find_at)\b", "crates/matcher/src/lib.rs", "Matcher"),
    "grep_searcher::Searcher::search_path": (r"^\s{4}pub fn (?P<name>search_path)\b",
                                             "crates/searcher/src/searcher/mod.rs", None),
    "grep_cli::escape": (r"^pub fn (?P<name>escape)\(", "crates/cli/src/escape.rs", None),
    "ignore::ParallelVisitor::visit": (r"^\s{4}fn (?P<name>visit)\(", "crates/ignore/src/walk.rs", "ParallelVisitor"),
    "err_message": (r"^macro_rules! (?P<name>err_message)", "crates/core/messages.rs", None),
}
TRAITS = {
    "grep_searcher::Sink": (r"^pub trait (?P<name>Sink) ", "crates/searcher/src/sink.rs"),
    "grep_matcher::Matcher": (r"^pub trait (?P<name>Matcher) ", "crates/matcher/src/lib.rs"),
    "ignore::ParallelVisitor": (r"^pub trait (?P<name>ParallelVisitor):", "crates/ignore/src/walk.rs"),
}


def trait_scoped(root: Path, pattern: str, path: str, trait: str | None):
    """A method declared inside `pub trait <trait>`: the first match after the trait line, before its closing brace."""
    if trait is None:
        return find_decl(root, pattern, path)
    f = root / path
    lines = f.read_text(encoding="utf-8").splitlines()
    start = next(i for i, l in enumerate(lines) if re.match(rf"^pub trait {trait}\b", l))
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("}"))
    hits = [(f, i, m.start("name")) for i in range(start, end) if (m := re.search(pattern, lines[i]))]
    if len(hits) != 1:
        raise SystemExit(f"{trait}::{pattern}: {len(hits)} hits inside the trait")
    return hits[0]


def pos(f: Path, line: int, col: int) -> dict:
    return {"textDocument": {"uri": f.as_uri()}, "position": {"line": line, "character": col}}


def item_id(root: Path, it: dict) -> str:
    return f"{rel(root, it['uri'])}::{it.get('detail') or ''}::{it['name']}@{it['selectionRange']['start']['line'] + 1}"


def incoming(lsp: LSP, root: Path, f: Path, line: int, col: int) -> dict:
    items = lsp.request("textDocument/prepareCallHierarchy", pos(f, line, col)) or []
    if len(items) != 1:
        return {"error": f"prepareCallHierarchy returned {len(items)} items"}
    calls = lsp.request("callHierarchy/incomingCalls", {"item": items[0]}) or []
    out = []
    for c in calls:
        fr = c["from"]
        out.append({"caller": item_id(root, fr),
                    "sites": sorted(f"{rel(root, fr['uri'])}:{r['start']['line'] + 1}" for r in c["fromRanges"]),
                    "_item": fr})
    return {"target": item_id(root, items[0]), "callers": sorted(out, key=lambda x: x["caller"])}


def main(argv):
    root = Path(argv[1]).resolve()
    q = tomllib.loads((HERE / "questions.toml").read_text(encoding="utf-8"))
    t0 = time.time()
    lsp = LSP(root)
    lsp.start()
    out = {"tree": q["tree"], "rust_analyzer": subprocess.run(["rust-analyzer", "--version"], capture_output=True,
                                                              text=True).stdout.strip(),
           "ready_seconds": round(time.time() - t0, 1), "r1": {}, "r2": {}, "r3": {}, "r5": {}}
    for r in q["r1"]:
        syms = lsp.request("workspace/symbol", {"query": r["name"]}) or []
        hits = sorted({f"{rel(root, s['location']['uri'])}:{s['location']['range']['start']['line'] + 1}"
                       f"::{s.get('containerName') or ''}" for s in syms
                       if s["name"] == r["name"] and s["location"]["uri"].startswith(root.as_uri())})
        # workspace/symbol also returns re-exports (`pub use a::{Name}`); R1 asks for definitions only.
        defs = []
        for h in hits:
            path, line = h.split("::")[0].rsplit(":", 1)
            text = (root / path).read_text(encoding="utf-8").splitlines()[int(line) - 1]
            if re.search(r"\b(fn|struct|enum|trait|mod|type|const|static|union)\b|\bmacro_rules!", text):
                defs.append(h)
        out["r1"][r["name"]] = {"definitions": defs, "reexports": sorted(set(hits) - set(defs))}
    for r in q["r2"]:
        pat, path, trait = DECLS[r["symbol"]]
        f, line, col = trait_scoped(root, pat, path, trait)
        if r["kind"] == "macro":
            refs = lsp.request("textDocument/references", {**pos(f, line, col), "context": {"includeDeclaration": False}}) or []
            out["r2"][r["symbol"]] = {"kind": "macro", "sites": sorted(
                f"{rel(root, x['uri'])}:{x['range']['start']['line'] + 1}" for x in refs)}
            continue
        ans = incoming(lsp, root, f, line, col)
        callers = ans.get("callers", [])
        out["r2"][r["symbol"]] = {"kind": r["kind"], "target": ans.get("target"), "error": ans.get("error"),
                                  "callers": [{k: v for k, v in c.items() if k != "_item"} for c in callers]}
        depth2 = {}
        for c in callers:
            it = c["_item"]
            sub = lsp.request("callHierarchy/incomingCalls", {"item": it}) or []
            depth2[c["caller"]] = sorted(item_id(root, s["from"]) for s in sub)
        out["r3"][r["symbol"]] = depth2
    for name, (pat, path) in TRAITS.items():
        f, line, col = find_decl(root, pat, path)
        impls = lsp.request("textDocument/implementation", pos(f, line, col)) or []
        out["r5"][name] = sorted(f"{rel(root, x['uri'])}:{x['range']['start']['line'] + 1}" for x in impls)
    lsp.stop()
    json.dump(out, sys.stdout, indent=1, sort_keys=True)
    print()


if __name__ == "__main__":
    main(sys.argv)
