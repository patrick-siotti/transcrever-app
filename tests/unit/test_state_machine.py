import pytest

from transcrever_app.server.worker.state_machine import (
    ALLOWED_TRANSITIONS,
    JobStatus,
    can_transition,
)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (JobStatus.QUEUED, JobStatus.PREPARING),
        (JobStatus.TRANSCRIBING, JobStatus.DIARIZING),
        (JobStatus.EXPORTING, JobStatus.COMPLETED),
        (JobStatus.FAILED, JobStatus.QUEUED),
    ],
)
def test_expected_state_transitions_are_allowed(current: JobStatus, target: JobStatus) -> None:
    assert can_transition(current, target)


def test_terminal_states_have_no_automatic_transitions() -> None:
    assert ALLOWED_TRANSITIONS[JobStatus.COMPLETED] == frozenset()
    assert ALLOWED_TRANSITIONS[JobStatus.CANCELLED] == frozenset()


def test_invalid_transition_is_rejected() -> None:
    assert not can_transition(JobStatus.QUEUED, JobStatus.COMPLETED)
