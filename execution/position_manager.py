"""
Position state machine.

Valid states and allowed transitions are defined here.
The state machine is the single source of truth for what the bot
is currently doing; nothing else may change the state directly.
"""

from __future__ import annotations

import logging
from enum import Enum, auto

from utils.logging_config import log_event

logger = logging.getLogger(__name__)


class State(str, Enum):
    IDLE = "IDLE"
    CE_SIGNAL = "CE_SIGNAL"
    PE_SIGNAL = "PE_SIGNAL"
    ENTRY_PENDING = "ENTRY_PENDING"
    POSITION_OPEN = "POSITION_OPEN"
    EXIT_PENDING = "EXIT_PENDING"
    CLOSED = "CLOSED"
    ERROR = "ERROR"
    HALTED = "HALTED"


# Map: current_state -> allowed next states
_TRANSITIONS: dict[State, set[State]] = {
    State.IDLE: {State.CE_SIGNAL, State.PE_SIGNAL, State.ERROR, State.HALTED},
    State.CE_SIGNAL: {State.ENTRY_PENDING, State.IDLE, State.ERROR},
    State.PE_SIGNAL: {State.ENTRY_PENDING, State.IDLE, State.ERROR},
    State.ENTRY_PENDING: {State.POSITION_OPEN, State.IDLE, State.ERROR},
    State.POSITION_OPEN: {State.EXIT_PENDING, State.ERROR, State.HALTED},
    State.EXIT_PENDING: {State.CLOSED, State.ERROR, State.HALTED},
    State.CLOSED: {State.IDLE},
    State.ERROR: {State.IDLE, State.HALTED},
    State.HALTED: {State.IDLE},
}

# States in which new entries are blocked
_ENTRY_BLOCKED = {
    State.CE_SIGNAL,
    State.PE_SIGNAL,
    State.ENTRY_PENDING,
    State.POSITION_OPEN,
    State.EXIT_PENDING,
    State.ERROR,
    State.HALTED,
}


class StateMachine:
    def __init__(self) -> None:
        self._state = State.IDLE

    @property
    def state(self) -> State:
        return self._state

    def transition(self, new_state: State, reason: str = "") -> None:
        allowed = _TRANSITIONS.get(self._state, set())
        if new_state not in allowed:
            raise ValueError(
                f"Invalid transition {self._state} -> {new_state}. "
                f"Allowed: {allowed}"
            )
        log_event(
            logger,
            "STATE_TRANSITION",
            from_state=self._state.value,
            to_state=new_state.value,
            reason=reason,
        )
        self._state = new_state

    def can_enter(self) -> bool:
        return self._state == State.IDLE

    def is_entry_blocked(self) -> bool:
        return self._state in _ENTRY_BLOCKED

    def force_halt(self, reason: str = "") -> None:
        """Move to HALTED regardless of current state (safety escape)."""
        log_event(logger, "BOT_HALTED", reason=reason, current_state=self._state.value)
        self._state = State.HALTED
