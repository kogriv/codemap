"""codemap — static code-graph builder.

Pipeline: Extract (griffe) -> Build (neutral model) -> Store (JSON) -> Serve (reports).
See DESIGN.md.
"""

from codemap.model import Edge, Graph, Node
from codemap.provenance import tool_version

__all__ = ["Graph", "Node", "Edge"]

#: Read from the installed distribution rather than written down, because it had been
#: written down and had drifted: this said ``0.0.2`` while `codmap` 0.0.3 was on PyPI, so
#: every SCIP index and ctags file stamped a version the package had not been for a
#: release. `provenance` was already asking `importlib.metadata`, which is why graphs were
#: right and these two exports were not — one source now, and nothing left to drift.
__version__ = tool_version() or "0+unknown"
