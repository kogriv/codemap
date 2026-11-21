"""`codemap devkit init | update | status` (R1-C108 D1, D2).

One rule decides every write: a managed region is rewritten only when its current content hashes to what the
devkit last wrote. A hand-edited region is reported with a diff and kept; a foreign artifact in the devkit's
place is never overwritten without ``--force`` (the git hook's version then goes to
``.codemap/devkit/post-commit``, to be called from the existing hook).

Exit codes: 0 — done, nothing needs attention; 1 — done, with items that need attention (hand-edited,
foreign, outdated in ``status``); 2 — refused (bad arguments, nothing installed for ``update``).
"""

from __future__ import annotations

import difflib
import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from codemap.devkit import DEVKIT_VERSION, render, sha, template
from codemap.devkit.artifacts import (CI_MARK, HOOK_MARK, Artifact, ClaudeHooks, JsonKey,
                                      MarkdownRegion, TomlRegion, WholeFile, canon_json)
from codemap.devkit.state import STATE, load_state, save_state

GRAPH = ".codemap/graph.json"
GRAPH_NEXT = ".codemap/graph.next.json"
HOOK_ALT = ".codemap/devkit/post-commit"
GITIGNORE_LINE = ".codemap/"
LABELS = {
    "agents": "agent rules block",
    "mcp": "MCP server for Claude Code",
    "codex": "MCP server for Codex",
    "hook": "post-commit graph rebuild",
    "claude_hooks": "Claude Code hooks",
    "ci": "CI gate",
}


def _version() -> str:
    from codemap.provenance import tool_version
    return tool_version() or "unknown"


# --------------------------------------------------------------------------- the pin

def running_pin() -> list[str]:
    """How to run *this* codemap: its console script, else ``python -m codemap``."""
    argv0 = Path(sys.argv[0]) if sys.argv and sys.argv[0] else None
    if argv0 is not None and argv0.name == "codemap" and argv0.exists():
        # abspath, not resolve: `..` is folded, a venv's symlinked bin is kept as the user named it
        return [os.path.abspath(argv0)]
    return [sys.executable, "-m", "codemap"]


def pin_from_mcp(entry: dict | None) -> list[str] | None:
    """The pin recorded in an `.mcp.json` codemap entry: its command plus the args before `serve`."""
    if not isinstance(entry, dict) or not isinstance(entry.get("command"), str):
        return None
    args = [a for a in entry.get("args", []) if isinstance(a, str)]
    head = args[:args.index("serve")] if "serve" in args else []
    return [entry["command"], *head]


def pin_version(pin: list[str]) -> str | None:
    try:
        out = subprocess.run([*pin, "--version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    parts = (out.stdout or "").split()
    return parts[1] if len(parts) > 1 and parts[0] == "codemap" else None


def pin_has_mcp(pin: list[str]) -> bool | None:
    """Can the pinned interpreter import `mcp`? (`serve --mcp` needs the `codmap[mcp]` extra.)"""
    py = None
    if len(pin) >= 3 and pin[1] == "-m":
        py = pin[0]
    else:
        try:
            first = Path(pin[0]).read_text(encoding="utf-8", errors="replace").splitlines()[0]
        except (OSError, IndexError):
            first = ""
        if first.startswith("#!"):
            py = first[2:].strip().split()[0] if first[2:].strip() else None
    if not py:
        return None
    try:
        r = subprocess.run([py, "-c", "import mcp"], capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.returncode == 0


# --------------------------------------------------------------------------- rendering

def build_args(st: dict) -> str:
    parts: list[str] = []
    for c in st.get("consumers", []):
        parts += ["--consumer", c]
    for d in st.get("docs", []):
        parts += ["--docs", d]
    if st.get("consumers"):
        parts += ["--mode", "full"]
    return shlex.join(parts)


def context(st: dict, pin: list[str], codemap_version: str, root: Path | None = None) -> dict:
    pkg = st["package"]
    return {
        "devkit_version": DEVKIT_VERSION,
        "codemap_version": codemap_version,
        "package": pkg,
        "package_name": Path(pkg).name,
        "graph": st.get("graph", GRAPH),
        "graph_next": GRAPH_NEXT,
        "build_args": build_args(st),
        "agents_file": st.get("agents_file", "AGENTS.md"),
        "pin_shell": shlex.join(pin),
        "pin_assign": shlex.quote(shlex.join(pin)),
        "pin_command_toml": json.dumps(pin[0]),
        "pin_args_toml": "".join(json.dumps(a) + ", " for a in pin[1:]),
        # Codex resolves a relative `cwd` against `.codex/`; an absolute root leaves nothing to assume.
        "root_toml": json.dumps(str(root) if root is not None else "."),
        "outside_languages": outside_languages(root),
    }


def outside_languages(root: Path | None) -> str:
    """R1-C110 D4: the languages under the root that codemap does not read, named in the rules block.
    Names only, never counts: a count would turn the block "outdated" on every new file."""
    if root is None:
        return ""
    from codemap.advise import detect_languages
    # Shell scripts are glue, not a code graph anyone asks codemap about: naming them is noise.
    langs = sorted(k for k in detect_languages(root) if k not in ("python", "shell"))
    return f"; this repository also has {', '.join(langs)}, which it does not read" if langs else ""


def mcp_entry(ctx: dict, pin: list[str]) -> str:
    args = shlex.split(render(template("mcp_claude.args"), ctx))
    return canon_json(json.dumps({"command": pin[0], "args": [*pin[1:], *args]}))


def claude_hooks(ctx: dict) -> str:
    return canon_json(render(template("claude_hooks.json"), ctx))


def git_hooks_dir(root: Path) -> Path | None:
    try:
        out = subprocess.run(["git", "rev-parse", "--git-path", "hooks"], cwd=root,
                             capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    p = Path(out.stdout.strip())
    return p if p.is_absolute() else root / p


@dataclass
class Item:
    key: str
    art: Artifact
    content: str
    canonical: bool = False      # compare as canonical JSON


def items(root: Path, st: dict, pin: list[str], codemap_version: str) -> tuple[list[Item], list[str]]:
    """The artifacts this repository's options call for, with their rendered content; plus skip notes."""
    ctx = context(st, pin, codemap_version, root)
    opts = st.get("options", {})
    out: list[Item] = []
    notes: list[str] = []
    out.append(Item("agents", MarkdownRegion("agents", root / ctx["agents_file"]),
                    render(template("agents_block.md"), ctx)))
    mcp = JsonKey("mcp", root / ".mcp.json")
    mcp.recorded = (st.get("artifacts", {}).get("mcp") or {}).get("sha256")
    out.append(Item("mcp", mcp, mcp_entry(ctx, pin), canonical=True))
    if opts.get("codex"):
        out.append(Item("codex", TomlRegion("codex", root / ".codex" / "config.toml"),
                        render(template("codex_region.toml"), ctx)))
    if opts.get("hook", True):
        hooks = git_hooks_dir(root)
        if hooks is None:
            notes.append("post-commit hook skipped: not a git repository")
        else:
            art = WholeFile("hook", hooks / "post-commit")
            art.marker, art.mode, art.alt = HOOK_MARK, 0o755, root / HOOK_ALT
            out.append(Item("hook", art, render(template("post-commit.sh"), ctx)))
    if opts.get("claude_hooks"):
        out.append(Item("claude_hooks", ClaudeHooks("claude_hooks", root / ".claude" / "settings.json"),
                        claude_hooks(ctx), canonical=True))
    ci = opts.get("ci")
    if ci in ("github", "gitlab"):
        path = (root / ".github" / "workflows" / "codemap.yml" if ci == "github"
                else root / ".gitlab" / "codemap-ci.yml")
        art = WholeFile("ci", path)
        art.marker = CI_MARK
        out.append(Item("ci", art, render(template(
            "github-workflow.yml" if ci == "github" else "gitlab-ci.yml"), ctx)))
    return out, notes


# --------------------------------------------------------------------------- classification

@dataclass
class Outcome:
    key: str
    path: str
    status: str                  # current | created | updated | outdated | edited | foreign | missing
    #                              | foreign→alt | overwritten
    attention: bool = False
    detail: list[str] = field(default_factory=list)


def _same(cur: str | None, new: str, canonical: bool) -> bool:
    if cur is None:
        return False
    return (canon_json(cur) == canon_json(new)) if canonical else cur == new


def _diff(cur: str, new: str, path: str) -> list[str]:
    lines = list(difflib.unified_diff(cur.splitlines(), new.splitlines(), f"{path} (now)",
                                      f"{path} (devkit)", lineterm="", n=1))
    return lines[:40] + ([f"… {len(lines) - 40} more diff line(s)"] if len(lines) > 40 else [])


def process(root: Path, st: dict, it: Item, *, write: bool, force: bool) -> Outcome:
    art, new = it.art, it.art.normalize(it.content)
    rel = str(art.path.relative_to(root)) if art.path.is_relative_to(root) else str(art.path)
    recorded = (st.get("artifacts", {}).get(it.key) or {}).get("sha256")
    cur = art.current()

    def do(status: str, attention: bool = False, detail=None, path: Path | None = None) -> Outcome:
        target = path or art.path
        if write:
            if path is None:
                art.write(new)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(new, encoding="utf-8")
                target.chmod(0o755)
            st.setdefault("artifacts", {})[it.key if path is None else it.key + "@alt"] = {
                "path": str(target.relative_to(root)) if target.is_relative_to(root) else str(target),
                "sha256": sha(new)}
        return Outcome(it.key, str(target.relative_to(root)) if target.is_relative_to(root) else str(target),
                       status, attention, detail or [])

    if art.foreign():
        if force:
            return do("overwritten", detail=["a foreign artifact was replaced (--force)"])
        alt = art.alternative()
        if alt is not None:
            alt_cur = alt.read_text(encoding="utf-8") if alt.is_file() else None
            o = (do("foreign→alt", True, path=alt) if alt_cur != new or not write else
                 Outcome(it.key, str(alt.relative_to(root)), "foreign→alt", True))
            o.detail = [f"{rel} belongs to someone else and was not touched; the devkit's version is "
                        f"{alt.relative_to(root)} — call it from the existing hook: "
                        f"`\"$(git rev-parse --show-toplevel)/{alt.relative_to(root)}\"`"]
            return o
        return Outcome(it.key, rel, "foreign", True,
                       [f"{rel} has a `codemap` entry the devkit did not write; not touched "
                        "(`--force` replaces it)" if it.key == "mcp" else
                        f"{rel} is not the devkit's; not touched (`--force` replaces it)"])
    if cur is None:
        return do("created" if write else "missing", attention=not write)
    if recorded is None or sha(cur) != recorded:
        if _same(cur, new, it.canonical):
            if write:
                st.setdefault("artifacts", {})[it.key] = {"path": rel, "sha256": sha(cur)}
            return Outcome(it.key, rel, "current")
        if force:
            return do("overwritten", detail=["a hand edit was replaced (--force)"])
        return Outcome(it.key, rel, "edited", True,
                       ["edited by hand since the devkit wrote it; kept (`--force` rewrites it):",
                        *_diff(cur, new, rel)])
    if _same(cur, new, it.canonical):
        return Outcome(it.key, rel, "current")
    return do("updated") if write else Outcome(it.key, rel, "outdated", True)


# --------------------------------------------------------------------------- commands

def _ensure_gitignore(root: Path, write: bool) -> bool:
    p = root / ".gitignore"
    text = p.read_text(encoding="utf-8") if p.is_file() else ""
    if any(ln.strip() in (GITIGNORE_LINE, ".codemap", "/.codemap/", "/.codemap") for ln in text.splitlines()):
        return False
    if write:
        sep = "" if not text or text.endswith("\n") else "\n"
        p.write_text(text + sep + GITIGNORE_LINE + "\n", encoding="utf-8")
    return True


def _report(title: str, outcomes: list[Outcome], notes: list[str]) -> None:
    print(f"# {title}\n")
    for o in outcomes:
        mark = "!" if o.attention else " "
        print(f"{mark} {LABELS.get(o.key, o.key):<28} {o.path:<34} {o.status}")
    for o in outcomes:
        for d in o.detail:
            print(f"    {d}")
    for n in notes:
        print(f"  {n}")


def _build_graph(root: Path, st: dict, pin: list[str]) -> tuple[bool, str]:
    graph = root / st.get("graph", GRAPH)
    graph.parent.mkdir(parents=True, exist_ok=True)
    cmd = [*pin, "build", st["package"], *shlex.split(build_args(st)), "-o", str(graph)]
    r = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
    return r.returncode == 0, (r.stderr or "").strip()[-2000:]


def _query(root: Path, st: dict):
    from codemap import store
    from codemap.query import Query
    return Query(store.load(str(root / st.get("graph", GRAPH))))


def _contract(root: Path, st: dict, *, ratchet: bool, dry_run: bool, notes: list[str]) -> None:
    from codemap.arch import layer_pairs
    from codemap.devkit.ratchet import RatchetError, edit_region, starter_flags
    graph = root / st.get("graph", GRAPH)
    has_table = (root / "codemap.toml").is_file() and any(
        ln.strip() == "[architecture]"
        for ln in (root / "codemap.toml").read_text(encoding="utf-8").splitlines())
    if has_table and not ratchet:
        notes.append("codemap.toml already has `[architecture]`: left as it is "
                     "(`codemap devkit ratchet` adds the `allowed` region to it)")
        return
    if not graph.is_file():
        notes.append("contract not written: no graph (`--no-build`); run `codemap devkit ratchet` after a build")
        return
    q = _query(root, st)
    used = sorted(layer_pairs(q))
    try:
        res = edit_region(root, used, create_table_flags=None if has_table else starter_flags(q),
                          package_name=Path(st["package"]).name, graph=st.get("graph", GRAPH),
                          dry_run=dry_run)
    except RatchetError as exc:
        notes.append(f"contract not edited: {exc}")
        return
    what = "starter contract written" if res.created_table else "`allowed` region written"
    notes.append(f"codemap.toml: {what} — {len(used)} layer pair(s) allowed as of this graph")


def _choose_agents_file(root: Path, given: str | None) -> str:
    if given:
        return given
    if (root / "AGENTS.md").is_file():
        return "AGENTS.md"
    if (root / "CLAUDE.md").is_file():
        return "CLAUDE.md"
    return "AGENTS.md"


def init(root: Path, *, package: str, consumers: list[str], docs: list[str], agents_file: str | None,
         claude_hooks: bool, codex: bool, ci: str | None, hook: bool, build: bool, ratchet: bool,
         dry_run: bool, force: bool) -> int:
    root = root.resolve()
    st = load_state(root)
    if st is not None:
        print(f"The devkit is already installed here (v{st.get('devkit_version')}); running `update` with the "
              "options given now added to the recorded ones.\n")
        opts = st.setdefault("options", {})
        opts["claude_hooks"] = opts.get("claude_hooks") or claude_hooks
        opts["codex"] = opts.get("codex") or codex
        opts["ci"] = ci or opts.get("ci")
        return update(root, force=force, repin=False, dry_run=dry_run, _state=st)
    for p, what in [(package, "--package"), *((c, "--consumer") for c in consumers),
                    *((d, "--docs") for d in docs)]:
        if not (root / p).is_dir():
            print(f"error: {what} {p}: no such directory under {root}", file=sys.stderr)
            return 2
    pin = running_pin()
    if any(any(ch.isspace() for ch in part) for part in pin):
        print(f"error: the codemap executable path contains whitespace ({pin}); the hook cannot run it safely",
              file=sys.stderr)
        return 2
    version = _version()
    st = {"devkit_version": DEVKIT_VERSION, "written_by": version, "package": package.rstrip("/"),
          "consumers": consumers, "docs": docs, "graph": GRAPH,
          "agents_file": _choose_agents_file(root, agents_file),
          "options": {"hook": hook, "claude_hooks": claude_hooks, "codex": codex, "ci": ci},
          "artifacts": {}}
    notes: list[str] = []
    graph = root / GRAPH
    if build and not graph.is_file() and not dry_run:
        ok, err = _build_graph(root, st, pin)
        notes.append("graph built (fast tier; the post-commit hook builds --deep)" if ok else
                     f"graph build FAILED — {err.splitlines()[-1] if err else 'no message'}")
    _contract(root, st, ratchet=ratchet, dry_run=dry_run, notes=notes)
    if _ensure_gitignore(root, write=not dry_run):
        notes.append(".gitignore: `.codemap/` added (graphs and the hooks' digest are local)")
    its, skip = items(root, st, pin, version)
    notes += skip
    outcomes = [process(root, st, it, write=not dry_run, force=force) for it in its]
    if any(o.key == "mcp" and o.status == "created" for o in outcomes):
        notes.append(".mcp.json names the codemap executable by its absolute path on this machine "
                     f"({pin[0]}); whether to commit it is this project's decision")
    if graph.is_file() and not dry_run:
        from codemap.devkit.hooks import index
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            index(root)
    if not dry_run:
        save_state(root, st)
        notes.append(f"{STATE} written — commit it: it records the devkit version and what the devkit wrote")
    _report(f"codemap devkit v{DEVKIT_VERSION} — init{' (dry run)' if dry_run else ''}", outcomes, notes)
    return 1 if any(o.attention for o in outcomes) else 0


def update(root: Path, *, force: bool, repin: bool, dry_run: bool, _state: dict | None = None) -> int:
    root = root.resolve()
    st = _state if _state is not None else load_state(root)
    if st is None:
        print(f"error: no devkit here ({STATE} not found) — run `codemap devkit init --package <path>`",
              file=sys.stderr)
        return 2
    pin, version = _pin_and_version(root, st, repin)
    notes: list[str] = []
    its, skip = items(root, st, pin, version)
    notes += skip
    outcomes = [process(root, st, it, write=not dry_run, force=force) for it in its]
    if not dry_run:
        st["devkit_version"] = DEVKIT_VERSION
        st["written_by"] = _version()
        save_state(root, st)
    if repin:
        notes.append(f"re-pinned to {shlex.join(pin)} (codemap {version})")
    _report(f"codemap devkit v{DEVKIT_VERSION} — update{' (dry run)' if dry_run else ''}", outcomes, notes)
    return 1 if any(o.attention for o in outcomes) else 0


def _pin_and_version(root: Path, st: dict, repin: bool) -> tuple[list[str], str]:
    """Keep the project's pin unless asked to move it (D2): from `.mcp.json`, else this codemap."""
    if not repin:
        entry = JsonKey("mcp", root / ".mcp.json").entry()
        recorded = (st.get("artifacts", {}).get("mcp") or {}).get("sha256")
        pin = pin_from_mcp(entry) if entry is not None and recorded is not None else None
        if pin:
            ci = root / ".github" / "workflows" / "codemap.yml"
            gl = root / ".gitlab" / "codemap-ci.yml"
            ver = None
            for f in (ci, gl):
                if f.is_file():
                    import re
                    m = re.search(r"codmap==([\w.\-+]+)", f.read_text(encoding="utf-8"))
                    if m:
                        ver = m.group(1)
            return pin, ver or pin_version(pin) or _version()
    return running_pin(), _version()


def status(root: Path, fmt: str = "text") -> int:
    from codemap.devkit.hooks import currency_line
    root = root.resolve()
    st = load_state(root)
    if st is None:
        if fmt == "json":
            print(json.dumps({"installed": False}))
        else:
            print(f"No devkit here ({STATE} not found) — `codemap devkit init --package <path>` installs it.")
        return 1
    pin, version = _pin_and_version(root, st, repin=False)
    its, notes = items(root, st, pin, version)
    outcomes = [process(root, st, it, write=False, force=False) for it in its]
    installed = st.get("devkit_version")
    behind = installed != DEVKIT_VERSION
    pv = pin_version(pin)
    mcp_ok = pin_has_mcp(pin)
    info = [f"devkit: v{installed} in this repository, v{DEVKIT_VERSION} in the installed codemap "
            f"({_version()})" + (" — `codemap devkit update`" if behind else ""),
            f"pin: {shlex.join(pin)} → codemap {pv or 'not runnable'}"
            + ("" if pv is None or pv == _version() else f" (the installed codemap is {_version()}; "
               "moving the pin is this project's decision: `codemap devkit update --repin`)"),
            f"graph: {currency_line(root, st)}"]
    if mcp_ok is False:
        info.append("MCP: the pinned interpreter cannot import `mcp` — `serve --mcp` will not start; "
                    "install the extra: `pip install 'codmap[mcp]'`")
    attention = behind or any(o.attention for o in outcomes) or pv is None or mcp_ok is False
    if fmt == "json":
        print(json.dumps({"installed": True, "devkit_version": installed,
                          "devkit_available": DEVKIT_VERSION, "pin": pin, "pin_version": pv,
                          "mcp_importable": mcp_ok,
                          "artifacts": [{"key": o.key, "path": o.path, "status": o.status} for o in outcomes],
                          "needs_attention": attention}, indent=2))
    else:
        _report("codemap devkit — status", outcomes, notes)
        print()
        for ln in info:
            print(f"  {ln}")
    return 1 if attention else 0
