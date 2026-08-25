_LAZY = {"lazy_thing": "hardpkg.meta:Impl"}

def __getattr__(name):
    if name in _LAZY:
        return _resolve(_LAZY[name])
    raise AttributeError(name)

def _resolve(spec):
    return spec

def __dir__():
    return sorted(_LAZY)
