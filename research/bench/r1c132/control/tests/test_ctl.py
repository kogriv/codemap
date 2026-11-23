import ctl


def test_outer():
    assert ctl.outer() == 6


def test_make_e():
    assert ctl.make_e().v == 1


def test_pick():
    assert ctl.pick() == 1


def test_only_a():
    assert ctl.only_a() == 1
