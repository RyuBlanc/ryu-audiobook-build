"""Paint-stable refreshes for native pages backed by local files or catalogues."""
from __future__ import annotations

from functools import wraps
from typing import Callable, TypeVar, cast

from PySide6.QtWidgets import QScrollBar, QWidget


F = TypeVar("F", bound=Callable[..., object])


def stable_view_refresh(method: F) -> F:
    """Avoid intermediate paints and preserve child-scroll positions during refresh.

    Catalogue-backed refreshes often update labels and rebuild lists/tables in one
    synchronous operation. Disabling page updates prevents an empty or half-populated
    intermediate frame. The previous state and scroll positions are restored even if
    the data read raises an exception.
    """
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        if not isinstance(self, QWidget):
            return method(self, *args, **kwargs)

        updates_enabled = self.updatesEnabled()
        scroll_positions = [(bar, bar.value()) for bar in self.findChildren(QScrollBar)]
        self.setUpdatesEnabled(False)
        try:
            return method(self, *args, **kwargs)
        finally:
            self.setUpdatesEnabled(updates_enabled)
            for bar, value in scroll_positions:
                try:
                    bar.setValue(min(max(value, bar.minimum()), bar.maximum()))
                except RuntimeError:
                    # A refresh may replace a nested widget and delete its old bar.
                    continue
            if updates_enabled:
                self.update()

    return cast(F, wrapped)
