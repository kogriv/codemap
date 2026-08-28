"""The auto-loop: source changes → incremental rebuild → the server picks it up (M3.2).

Three of the four bricks were already here, and each was built because a specific
dishonesty showed up first:

- **M18** — the graph carries its age, so `stats` can say the map may be stale.
- **R1-C9** — `build --incremental` recomputes only the modules a change touched.
- **issue #3** — freshness describes the *served* snapshot and flags `stale: true` when
  the artifact on disk has moved past it; `reload` picks the new one up without a restart.

What was missing was glue, and glue only: something to notice the change and pull the
three together. This module is that, and it deliberately decides nothing on its own.

**What counts as a change is not this module's call.** It asks
:func:`codemap.scope.resolve_scope` — the same manifest a build records in its sidecar —
and compares ``scope_id``. So the watcher and the build agree by construction: no second
notion of "a relevant file", no include/exclude list to drift apart. Content hashes, not
mtimes, so `touch` is not a rebuild and a revert back to identical bytes is not either.

**Polling, not inotify.** A native-events watcher would need a dependency; codemap's cost
is a full `resolve_scope` per interval — every in-scope file read and hashed. Measured on
the R2 benchmark target (292 tracked ``*.py``/``*.md``, 4.7 MB): **median 50 ms** over 7
runs, i.e. ~5% of one core at the 1 s default. That is the honest price of hashing rather
than trusting mtimes, and it scales with tree size: on a much larger tree, raise
``--interval`` rather than assume it is free. The peer measurement that
made this worth building at all (native events, 2 s debounce, 121 ms to answer a query
about a symbol that did not exist before the edit) is in `research/tools/codegraph.md`.

**A broken tree still gets an honest graph, not a stale one.** Saving a file with a syntax
error rebuilds as usual: the module's symbols drop out and the R1-C21 diagnostic says
*"1 input file(s) produced no module (1 syntax) — anything those files define is missing,
not absent"*. Holding back the old graph would look kinder and would be a lie: it would
serve a symbol table for source that no longer exists, with nothing marking it. The next
save that parses restores it. A rebuild that genuinely *fails* (an unreadable tree, a
crash) is different — the previous graph stays, the failure is reported once per tree
version, and the loop retries rather than recording the failed version as done.

Two loops, one state machine, composed by the shell rather than by a framework:

    codemap watch ./pkg -o graph.json &          # source  → artifact
    codemap serve --graph graph.json --watch     # artifact → memory

Splitting them this way keeps the rebuild out of the resident process: a serving thread
that also extracts would compete with the queries it exists to answer, and a rebuild that
crashes would take the server with it. Run either half alone if that is what you need —
`watch` alone keeps a graph current for CI or for a cold `codemap query`; `serve --watch`
alone follows any external rebuild, including one you type by hand.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any


class DebouncedPoller:
    """Poll a cheap token; act once the token has stopped moving.

    ``probe`` returns any comparable token (a scope_id, an mtime); ``act`` is called with
    the settled token. Debounce is what makes this usable during real editing: a save on
    every keystroke, a `git checkout` touching 300 files, or a formatter rewriting a
    directory are one event, not three hundred — and acting mid-flight would rebuild a
    tree that no longer exists by the time the build finishes.

    The clock and sleep are injected so the state machine can be tested without waiting.
    """

    #: A change no larger than this many units is treated as "one save" and gets the
    #: quick window. Two, not one, because saving a module and its test together is the
    #: same human action — the pattern the peer this was taken from also settled on.
    QUICK_MAX = 2

    def __init__(self, probe: Callable[[], Any], act: Callable[[Any], Any], *,
                 interval: float = 1.0, debounce: float = 2.0,
                 quick_debounce: float | None = None,
                 size: Callable[[Any, Any], int | None] | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.probe, self.act = probe, act
        self.interval, self.debounce = interval, debounce
        # M3.2-f1: adaptive debounce, measured off CodeGraph (research/tools/codegraph.md).
        # A flat window taxes the common case — one file saved — for the burst that rarely
        # happens. `size(baseline, pending)` says how many units changed; a small change
        # settles on `quick_debounce`, a big one still coalesces on the full window. Size
        # unknown (None, or no `size` given) means the full window: the fast path is only
        # taken when the change is *known* to be small.
        self.quick_debounce = quick_debounce
        self.size = size
        self.clock, self.sleep = clock, sleep
        self.baseline = probe()
        self._pending: Any = None
        self._pending_since: float = 0.0
        self._pending_window: float = debounce
        self.acted = 0

    def _window_for(self, token: Any) -> float:
        """The debounce this pending change earns — computed once, when it is first seen."""
        if self.quick_debounce is None or self.size is None:
            return self.debounce
        try:
            n = self.size(self.baseline, token)
        except Exception:
            return self.debounce            # sizing must never break the loop
        if n is None or n > self.QUICK_MAX:
            return self.debounce
        return self.quick_debounce

    def tick(self) -> str:
        """One poll. ``quiet`` | ``settling`` | ``acted`` | ``act-failed`` | ``probe-failed``.

        A probe that raises is reported, not fatal: a tree mid-`git checkout` or a file
        deleted between listing and reading must not kill a loop whose whole job is to
        survive until the tree makes sense again.

        An ``act`` that returns ``False`` did **not** take effect, and the baseline is
        deliberately left where it was so the next tick retries. Advancing it would make
        the loop believe it had caught up — a server quietly serving the old graph after
        a failed reload is precisely the silent staleness this whole line of work exists
        to remove.
        """
        self.sleep(self.interval)
        try:
            token = self.probe()
        except Exception:
            return "probe-failed"
        if token == self.baseline:
            self._pending = None
            return "quiet"
        if token != self._pending:
            self._pending, self._pending_since = token, self.clock()
            self._pending_window = self._window_for(token)
            return "settling"
        if self.clock() - self._pending_since < self._pending_window:
            return "settling"
        outcome = self.act(token)
        self._pending = None
        if outcome is False:
            return "act-failed"
        self.baseline = token
        self.acted += 1
        return "acted"

    def run(self, *, cycles: int | None = None) -> int:
        """Tick until ``cycles`` are spent (``None`` = forever). Returns acts performed."""
        n = 0
        while cycles is None or n < cycles:
            self.tick()
            n += 1
        return self.acted


class ScopeProbe:
    """The tree's ``scope_id``, plus how many files changed between two of them.

    The id alone is enough to notice a change; the **count** is what lets the poller tell
    one save from a `git checkout` and pick its debounce accordingly (M3.2-f1). Both come
    from the same `resolve_scope` call, so sizing costs nothing extra — the manifests are
    already in hand, and `diff_scopes` is the build's own comparison, not a second one.

    Only the last two manifests are kept: the poller ever asks about the baseline and the
    change currently settling.
    """

    def __init__(self, path: str, *, consumers: tuple = (), docs: tuple = ()) -> None:
        self.path, self.consumers, self.docs = path, consumers, docs
        self._manifests: dict[str, dict] = {}

    def __call__(self) -> str:
        from codemap.scope import resolve_scope
        scope = resolve_scope(self.path, consumers=self.consumers, docs=self.docs)
        sid = scope["scope_id"]
        self._manifests[sid] = scope
        if len(self._manifests) > 3:        # baseline + pending + the one just read
            for k in list(self._manifests)[:-3]:
                del self._manifests[k]
        return sid

    def size(self, baseline: str, pending: str) -> int | None:
        """Files added + removed + changed between two scope_ids, or None if not known."""
        from codemap.scope import diff_scopes
        a, b = self._manifests.get(baseline), self._manifests.get(pending)
        if a is None or b is None:
            return None                      # the baseline predates this process
        d = diff_scopes(a, b)
        return len(d["added"]) + len(d["removed"]) + len(d["changed"])


def scope_probe(path: str, *, consumers: tuple = (), docs: tuple = ()) -> ScopeProbe:
    """A probe over the tree's scope_id — the build's own notion of what an input is."""
    return ScopeProbe(path, consumers=consumers, docs=docs)


def mtime_probe(graph_path: str) -> Callable[[], float | None]:
    """A probe for the artifact side: the mtime of the graph file, or None if absent.

    mtime is the right instrument *here* — the question is "has the file been rewritten
    since I loaded it", which is what `serve` already answers with `freshness.stale`.
    """
    import os

    def probe() -> float | None:
        try:
            return os.path.getmtime(graph_path)
        except OSError:
            return None

    return probe
