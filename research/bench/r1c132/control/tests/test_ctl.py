import ctl


def test_outer():
    assert ctl.outer() == 6


def test_make_e():
    assert ctl.make_e().v == 1


def test_pick():
    assert ctl.pick() == 1


def test_only_a():
    assert ctl.only_a() == 1


def test_generators():
    g = ctl.use_gen()           # called in use_gen, first run here in the test
    assert list(g) == [4]
    assert list(ctl.G().items()) == [1]
