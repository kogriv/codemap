"""Atomic file publication (R1-C124): a reader sees the old file or the new one, never a torn one.

Written to a temporary file in the target's directory (same filesystem, so the rename is atomic), flushed and
fsync'd, then ``os.replace``d over the target. A failure at any point before the rename leaves the target as it
was and removes the temporary file.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def write_bytes(path: str | Path, data: bytes) -> None:
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def write_text(path: str | Path, text: str) -> None:
    write_bytes(path, text.encode("utf-8"))
