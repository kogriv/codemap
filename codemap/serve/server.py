"""Line-delimited JSON stdio loop over a warm ``Session`` (DESIGN §14.4, M3.1).

Transport for the resident process: one JSON request per input line, one JSON
response per output line. Zero startup per call — the graph is loaded once by the
caller and reused for the life of the process. Transport-neutral by design: an
MCP adapter can wrap the same ``Session.handle`` later without touching this loop.

    $ codemap serve --graph graph.json
    {"op": "query", "args": {"name": "analyze_zones"}}
    {"ok": true, "result": {...}}
    {"op": "column", "args": {"name": "macd_hist"}}
    {"ok": true, "result": {"writes": [...], "reads": [...]}}
"""

from __future__ import annotations

import json
import sys

from codemap.serve.session import Session


def serve_stdio(session: Session, stdin=None, stdout=None) -> int:
    """Read JSON requests line-by-line, write JSON responses. EOF ends the loop.

    A blank line is skipped; a malformed line yields an error response rather than
    crashing the resident process. Returns 0 at EOF.
    """
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            response = {"ok": False, "error": f"invalid JSON: {exc}"}
        else:
            response = session.handle(request)
        stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        stdout.flush()
    return 0
