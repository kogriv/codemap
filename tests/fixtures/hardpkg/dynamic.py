def _body(self):
    return _dyn_helper()

def _dyn_helper():
    return 2

Generated = type("Generated", (object,), {"body": _body})

def make_class(name):
    class Inner:
        def go(self):
            return _dyn_helper()
    Inner.__name__ = name
    return Inner
