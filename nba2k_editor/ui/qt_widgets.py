from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QPoint, QSize, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


COMBO_BOX_MAX_VISIBLE_ITEMS = 12
COMBO_BOX_POPUP_ROW_HEIGHT = 24
COMBO_BOX_POPUP_MAX_HEIGHT = COMBO_BOX_MAX_VISIBLE_ITEMS * COMBO_BOX_POPUP_ROW_HEIGHT + 4


def configure_combo_box(combo: QComboBox) -> QComboBox:
    combo.setMaxVisibleItems(COMBO_BOX_MAX_VISIBLE_ITEMS)
    view = combo.view()
    view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    view.setMaximumHeight(COMBO_BOX_POPUP_MAX_HEIGHT)
    return combo


def configure_table(table: QTableWidget, *, editable: bool = False) -> None:
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    table.setAlternatingRowColors(False)
    table.setShowGrid(True)
    table.verticalHeader().setDefaultSectionSize(22)
    table.verticalHeader().setMinimumSectionSize(20)
    table.horizontalHeader().setStretchLastSection(True)
    if not editable:
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)


def configure_output_text(text: QTextEdit) -> None:
    text.setObjectName("DataOutput")
    text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
    text.setFont(QFont("Consolas", 10))


class NavButton(QPushButton):
    def __init__(self, label: str, callback: Callable[[], None]) -> None:
        super().__init__(label)
        self.setObjectName("NavButton")
        self.setCheckable(True)
        self.setMinimumHeight(25)
        self.clicked.connect(callback)


class OperationDialog(QDialog):
    def __init__(self, cancel_callback: Callable[[], None] | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Operation Progress")
        layout = QVBoxLayout(self)
        self.message = QLabel("")
        self.progress = QProgressBar()
        self.cancel_button = QPushButton("Cancel")
        if cancel_callback is not None:
            self.cancel_button.clicked.connect(cancel_callback)
        layout.addWidget(self.message)
        layout.addWidget(self.progress)
        layout.addWidget(self.cancel_button)

    def update_progress(self, message: str, current: int, total: int, *, done: bool = False) -> None:
        self.message.setText(message)
        if total <= 0:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, total)
            self.progress.setValue(max(0, min(total, current)))
        self.cancel_button.setEnabled(not done)

    def show(self) -> None:
        if __import__("os").environ.get("QT_QPA_PLATFORM") == "offscreen":
            return
        super().show()


class RecordListWidget(QListWidget):
    def __init__(
        self,
        selection_callback: Callable[[set[int], int | None], None] | None = None,
        context_callback: Callable[[int, QPoint], None] | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName("RecordList")
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._selection_callback = selection_callback
        self._context_callback = context_callback
        self._last_selected_indexes: set[int] = set()
        self.itemSelectionChanged.connect(self._emit_selection)

    def set_records(self, records: list[tuple[int, str]], selected: set[int] | None = None) -> None:
        selected = selected or set()
        available_indexes = {index for index, _label in records}
        self.blockSignals(True)
        self.clear()
        for index, label in records:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setSizeHint(QSize(0, 24))
            self.addItem(item)
            item.setSelected(index in selected)
        self._last_selected_indexes = selected & available_indexes
        self.blockSignals(False)

    def selected_indexes(self) -> set[int]:
        return {int(item.data(Qt.ItemDataRole.UserRole)) for item in self.selectedItems()}

    def current_index(self) -> int | None:
        item = self.currentItem()
        return None if item is None else int(item.data(Qt.ItemDataRole.UserRole))

    def _emit_selection(self) -> None:
        if self._selection_callback is None:
            return
        selected = self.selected_indexes()
        if selected == self._last_selected_indexes:
            return
        self._last_selected_indexes = set(selected)
        current = self.current_index()
        self._selection_callback(set(selected), current if current in selected else None)

    def contextMenuEvent(self, event) -> None:
        item = self.itemAt(event.pos())
        if item is None or self._context_callback is None:
            super().contextMenuEvent(event)
            return
        if not item.isSelected():
            self.clearSelection()
            item.setSelected(True)
            self.setCurrentItem(item)
        self._context_callback(int(item.data(Qt.ItemDataRole.UserRole)), event.globalPos())
        event.accept()


class DetailRow(QWidget):
    def __init__(self, label: str, value: str = "") -> None:
        super().__init__()
        self.setObjectName("DetailRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(label)
        self.value = QLabel(value)
        self.value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.label, 0)
        layout.addWidget(self.value, 1)

    def set_value(self, value: object) -> None:
        self.value.setText(str(value))


class EditableFieldRow(QWidget):
    def __init__(self, label: str, current_value: str, dirty_callback: Callable[[str], None], row_key: str, options: list[str] | None = None) -> None:
        super().__init__()
        self.setObjectName("EditableFieldRow")
        self.row_key = row_key
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(label)
        self.current = QLineEdit(current_value)
        self.current.setReadOnly(True)
        option_values = [str(option) for option in (options or [])]
        if option_values:
            combo = configure_combo_box(QComboBox())
            combo.addItems(option_values)
            if current_value not in option_values:
                combo.insertItem(0, current_value)
            combo.setCurrentText(current_value)
            combo.currentTextChanged.connect(lambda _text: dirty_callback(row_key))
            self.new_value = combo
        else:
            edit = QLineEdit(current_value)
            edit.textEdited.connect(lambda _text: dirty_callback(row_key))
            self.new_value = edit
        self.status = QLabel("")
        layout.addWidget(self.label, 2)
        layout.addWidget(self.current, 1)
        layout.addWidget(self.new_value, 1)
        layout.addWidget(self.status, 1)

    def value_text(self) -> str:
        if isinstance(self.new_value, QComboBox):
            return self.new_value.currentText()
        return self.new_value.text()
