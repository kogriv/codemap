"""Factory: string name -> instance (the seam that hides the concrete type)."""

from dispatchpkg.registry import Reg


def create_thing(name):
    return Reg.get_thing(name)
