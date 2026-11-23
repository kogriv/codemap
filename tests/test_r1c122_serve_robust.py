"""R1-C122 — `serve` survives any JSON value, and a reload never interleaves with a request.

Expectations E1–E3 are in BACKLOG.md (R1-C122), written before the change (external audit F-04, F-05).
"""

from __future__ import annotations

import io
import json
import shutil
import threading
from pathlib import Path

import pytest

from codemap import store
from codemap.extract import extract
from codemap.serve.server import serve_stdio
from codemap.serve.session import Session


def _pkg(root: Path, extra: int) -> Path:
    (root / "pkg").mkdir(parents=True)
    body = "def f():\n    return 1\n\n\ndef g():\n    return f()\n"
    body += "".join(f"\n\ndef extra_{i}():\n    return {i}\n" for i in range(extra))
    (root / "pkg/__init__.py").write_text(body)
    return root / "pkg"


@pytest.fixture
def graphs(tmp_path):
    out = []
    for i, extra in enumerate((0, 40)):
        g = extract(str(_pkg(tmp_path / f"t{i}", extra)))
        path = tmp_path / f"g{i}.json"
        store.save(g, path)
        out.append(path)
    return out


@pytest.mark.parametrize("line", ["null", "[]", "42", '"x"', '{"op": []}', '{"op": "stats", "args": 5}',
                                  '{"op": "stats", "args": [1]}', '{"op": 7}'])
def test_e1_any_json_value_gets_an_error_and_the_server_goes_on(graphs, line):
    session = Session(store.load(graphs[0]), graph_path=str(graphs[0]))
    out = io.StringIO()
    assert serve_stdio(session, io.StringIO(line + '\n{"op": "stats"}\n'), out) == 0
    first, second = (json.loads(x) for x in out.getvalue().splitlines())
    assert first["ok"] is False and first["error"]
    assert second["ok"] is True and second["result"]["nodes"] >= 1


def test_e2_e3_requests_and_reloads_never_interleave(graphs, tmp_path):
    served = tmp_path / "served.json"
    shutil.copy(graphs[0], served)
    session = Session(store.load(served), graph_path=str(served))
    sizes = {len(store.load(p).nodes) for p in graphs}
    stop = threading.Event()
    problems: list[str] = []

    def reloader():
        i = 0
        while not stop.is_set():
            shutil.copy(graphs[i % 2], served)
            env = session.handle({"op": "reload"})
            if not env.get("ok"):
                problems.append(f"reload: {env}")
            i += 1

    def asker():
        for _ in range(300):
            q = session.handle({"op": "callers", "args": {"symbol": "f"}})
            if not q.get("ok") or "resolved" not in q:
                problems.append(f"callers lost its resolved block: {q}")
            s = session.handle({"op": "stats"})
            if s["result"]["nodes"] not in sizes:
                problems.append(f"stats counted {s['result']['nodes']} nodes, a snapshot has {sizes}")

    threads = [threading.Thread(target=reloader)] + [threading.Thread(target=asker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads[1:]:
        t.join()
    stop.set()
    threads[0].join()
    assert not problems, problems[:5]
