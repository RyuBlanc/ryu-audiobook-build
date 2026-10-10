from __future__ import annotations

from pathlib import Path
import json

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QInputDialog, QLineEdit, QMenu, QPushButton


BUILTIN_GENRES = [
    "Audiobook", "Fiction", "Fantasy", "Adventure", "Action", "Romance",
    "Drama", "Comedy", "Mystery", "Thriller", "Horror", "Science Fiction",
    "Slice of Life", "Young Adult", "Coming of Age", "Light Novel", "Isekai",
    "Supernatural", "Anime", "Anime • Action", "Anime • Adventure",
    "Anime • Comedy", "Anime • Drama", "Anime • Fantasy", "Anime • Harem",
    "Anime • Isekai", "Anime • Romance", "Anime • Slice of Life", "Cartoon",
    "Cartoon • Adventure", "Cartoon • Comedy", "Cartoon • Fantasy",
    "Cartoon • Sci-Fi", "Cartoon • Slice of Life",
]


def _catalog_path() -> Path:
    from app.core.paths import settings_root
    return settings_root() / "genres.json"


def load_genres() -> list[str]:
    values = list(BUILTIN_GENRES)
    path = _catalog_path()
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                values.extend(str(v).strip() for v in payload if str(v).strip())
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
    result, seen = [], set()
    for value in values:
        key = value.casefold()
        if key not in seen:
            result.append(value)
            seen.add(key)
    return result


def save_custom_genre(value: str) -> None:
    value = str(value or "").strip()
    if not value:
        return
    path = _catalog_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    custom = []
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                custom = [str(v).strip() for v in payload if str(v).strip()]
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
    if value.casefold() not in {v.casefold() for v in custom}:
        custom.append(value)
        path.write_text(json.dumps(custom, ensure_ascii=False, indent=2), encoding="utf-8")


class GenrePicker(QPushButton):
    def __init__(self, parent=None):
        super().__init__("Select genres…", parent)
        self._selected: list[str] = []
        self.setMinimumHeight(34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._open_menu)

    def set_value(self, value: str) -> None:
        catalog = load_genres()
        values = [p.strip() for p in str(value or "").replace(",", ";").split(";") if p.strip()]
        self._selected = []
        for item in values:
            match = next((g for g in catalog if g.casefold() == item.casefold()), None)
            self._selected.append(match or item)
        self._refresh()

    def value(self) -> str:
        return "; ".join(self._selected)

    def _refresh(self) -> None:
        self.setText(", ".join(self._selected) if self._selected else "Select genres…")
        self.setToolTip(self.value() or "Choose one or more genres")

    def _open_menu(self) -> None:
        menu = QMenu(self)
        for genre in load_genres():
            action = QAction(genre, menu)
            action.setCheckable(True)
            action.setChecked(any(x.casefold() == genre.casefold() for x in self._selected))
            action.toggled.connect(lambda checked, name=genre: self._toggle(name, checked))
            menu.addAction(action)
        menu.addSeparator()
        add_action = QAction("＋ Add new genre…", menu)
        add_action.triggered.connect(self._add_new)
        menu.addAction(add_action)
        menu.exec(self.mapToGlobal(self.rect().bottomLeft()))

    def _toggle(self, genre: str, checked: bool) -> None:
        self._selected = [x for x in self._selected if x.casefold() != genre.casefold()]
        if checked:
            self._selected.append(genre)
        self._refresh()

    def _add_new(self) -> None:
        value, ok = QInputDialog.getText(self, "Add Genre", "New genre name:", QLineEdit.EchoMode.Normal)
        value = value.strip()
        if ok and value:
            save_custom_genre(value)
            if not any(x.casefold() == value.casefold() for x in self._selected):
                self._selected.append(value)
            self._refresh()
