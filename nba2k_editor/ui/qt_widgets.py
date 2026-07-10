from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QSize, Qt
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


def configure_combo_box(combo: QComboBox) -> QComboBox:
    combo.setMaxVisibleItems(COMBO_BOX_MAX_VISIBLE_ITEMS)
    combo.view().setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
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
    def __init__(self, selection_callback: Callable[[set[str], str | None], None] | None = None) -> None:
        super().__init__()
        self.setObjectName("RecordList")
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._selection_callback = selection_callback
        self._last_selected_labels: set[str] = set()
        self.itemSelectionChanged.connect(self._emit_selection)

    def set_labels(self, labels: list[str], selected: set[str] | None = None) -> None:
        selected = selected or set()
        label_set = set(labels)
        self.blockSignals(True)
        self.clear()
        for label in labels:
            item = QListWidgetItem(label)
            item.setSizeHint(QSize(0, 24))
            item.setSelected(label in selected)
            self.addItem(item)
        self._last_selected_labels = {label for label in selected if label in label_set}
        self.blockSignals(False)

    def selected_labels(self) -> set[str]:
        return {item.text() for item in self.selectedItems()}

    def current_label(self) -> str | None:
        item = self.currentItem()
        return None if item is None else item.text()

    def _emit_selection(self) -> None:
        if self._selection_callback is None:
            return
        selected = self.selected_labels()
        if selected == self._last_selected_labels:
            return
        self._last_selected_labels = set(selected)
        current = self.current_label()
        self._selection_callback(set(selected), current if current in selected else None)


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
