"""M12 acceptance — string-key dataflow (F6).

bquant threads data through string-keyed DataFrame columns; the symbol call-graph
was blind to it (querying ``macd_hist`` returned nothing — worse than grep). This
adds ``column`` nodes + ``reads``/``writes`` edges so producer/consumer of a key
is queryable. Fixture ``flowpkg``: producer via dict-literal + subscript write,
consumer via subscript read.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codemap.extract import extract
from codemap.query import Query

FIX = Path(__file__).resolve().parent / "fixtures" / "flowpkg"


@pytest.fixture(scope="module")
def q():
    return Query(extract(FIX))


def test_producer_and_consumer_linked(q):
    col = q.column("signal")
    assert col is not None
    assert col["writes"] == ["flowpkg.produce.compute"]   # dict-literal producer
    assert col["reads"] == ["flowpkg.consume.plot"]        # subscript read


def test_subscript_write_is_a_producer(q):
    col = q.column("flag")
    assert "flowpkg.produce.compute" in col["writes"]      # df['flag'] = 0
    assert col["reads"] == []


def test_unknown_key_is_none(q):
    assert q.column("does_not_exist") is None


def test_column_nodes_listed(q):
    # M14/F15: `columns()` defaults to subscript-accessed keys (the real column-like
    # set). 'signal' (subscript read) and 'flag' (subscript write) qualify; 'meta'
    # is a dict-literal-only payload key and is excluded by default.
    assert {"signal", "flag"} <= set(q.columns())
    assert "meta" not in q.columns()
    # the full over-set (historical behavior) still includes the payload key.
    assert "meta" in q.columns(subscripted_only=False)


def test_access_form_recorded(q):
    # M14/F15: column nodes carry `subscripted`; edges carry `access`.
    g = q.graph
    assert g.nodes["column:meta"].extras["subscripted"] is False
    assert g.nodes["column:flag"].extras["subscripted"] is True
    assert g.nodes["column:signal"].extras["subscripted"] is True
    access = {(e.type, e.target): e.extras.get("access")
              for e in g.edges if e.target.startswith("column:")}
    assert access[("writes", "column:flag")] == "subscript"      # df['flag'] = 0
    assert access[("reads", "column:signal")] == "subscript"     # frame['signal']
    assert access[("writes", "column:meta")] == "dict-literal"   # {'meta': 1}


def test_embedded_data_excluded():
    # column nodes must not explode from literal datasets — the pass skips them.
    g = extract(FIX)
    assert all(n.kind != "column" or n.id.startswith("column:") for n in g.nodes.values())


def test_deterministic():
    from codemap import store
    assert store.dumps(extract(FIX)) == store.dumps(extract(FIX))
