"""Maps a panel's logical width to one of three layout states.

These are design targets, not rigid web breakpoints — widgets query
``BreakpointManager.current`` and adjust layout (column count, hidden
detail panes) rather than every widget re-deriving thresholds itself.
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QObject, Signal

from corona_doctor.ui.design.metrics import Breakpoint


class LayoutState(str, Enum):
    COMPACT = "compact"
    STANDARD = "standard"
    EXPANDED = "expanded"


def state_for_width(width: int) -> LayoutState:
    if width < Breakpoint.COMPACT_MAX:
        return LayoutState.COMPACT
    if width < Breakpoint.STANDARD_MAX:
        return LayoutState.STANDARD
    return LayoutState.EXPANDED


class BreakpointManager(QObject):
    """Tracks the current layout state and emits a signal on change.

    Call :meth:`update_width` from the panel's ``resizeEvent``. Consumers
    connect to ``state_changed`` instead of polling width themselves.
    """

    state_changed = Signal(str)  # LayoutState.value

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._current = LayoutState.STANDARD

    @property
    def current(self) -> LayoutState:
        return self._current

    def update_width(self, width: int) -> None:
        new_state = state_for_width(width)
        if new_state != self._current:
            self._current = new_state
            self.state_changed.emit(new_state.value)
