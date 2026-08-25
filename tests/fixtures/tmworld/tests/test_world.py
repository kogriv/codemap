from tmpkg.core import Engine, entry


def test_entry():
    assert entry(1) == 1


def test_entry_again():
    assert entry(2) == 2


def helper_not_a_test():
    return entry(3)


class TestEngine:
    def test_run(self):
        assert Engine().run() == 1
