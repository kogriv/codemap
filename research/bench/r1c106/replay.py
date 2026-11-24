"""Replay R1-C106 through the released wheel and a candidate checkout."""

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


SOURCE = '''\
from argparse import ArgumentParser

registry = {}
events = []


def retain(key):
    def store(fn):
        registry[key] = fn
        return fn
    return store


@retain("old")
def _hook():
    return "old callback"


@retain("new")
def _hook():
    return "new callback"


def _ordinary():
    return 1


def _ordinary():
    return 2


def _decorated_later():
    return 3


@retain("late")
def _decorated_later():
    return 4


class Runner(ArgumentParser):
    def _print_message(self, message, file=None):
        events.append("external dispatch")

    def _unused_private(self):
        return 0
'''


def observed_runtime(source):
    spec = importlib.util.spec_from_file_location("proofpkg", source)
    package = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(package)
    package.Runner().print_help()
    observed = {"callbacks": [package.registry[key]() for key in ("old", "new")],
                "external_calls": package.events}
    assert observed == {"callbacks": ["old callback", "new callback"],
                        "external_calls": ["external dispatch"]}, observed
    return observed


def replay(work, package, candidate, deep):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    if candidate is not None:
        env["PYTHONPATH"] = str(candidate)
    graph = work / "graph.json"

    def cli(*args):
        return subprocess.check_output([sys.executable, "-m", "codemap", *args],
                                       env=env, cwd=work, text=True)

    cli("build", package, "-o", graph, *(["--deep"] if deep else []))
    report = ("report", "dead-code", "--graph", graph, "--public")
    data = json.loads(cli(*report, "--format", "json"))
    high = json.loads(cli(*report, "--format", "json", "--min-confidence", "high"))
    text = cli(*report, "--min-confidence", "high")
    shadows = {row["id"] for row in data["shadowed"]}
    assert shadows == {row["id"] for row in high["shadowed"]}
    section = text.partition("## Shadowed definitions")[2].partition("\n## ")[0]
    for name in ("_ordinary", "_decorated_later", "_hook"):
        symbol = f"proofpkg.{name}"
        assert (f"`{symbol}`" in section) == (symbol in shadows), (name, section)
    grades = {row["id"]: row for row in data["candidates"]}
    override = "proofpkg.Runner._print_message"
    unused = "proofpkg.Runner._unused_private"
    high_ids = {row["id"] for row in high["candidates"]}
    expected_shadows = {"proofpkg._ordinary", "proofpkg._decorated_later"}
    if candidate is None:
        assert shadows == expected_shadows | {"proofpkg._hook"}, shadows
        assert override in high_ids, high_ids
    else:
        assert shadows == expected_shadows, shadows
        assert override not in high_ids and grades[override]["confidence"] == "medium", grades
        assert any("argparse" in reason and "_print_message" in reason
                   for reason in grades[override]["reasons"]), grades[override]
    assert unused in high_ids, high_ids
    return {"shadowed": sorted(shadows), "high": sorted(high_ids), "override": grades[override]}


def main(candidate):
    with tempfile.TemporaryDirectory(prefix="r1c106-proof-") as tmp:
        work = Path(tmp)
        package = work / "proofpkg"
        package.mkdir()
        source = package / "__init__.py"
        source.write_text(SOURCE)
        data = {"runtime": observed_runtime(source), "baseline": {}, "candidate": {}}
        for tier in ("fast", "deep"):
            data["baseline"][tier] = replay(work, package, None, tier == "deep")
            data["candidate"][tier] = replay(work, package, candidate, tier == "deep")
        print(json.dumps(data, indent=2, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    main(parser.parse_args().candidate.resolve())
