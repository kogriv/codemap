"""Deep-only: a call on a local variable whose type comes from a local
constructor. ``w = Widget(); w.act()`` needs local type inference (jedi, the
deep tier) — the fast ast tier leaves ``w.act()`` unresolved by design.
"""


class Widget:
    def act(self):
        return 1


def run():
    w = Widget()
    return w.act()
