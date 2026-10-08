"""The inbox state machine (LLD section 3): every action from every state."""

import pytest

from jobs_radar.domain.enums import InboxAction, InboxState
from jobs_radar.domain.inbox import InvalidTransitionError, next_state, undo_action

S = InboxState
A = InboxAction

# (action, source states that are allowed, target state) straight from the table in LLD section 3.
TABLE = [
    (A.OPEN, {S.UNREAD, S.UPDATED_UNREAD}, S.READ),
    (A.MARK_UNREAD, {S.READ, S.IGNORED, S.ARCHIVED, S.APPLIED}, S.UNREAD),
    (A.MATERIAL_UPDATE, {S.UNREAD, S.READ, S.UPDATED_UNREAD}, S.UPDATED_UNREAD),
    (A.IGNORE, {S.UNREAD, S.READ, S.UPDATED_UNREAD}, S.IGNORED),
    (A.RESTORE, {S.IGNORED, S.ARCHIVED, S.APPLIED}, S.READ),
    (A.ARCHIVE, {S.UNREAD, S.READ, S.UPDATED_UNREAD, S.IGNORED}, S.ARCHIVED),
    (A.RECORD_APPLICATION, {S.UNREAD, S.READ, S.UPDATED_UNREAD}, S.APPLIED),
]


@pytest.mark.parametrize(
    ("action", "allowed", "target"), TABLE, ids=[row[0].value for row in TABLE]
)
def test_each_action_is_allowed_exactly_from_its_listed_states(
    action: InboxAction, allowed: set[InboxState], target: InboxState
) -> None:
    for state in InboxState:
        if state in allowed:
            assert next_state(state, action) is target
        else:
            with pytest.raises(InvalidTransitionError) as error:
                next_state(state, action)
            assert state.value in str(error.value) and action.value in str(error.value)


@pytest.mark.parametrize("state", list(InboxState))
@pytest.mark.parametrize("action", [A.SHORTLIST, A.UNSHORTLIST])
def test_shortlisting_never_changes_the_state(state: InboxState, action: InboxAction) -> None:
    assert next_state(state, action) is state


def test_surfacing_is_not_a_user_transition() -> None:
    for state in InboxState:
        with pytest.raises(InvalidTransitionError):
            next_state(state, A.SURFACE_NEW)


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        (A.OPEN, A.MARK_UNREAD),
        (A.IGNORE, A.RESTORE),
        (A.ARCHIVE, A.RESTORE),
        (A.RECORD_APPLICATION, A.RESTORE),
        (A.SHORTLIST, A.UNSHORTLIST),
        (A.UNSHORTLIST, A.SHORTLIST),
        (A.MARK_UNREAD, None),
        (A.RESTORE, None),
    ],
)
def test_the_undo_action_for_each_action(action: InboxAction, expected: InboxAction | None) -> None:
    assert undo_action(action) is expected
