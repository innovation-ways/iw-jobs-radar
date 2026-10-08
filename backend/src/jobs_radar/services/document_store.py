"""Holds extracted CV text in memory only, briefly (ADR-010, ADR-046).

The upload and the proposal request are two calls, but the original and its text must never be
stored. The text therefore lives in this process-local store for a short time (default 30 minutes,
at most a few documents) and is gone after a restart. It is never written to disk or logged.
"""

from collections import OrderedDict
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class DocumentTextStore:
    """A small expiring map from document id to extracted text."""

    def __init__(
        self,
        *,
        ttl: timedelta = timedelta(minutes=30),
        max_items: int = 5,
        clock: Clock = _utc_now,
    ) -> None:
        self._ttl = ttl
        self._max_items = max_items
        self._clock = clock
        self._items: OrderedDict[int, tuple[datetime, str]] = OrderedDict()

    def __len__(self) -> int:
        self._expire()
        return len(self._items)

    def __repr__(self) -> str:
        return f"DocumentTextStore(items={len(self._items)})"

    def _expire(self) -> None:
        now = self._clock()
        for document_id in [i for i, (at, _) in self._items.items() if at <= now - self._ttl]:
            del self._items[document_id]

    def put(self, document_id: int, text: str) -> None:
        """Keep ``text`` for ``document_id``; the oldest entry is dropped when full."""
        self._expire()
        self._items[document_id] = (self._clock(), text)
        self._items.move_to_end(document_id)
        while len(self._items) > self._max_items:
            self._items.popitem(last=False)

    def get(self, document_id: int) -> str | None:
        """Return the text, or ``None`` if it expired, was discarded or the process restarted."""
        self._expire()
        entry = self._items.get(document_id)
        return entry[1] if entry else None

    def discard(self, document_id: int) -> None:
        """Forget the text of a document."""
        self._items.pop(document_id, None)
