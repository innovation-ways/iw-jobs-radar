"""The inbox state machine (LLD section 3). Pure: a table of legal transitions.

``is_shortlisted`` is a separate flag, so shortlisting and un-shortlisting never change the state.
Every other action has a fixed set of allowed source states and one target state.
"""

from jobs_radar.domain.enums import InboxAction, InboxState

_S = InboxState
_A = InboxAction

_TRANSITIONS: dict[InboxAction, tuple[frozenset[InboxState], InboxState]] = {
    _A.OPEN: (frozenset({_S.UNREAD, _S.UPDATED_UNREAD}), _S.READ),
    _A.MARK_UNREAD: (frozenset({_S.READ, _S.IGNORED, _S.ARCHIVED, _S.APPLIED}), _S.UNREAD),
    _A.MATERIAL_UPDATE: (frozenset({_S.UNREAD, _S.READ, _S.UPDATED_UNREAD}), _S.UPDATED_UNREAD),
    _A.IGNORE: (frozenset({_S.UNREAD, _S.READ, _S.UPDATED_UNREAD}), _S.IGNORED),
    _A.RESTORE: (frozenset({_S.IGNORED, _S.ARCHIVED, _S.APPLIED}), _S.READ),
    _A.ARCHIVE: (frozenset({_S.UNREAD, _S.READ, _S.UPDATED_UNREAD, _S.IGNORED}), _S.ARCHIVED),
    _A.RECORD_APPLICATION: (frozenset({_S.UNREAD, _S.READ, _S.UPDATED_UNREAD}), _S.APPLIED),
}

# What the interface offers to take an action back (restore returns to "read"; the owner may then
# mark the item unread).
_UNDO: dict[InboxAction, InboxAction] = {
    _A.OPEN: _A.MARK_UNREAD,
    _A.IGNORE: _A.RESTORE,
    _A.ARCHIVE: _A.RESTORE,
    _A.RECORD_APPLICATION: _A.RESTORE,
    _A.SHORTLIST: _A.UNSHORTLIST,
    _A.UNSHORTLIST: _A.SHORTLIST,
}


class InvalidTransitionError(ValueError):
    """The action is not allowed from the item's current state."""


def next_state(state: InboxState, action: InboxAction) -> InboxState:
    """Return the state after ``action`` from ``state``.

    Raises:
        InvalidTransitionError: if the action is not allowed from ``state``.
    """
    if action in (_A.SHORTLIST, _A.UNSHORTLIST):
        return state
    rule = _TRANSITIONS.get(action)
    if rule is None or state not in rule[0]:
        msg = f"'{action.value}' is not allowed while the item is {state.value}."
        raise InvalidTransitionError(msg)
    return rule[1]


def undo_action(action: InboxAction) -> InboxAction | None:
    """Return the action that takes ``action`` back, if there is one."""
    return _UNDO.get(action)
