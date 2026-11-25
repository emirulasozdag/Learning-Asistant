"""Shared deadline for synchronous LLM work in one tutor turn."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from time import monotonic

_deadline_at: ContextVar[float | None] = ContextVar("tutor_turn_deadline", default=None)

DEADLINE_ERROR_DETAIL = "Yanıt süresi doldu; lütfen tekrar dene."


class TutorTurnDeadlineExceeded(TimeoutError):
    """The tutor turn exhausted its shared time budget."""


@contextmanager
def use_tutor_turn_deadline(deadline_at: float) -> Iterator[None]:
    current = _deadline_at.get()
    if current is not None:
        deadline_at = min(deadline_at, current)
    token = _deadline_at.set(deadline_at)
    try:
        yield
    finally:
        _deadline_at.reset(token)


@contextmanager
def tutor_turn_deadline(timeout_s: float) -> Iterator[None]:
    with use_tutor_turn_deadline(monotonic() + timeout_s):
        yield


def request_timeout(configured_timeout_s: float) -> tuple[float, bool]:
    """Cap a provider request to the remaining turn budget, if one is active."""
    deadline = _deadline_at.get()
    if deadline is None:
        return configured_timeout_s, False
    remaining_s = deadline - monotonic()
    if remaining_s <= 0:
        raise TutorTurnDeadlineExceeded
    return min(configured_timeout_s, remaining_s), True


def request_timed_out_at_deadline(configured_timeout_s: float, started_at: float) -> bool:
    """Distinguish a deadline-capped timeout from an earlier provider timeout."""
    deadline = _deadline_at.get()
    if deadline is None:
        return False

    budget_at_start = deadline - started_at
    if budget_at_start <= 0:
        return True
    if budget_at_start > configured_timeout_s:
        return False

    tolerance_s = min(0.1, budget_at_start * 0.01)
    return monotonic() >= deadline - tolerance_s


def check_tutor_turn_deadline() -> None:
    deadline = _deadline_at.get()
    if deadline is not None and monotonic() >= deadline:
        raise TutorTurnDeadlineExceeded
