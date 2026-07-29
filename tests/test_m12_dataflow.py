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
    assert {"signal", "flag", "meta"} <= set(q.columns())


def test_embedded_data_excluded():
    # column nodes must not explode from literal datasets — the pass skips them.
    g = extract(FIX)
    assert all(n.kind != "column" or n.id.startswith("column:") for n in g.nodes.values())


def test_deterministic():
    from codemap import store
    assert store.dumps(extract(FIX)) == store.dumps(extract(FIX))
