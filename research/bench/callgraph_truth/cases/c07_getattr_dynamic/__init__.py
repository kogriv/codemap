"""Undecidable: dispatch through ``getattr`` on a runtime-computed name. No
sound static analyzer can resolve ``getattr(obj, name)()`` — ``name`` is data.
This is the dynamic-dispatch ceiling; the true edge run→handle is real but
statically unknowable.
"""


class Obj:
    def handle(self):
        return 1


def run(name):
    obj = Obj()
    return getattr(obj, name)()  # name == "handle" at runtime, but it is data
