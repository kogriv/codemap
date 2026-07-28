"""Two implementations registered by string key (no shared base — like bquant)."""

from dispatchpkg.registry import Reg


@Reg.register_thing('alpha')
class Alpha:
    def run(self) -> int:
        return 1


@Reg.register_thing('beta')
class Beta:
    def run(self) -> int:
        return 2
