"""
Editor for the chain of processing steps applied to every spectrum before averaging
"""
from PySide6 import QtWidgets
from PySide6.QtCore import Signal
from PySide6.QtGui import QBrush, QColor

from mmg_toolbox.xas.spectra import BACKGROUND_FUNCTIONS
from ..common import button
from ..style import CURRENT, row
from .analysis import Step, PROCESSES, BACKGROUND, AUTO, default_steps


def _text(value) -> str:
    return '' if value is AUTO else str(value)


def _value(text: str):
    text = text.strip()
    if not text:
        return AUTO
    try:
        return float(text)
    except ValueError:
        return text


class ChainEditor(QtWidgets.QWidget):
    """
    Detection mode and an ordered list of processing steps.
    Selecting a step shows its parameters; empty parameters are filled in by mmg_toolbox.
    Emits changed() whenever the mode or any step changes.
    """
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.steps: list[Step] = default_steps()
        self.mode = QtWidgets.QComboBox(toolTip='Detection mode')
        self.mode.currentTextChanged.connect(lambda *_: self.changed.emit())
        self.list = QtWidgets.QListWidget()
        self.list.currentRowChanged.connect(self._show_parameters)
        self.list.setMaximumHeight(140)

        add_menu = QtWidgets.QMenu(self)
        for method, description in PROCESSES.items():
            action = add_menu.addAction(method.replace('_', ' '))
            action.setToolTip(description)
            action.triggered.connect(lambda *_, m=method: self.add(Step(m)))
        backgrounds = add_menu.addMenu('remove background')
        for name in BACKGROUND_FUNCTIONS:
            backgrounds.addAction(name).triggered.connect(lambda *_, n=name: self.add(Step(BACKGROUND, {'name': n})))
        add_menu.setToolTipsVisible(True)
        add = QtWidgets.QToolButton(text='Add step', popupMode=QtWidgets.QToolButton.InstantPopup)
        add.setMenu(add_menu)

        self.parameters = QtWidgets.QFormLayout()
        self.parameters.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        self.description = QtWidgets.QLabel(wordWrap=True, objectName='muted')

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(row(QtWidgets.QLabel('Mode'), self.mode, None))
        layout.addWidget(self.list)
        layout.addLayout(row(add, button('↑', lambda: self.move(-1), self), button('↓', lambda: self.move(1), self),
                             button('Remove', self.remove, self), None, button('Reset', self.reset, self)))
        layout.addWidget(self.description)
        layout.addLayout(self.parameters)
        self.refresh()

    def set_modes(self, modes: list[str], default: str = ''):
        current = self.mode.currentText() or default
        self.mode.blockSignals(True)
        self.mode.clear()
        self.mode.addItems(modes)
        if current in modes:
            self.mode.setCurrentText(current)
        self.mode.blockSignals(False)

    def current_mode(self) -> str:
        return self.mode.currentText()

    def add(self, step: Step):
        n = self.list.currentRow() + 1 if self.list.currentRow() >= 0 else len(self.steps)
        self.steps.insert(n, step)
        self.refresh(n)
        self.changed.emit()

    def remove(self):
        n = self.list.currentRow()
        if n >= 0:
            del self.steps[n]
            self.refresh(min(n, len(self.steps) - 1))
            self.changed.emit()

    def move(self, direction: int):
        n = self.list.currentRow()
        m = n + direction
        if n >= 0 and 0 <= m < len(self.steps):
            self.steps[n], self.steps[m] = self.steps[m], self.steps[n]
            self.refresh(m)
            self.changed.emit()

    def reset(self):
        self.steps[:] = default_steps()
        self.refresh(0)
        self.changed.emit()

    def set_steps(self, steps: list[Step]):
        self.steps[:] = [s.copy() for s in steps]
        self.refresh(0)
        self.changed.emit()

    def refresh(self, current: int = 0):
        self.list.blockSignals(True)
        self.list.clear()
        for n, step in enumerate(self.steps, start=1):
            item = QtWidgets.QListWidgetItem(f"{n}. {step.label()}")
            item.setToolTip(step.description())
            self.list.addItem(item)
        self.list.blockSignals(False)
        self.list.setCurrentRow(current if self.steps else -1)
        self._show_parameters(self.list.currentRow())

    def set_error(self, index: int | None, message: str = ''):
        """Mark the step that failed (or clear the marks if index is None)"""
        for n in range(self.list.count()):
            item = self.list.item(n)
            failed = n == index
            item.setForeground(QBrush(QColor('#dc2626' if failed else CURRENT['text'])))
            item.setToolTip(f"Error: {message}" if failed else self.steps[n].description())

    def _show_parameters(self, n: int):
        while self.parameters.rowCount():
            self.parameters.removeRow(0)
        if not 0 <= n < len(self.steps):
            self.description.setText('')
            return
        step = self.steps[n]
        self.description.setText(step.description())
        for name, value in step.kwargs.items():
            if name == 'name' and step.method == BACKGROUND:
                field = QtWidgets.QComboBox()
                field.addItems(list(BACKGROUND_FUNCTIONS))
                field.setCurrentText(value)
                field.currentTextChanged.connect(lambda text, i=n: self._set_background(i, text))
            else:
                field = QtWidgets.QLineEdit(_text(value), placeholderText='auto')
                field.editingFinished.connect(lambda i=n, k=name, f=field: self._set_value(i, k, f.text()))
            self.parameters.addRow(QtWidgets.QLabel(name, objectName='muted'), field)

    def _set_value(self, n: int, name: str, text: str):
        value = _value(text)
        if self.steps[n].kwargs.get(name) != value:
            self.steps[n].kwargs[name] = value
            self.list.item(n).setText(f"{n + 1}. {self.steps[n].label()}")
            self.changed.emit()

    def _set_background(self, n: int, name: str):
        self.steps[n] = Step(BACKGROUND, {'name': name})
        self.refresh(n)
        self.changed.emit()
