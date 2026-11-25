"""
Grid of plots, one per pair of scans, with a checkbox to include each pair in the average
"""
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Signal

from mmg_toolbox.xas import SpectraContainer
from ..common import PlotCanvas, popout, tool_button, button
from ..style import CURRENT, row
from .analysis import Pair
from .draw import draw_pair

CELL_WIDTH = 380
ALL = 'All conditions'


class PairCell(QtWidgets.QFrame):
    """Plot of one pair: processed spectra above, difference below"""
    includeChanged = Signal()

    def __init__(self, pair: Pair, parent=None):
        super().__init__(parent, objectName='card')
        self.pair = pair
        self.include = QtWidgets.QCheckBox(pair.label(), checked=pair.include)
        self.include.setToolTip('Include this pair in the average')
        self.include.toggled.connect(self._toggled)
        warnings = pair.warnings()
        warning = QtWidgets.QLabel('⚠' if warnings else '', toolTip='\n'.join(warnings))
        self.plot = PlotCanvas(self, nrows=2, toolbar=False, sharex=True, height_ratios=[2, 1])
        self.plot.setMinimumHeight(260)
        self.setMaximumHeight(560)
        self.plot.canvas.mpl_connect('button_press_event', lambda e: e.dblclick and self.popout())
        self.plot.setToolTip('Double-click to enlarge')
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 6)
        layout.setSpacing(2)
        layout.addLayout(row(self.include, warning, None, tool_button('⤢', self.popout, 'Open in a new window')))
        layout.addWidget(self.plot)
        self.processed, self.error, self.mode, self.background = None, '', '', False

    def _toggled(self, checked: bool):
        self.pair.include = checked
        self.redraw()
        self.includeChanged.emit()

    def set_include(self, include: bool):
        """Change the checkbox without emitting includeChanged"""
        self.include.blockSignals(True)
        self.include.setChecked(include)
        self.include.blockSignals(False)
        self.pair.include = include
        self.redraw()

    def draw(self, processed: dict[int, SpectraContainer], errors: dict[int, str], mode: str, background: bool):
        self.processed = processed[id(self.pair.scan1)], processed[id(self.pair.scan2)]
        self.error = errors.get(id(self.pair.scan1)) or errors.get(id(self.pair.scan2))
        self.mode, self.background = mode, background
        self.redraw()

    def redraw(self):
        """Draw the pair, faded if it is not included in the average"""
        if self.processed is None:
            return
        self.plot.clear()
        try:
            if self.error:
                raise ValueError(self.error)
            draw_pair(self.plot.axes, *self.processed, self.mode, self.background, 1.0 if self.pair.include else 0.25)
        except Exception as e:
            self.plot.ax.text(0.5, 0.5, f"Processing failed:\n{e}", ha='center', va='center', wrap=True,
                              transform=self.plot.ax.transAxes, color=CURRENT['muted'], fontsize=8)
        self.plot.style_axes()
        self.plot.draw()

    def popout(self):
        scans, mode, background = self.processed, self.mode, self.background
        popout(f"Pair {self.pair.label()} | {self.pair.condition()}",
               lambda axes: draw_pair(axes, *scans, mode, background), nrows=2, sharex=True, height_ratios=[2, 1])


class PairGrid(QtWidgets.QWidget):
    """
    Scrollable grid of PairCells, with as many columns as fit the width.
    The condition filter shows only pairs measured at one temperature and field.
    """
    includeChanged = Signal()
    conditionChanged = Signal()
    backgroundChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cells: list[PairCell] = []
        self.condition = QtWidgets.QComboBox(toolTip='Only show and average pairs measured at one condition',
                                             minimumContentsLength=12,
                                             sizeAdjustPolicy=QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.condition.currentTextChanged.connect(self._condition_changed)
        self.background = QtWidgets.QCheckBox('Show background')
        self.background.toggled.connect(lambda *_: self.backgroundChanged.emit())
        self.summary = QtWidgets.QLabel(objectName='muted')
        self.inner = QtWidgets.QWidget()
        self.layout_grid = QtWidgets.QGridLayout(self.inner)
        self.layout_grid.setContentsMargins(0, 0, 0, 0)
        self.layout_grid.setAlignment(Qt.AlignTop)
        self.scroll = QtWidgets.QScrollArea(widgetResizable=True, frameShape=QtWidgets.QFrame.NoFrame)
        self.scroll.setWidget(self.inner)
        self.empty = QtWidgets.QLabel('Load scans, then use Auto-pair or Add selected pair to compare scans here.',
                                      objectName='muted', alignment=Qt.AlignCenter, wordWrap=True)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(row(QtWidgets.QLabel('Condition'), self.condition, stretch=1))
        layout.addLayout(row(button('Include all', lambda: self.include_all(True), self),
                             button('None', lambda: self.include_all(False), self), self.background, None,
                             self.summary))
        layout.addWidget(self.empty)
        layout.addWidget(self.scroll, stretch=1)
        self._columns = 0

    def set_pairs(self, pairs: list[Pair]):
        for cell in self.cells:
            cell.deleteLater()
        self.cells = [PairCell(pair, self.inner) for pair in pairs]
        for cell in self.cells:
            cell.includeChanged.connect(self._include_changed)
        conditions = list(dict.fromkeys(pair.condition() for pair in pairs))
        current = self.condition.currentText()
        self.condition.blockSignals(True)
        self.condition.clear()
        self.condition.addItems([ALL] + conditions if len(conditions) > 1 else conditions)
        if current in conditions:
            self.condition.setCurrentText(current)
        elif len(conditions) > 1:
            self.condition.setCurrentIndex(1)  # start with the first condition rather than mixing them
        self.condition.blockSignals(False)
        self.empty.setHidden(bool(pairs))
        self._columns = 0
        self._layout()
        self._update_summary()

    def draw(self, processed: dict, errors: dict, mode: str):
        for cell in self.cells:
            cell.draw(processed, errors, mode, self.background.isChecked())

    def active_pairs(self) -> list[Pair]:
        """Pairs measured at the selected condition"""
        condition = self.condition.currentText()
        return [cell.pair for cell in self.cells if condition in (ALL, cell.pair.condition())]

    def include_all(self, include: bool):
        """Include or exclude every pair at the selected condition"""
        active = self.active_pairs()
        for cell in self.cells:
            if cell.pair in active and cell.pair.include != include:
                cell.set_include(include)
        self._include_changed()

    def show_pair(self, index: int):
        if 0 <= index < len(self.cells):
            cell = self.cells[index]
            if cell.isHidden():
                self.condition.setCurrentText(ALL if self.condition.findText(ALL) >= 0 else cell.pair.condition())
            self.scroll.ensureWidgetVisible(cell)

    def _include_changed(self):
        self._update_summary()
        self.includeChanged.emit()

    def _condition_changed(self):
        self._columns = 0
        self._layout()
        self._update_summary()
        self.conditionChanged.emit()

    def _update_summary(self):
        active = self.active_pairs()
        self.summary.setText(f"{sum(p.include for p in active)} of {len(active)} pairs included")

    def _layout(self):
        columns = max(1, self.scroll.viewport().width() // CELL_WIDTH)
        if columns == self._columns:
            return
        self._columns = columns
        for cell in self.cells:
            self.layout_grid.removeWidget(cell)
        active = self.active_pairs()
        visible = [cell for cell in self.cells if cell.pair in active]
        for cell in self.cells:
            cell.setHidden(cell not in visible)
        for n, cell in enumerate(visible):
            self.layout_grid.addWidget(cell, n // columns, n % columns)
        for column in range(self.layout_grid.columnCount()):
            self.layout_grid.setColumnStretch(column, 1 if column < columns else 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout()
