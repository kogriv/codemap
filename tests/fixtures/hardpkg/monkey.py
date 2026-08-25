from . import meta

def _replacement():
    return 99

def patch():
    meta._helper_meta = _replacement
