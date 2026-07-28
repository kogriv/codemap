"""Core engine — the symbol consumers depend on (blast-radius target)."""


class Engine:
    def run(self) -> int:
        return self._step()

    def _step(self) -> int:
        return 1


def helper() -> int:
    return 0
