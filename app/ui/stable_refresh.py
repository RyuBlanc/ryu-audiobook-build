"""Paint-stable refreshes for native pages backed by local files or catalogues."""
from __future__ import annotations

from functools import wraps
from typing import Callable, TypeVar, cast

from PySide6.QtWidgets import QComboBox, QScrollBar, QWidget


F = TypeVar("F", bound=Callable[..., object])


def sync_combo_items_in_place(
    combo: QComboBox,
    rows: list[tuple[str, object]],
    selected_data: object = None,
) -> None:
    """Synchronize dropdown entries without clearing unchanged rows or flashing blank."""
    was_blocked = combo.blockSignals(True)
    updates_were_enabled = combo.updatesEnabled()
    if updates_were_enabled:
        combo.setUpdatesEnabled(False)
    try:
        for index, (label, data) in enumerate(rows):
            if index < combo.count():
                if combo.itemText(index) != label:
                    combo.setItemText(index, label)
                if combo.itemData(index) != data:
                    combo.setItemData(index, data)
            else:
                combo.addItem(label, data)

        while combo.count() > len(rows):
            combo.removeItem(combo.count() - 1)

        selected_index = combo.findData(selected_data) if selected_data is not None else -1
        if selected_index < 0 and rows:
            selected_index = 0
        combo.setCurrentIndex(selected_index)
    finally:
        combo.blockSignals(was_blocked)
        if updates_were_enabled:
            combo.setUpdatesEnabled(True)
            combo.update()


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
