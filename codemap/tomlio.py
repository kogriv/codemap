"""One place that reads TOML, and one rule about failing (R1-C27).

Three loaders — the architecture contract (`arch.py`), the integration gate
(`integrations/gate.py`) and the dead-code whitelist (`serve/audit.py`) — read the same
``codemap.toml``. Each had grown its own copy of:

    try:
        import tomllib
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, ModuleNotFoundError):
        return <empty>

which collapses three different situations into one silent empty result, and every caller
then renders that as *the user configured nothing*. It is not the same thing:

- **absent** — the user configured nothing. A legitimate, common answer.
- **unparseable** — the user configured something and it has a typo. `TOMLDecodeError`
  subclasses `ValueError`, so one missing ``]`` turned ``codemap check`` from *exit 2, 14
  imports point up the layer stack* into *"nothing to enforce"*, exit 0. A typo painted a
  CI gate green.
- **no parser** — the interpreter cannot do this class of work at all (``tomllib`` is
  stdlib from 3.11). Not per-file and not per-user: every TOML feature, off, everywhere.

The tolerance is deliberate and stays: reading a broken file must never raise, and must
never wedge a plain build. What changes is that the tool says which of the three happened,
so a caller can report *"I could not read your contract"* instead of *"you have no
contract"* — the same rule as `risk:"unknown"` never being rendered as `risk:"none"`.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["read_toml"]


def read_toml(path: Path) -> tuple[dict, str | None]:
    """Parse a TOML file → ``(data, error)``. Never raises.

    ``error`` is ``None`` when there is nothing to report — including when the file simply
    is not there, which is an answer and not a failure. Otherwise ``data`` is ``{}`` and
    ``error`` is a human-readable reason naming the file and, where the parser gives one,
    the position of the problem.
    """
    if not path.is_file():
        return {}, None
    try:
        import tomllib
    except ModuleNotFoundError:                      # pragma: no cover - 3.10 and older
        return {}, (f"cannot read {path.name}: this Python has no `tomllib` "
                    f"(added to the standard library in 3.11)")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return {}, f"cannot read {path.name}: {exc}"
    try:
        return tomllib.loads(text), None
    except ValueError as exc:                        # TOMLDecodeError subclasses ValueError
        return {}, f"{path.name} is not valid TOML: {exc}"
