"""A frozen copy of a live target, for the tests that must not move under them.

``test_determinism_*`` builds a package twice and compares the bytes. Pointed at the
**live** bquant checkout it does not measure codemap's determinism — it measures whether
anybody edited bquant between the two calls, and it goes red when somebody does. That
happened on 2026-08-24 (R1-C22-f1) and cost an hour: a red determinism test whose cause
was the input moving, not the tool being nondeterministic, with nothing in the artifact
able to tell the two apart.

That confusion is the whole subject of R1-C25 — so the lesson is applied here too: a
determinism test freezes its input, or it is measuring the wrong thing. One copy per
test process, shared by every caller.
"""

from __future__ import annotations

import atexit
import shutil
import tempfile
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=8)
def frozen(src: str | Path) -> Path:
    """A snapshot of ``src`` that cannot change while the test runs."""
    src = Path(src)
    tmp = Path(tempfile.mkdtemp(prefix="codemap-frozen-"))
    atexit.register(shutil.rmtree, tmp, ignore_errors=True)
    dst = tmp / src.name
    shutil.copytree(src, dst)
    return dst
