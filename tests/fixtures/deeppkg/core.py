"""Engine defined here; called through a local variable elsewhere."""


class Engine:
    def run(self) -> int:
        return self._step()

    def _step(self) -> int:
        return 1
