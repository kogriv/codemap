"""A tiny keyed registry — the dispatch table codemap reads statically."""


class Reg:
    _things = {}

    @classmethod
    def register_thing(cls, name):
        def deco(c):
            cls._things[name] = c
            return c
        return deco

    @classmethod
    def get_thing(cls, name):
        return cls._things[name]()
