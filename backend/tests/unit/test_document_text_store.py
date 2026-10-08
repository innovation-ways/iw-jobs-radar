"""The in-memory holder of extracted CV text (ADR-010): bounded, expiring, never persisted."""

from datetime import UTC, datetime, timedelta

from jobs_radar.services.document_store import DocumentTextStore

T0 = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


def test_text_is_returned_until_it_expires() -> None:
    clock = Clock()
    store = DocumentTextStore(ttl=timedelta(minutes=30), clock=clock)
    store.put(1, "cv text")
    assert store.get(1) == "cv text"
    clock.now = T0 + timedelta(minutes=31)
    assert store.get(1) is None and len(store) == 0


def test_the_oldest_text_is_dropped_when_the_store_is_full() -> None:
    store = DocumentTextStore(max_items=2, clock=Clock())
    for document_id in (1, 2, 3):
        store.put(document_id, f"text {document_id}")
    assert store.get(1) is None and store.get(2) == "text 2" and store.get(3) == "text 3"


def test_text_can_be_discarded_and_the_store_never_shows_it() -> None:
    store = DocumentTextStore(clock=Clock())
    store.put(1, "secret cv")
    assert "secret cv" not in repr(store)
    store.discard(1)
    assert store.get(1) is None
    store.discard(99)  # unknown ids are ignored
