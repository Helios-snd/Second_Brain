from app.assistant.deps import TurnRegistry
from tests.assistant._factories import make_passage


def test_register_and_lookup() -> None:
    registry = TurnRegistry()
    passage = make_passage()

    registry.register([passage])

    assert passage.chunk_id in registry
    assert registry.get(passage.chunk_id) is passage
    assert len(registry) == 1


def test_register_is_idempotent_and_keeps_first() -> None:
    registry = TurnRegistry()
    first = make_passage(text="first")
    same_id = make_passage(chunk_id=first.chunk_id, text="second")

    registry.register([first])
    registry.register([same_id])

    assert len(registry) == 1
    assert registry.get(first.chunk_id).text == "first"


def test_register_pulls_in_neighbors() -> None:
    neighbor = make_passage(text="neighbor")
    hit = make_passage(neighbors=[neighbor])

    registry = TurnRegistry()
    registry.register([hit])

    assert neighbor.chunk_id in registry
    assert len(registry) == 2


def test_unknown_chunk_is_not_contained() -> None:
    import uuid

    assert uuid.uuid4() not in TurnRegistry()
