from typing import TYPE_CHECKING

try:
    import ujson as _json
except ImportError:
    import json as _json

if TYPE_CHECKING:
    from .meta import Base

def dump(o) -> "Base":
    return _json.dumps(o)
