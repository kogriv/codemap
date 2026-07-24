"""codemap — static code-graph builder.

Pipeline: Extract (griffe) -> Build (neutral model) -> Store (JSON) -> Serve (reports).
See DESIGN.md.
"""

from codemap.model import Edge, Graph, Node

__all__ = ["Graph", "Node", "Edge"]
__version__ = "0.0.1"
