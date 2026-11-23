import contextlib

import pytest

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


def test_closures_and_generator_expressions():
    assert ctl.run_rules([ctl.make_rule()]) == [5]
    assert list(ctl.lazy_h()) == [0, 1]          # consumed here, after lazy_h returned


def test_context_manager_after_a_foreign_one():
    @contextlib.contextmanager
    def foreign():
        yield 0
    with foreign():
        pass
    assert ctl.use_cm() == 6


def test_a_patched_class_first(monkeypatch):
    class Other(Exception):
        pass
    monkeypatch.setattr(ctl, "Err", Other)
    with pytest.raises(Other):
        ctl.raise_err()


def test_the_package_class_after():
    with pytest.raises(ctl.Err):
        ctl.raise_err()


def test_an_object_whose_getattr_raises():
    class Broken:                    # rich's test_broken_getattr: the tracer must not look attributes up on it
        def __getattr__(self, name):
            1 / 0
    assert ctl.run_rules([ctl.make_rule_with(Broken())]) == [5]
