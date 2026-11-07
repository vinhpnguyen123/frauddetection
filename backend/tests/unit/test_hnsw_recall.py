from uuid import uuid4

from scripts.hnsw_recall import recall


def test_recall_is_the_share_of_exact_hits_found() -> None:
    a, b, c = uuid4(), uuid4(), uuid4()
    assert recall({a, b}, {a, c}) == 0.5
    assert recall({a}, {a}) == 1.0
    assert recall(set(), set()) == 1.0
