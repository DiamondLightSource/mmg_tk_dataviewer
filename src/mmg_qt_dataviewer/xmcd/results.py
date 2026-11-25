"""
Right-hand panels: averaged spectra and dichroism, sum rules, and the series of results
"""
import numpy as np
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Signal

from ..common import PlotCanvas, popout, tool_button, button, monospace
from ..style import CURRENT, form, row, heading
from .analysis import Result, n_holes, series_table, SERIES_AXES
from .draw import draw_average, draw_sum_rules, draw_series, SERIES_PLOTS


def message(plot: PlotCanvas, text: str):
    plot.clear()
    plot.ax.text(0.5, 0.5, text, ha='center', va='center', wrap=True, transform=plot.ax.transAxes,
                 color=CURRENT['muted'])
    plot.draw()


class AveragePanel(QtWidgets.QWidget):
    """All the scans of each polarisation, both averages and the dichroism"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.result: Result | None = None
        self.info = QtWidgets.QLabel(objectName='muted', wordWrap=True)
        self.plot = PlotCanvas(self, nrows=2, ncols=2, sharex=True)
        self.plot.toolbar_row.addWidget(tool_button('⤢', self.popout, 'Open in a new window'))
        self.plot.canvas.mpl_connect('button_press_event', lambda e: e.dblclick and self.popout())
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.addWidget(self.info)
        layout.addWidget(self.plot, stretch=1)

    def update_result(self, result: Result | None, info: str = ''):
        self.result = result
        self.info.setText(info)
        if result is None:
            return message(self.plot, info or 'No pairs included')
        self.plot.clear()
        draw_average(self.plot.axes, result)
        self.plot.style_axes()
        self.plot.draw()

    def popout(self):
        if self.result:
            result = self.result
            popout(f"Average: {result.label()}", lambda axes: draw_average(axes, result), 2, 2, sharex=True)


class SumRulesPanel(QtWidgets.QWidget):
    """
    Sum rule analysis of the dichroism: element and oxidation state give the number of holes,
    the slider sets the energy separating the L3 and L2 (or M5 and M4) edges
    """
    addRequested = Signal()

    def __init__(self, actions: dict, parent=None):
        super().__init__(parent)
        self.result: Result | None = None
        self.element = QtWidgets.QLineEdit(placeholderText='e.g. Fe', maximumWidth=70)
        self.element.editingFinished.connect(self._element_changed)
        self.oxidation = QtWidgets.QSpinBox(minimum=-4, maximum=8, toolTip='Oxidation state, e.g. 3 for Fe3+')
        self.oxidation.valueChanged.connect(self._element_changed)
        self.holes = QtWidgets.QDoubleSpinBox(minimum=0.01, maximum=14, decimals=2, singleStep=0.1, value=1,
                                              toolTip='Number of holes, calculated from the element and oxidation '
                                                      'state by mmg_toolbox (d-band metals only), or enter a value')
        self.holes.valueChanged.connect(self.calculate)
        self.holes_note = QtWidgets.QLabel(objectName='muted', wordWrap=True)
        self.slider = QtWidgets.QSlider(Qt.Horizontal)
        self.slider.valueChanged.connect(self._slider_moved)
        self.split = QtWidgets.QDoubleSpinBox(decimals=2, singleStep=0.1, suffix=' eV', keyboardTracking=False)
        self.split.valueChanged.connect(self._split_changed)

        self.values = {name: heading('–', 1.4) for name in ('L', 'S', 'L/S')}
        values = QtWidgets.QHBoxLayout()
        for name, label in self.values.items():
            label.setMinimumWidth(90)
            box = QtWidgets.QVBoxLayout()
            box.addWidget(QtWidgets.QLabel(f"{name} (μB)" if name != 'L/S' else name, objectName='muted'))
            box.addWidget(label)
            values.addLayout(box)
        values.addStretch()

        self.plot = PlotCanvas(self, nrows=2, sharex=True)
        self.plot.toolbar_row.addWidget(tool_button('⤢', self.popout, 'Open in a new window'))
        self.plot.canvas.mpl_connect('button_press_event', self._clicked)
        self.plot.setToolTip('Click the dichroism to set the L3/L2 split energy, double-click to enlarge')
        self.report = QtWidgets.QPlainTextEdit(readOnly=True, font=monospace(), maximumHeight=130)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.addLayout(form(
            ('Element', row(self.element, QtWidgets.QLabel('Oxidation'), self.oxidation, None)),
            ('Holes', row(self.holes, self.holes_note, stretch=1)),
            ('L3/L2 split', row(self.slider, self.split, tool_button('↺', self.reset_split, 'Midpoint of the edges'),
                                stretch=0)),
        ))
        layout.addLayout(values)
        layout.addWidget(self.plot, stretch=1)
        layout.addWidget(self.report)
        layout.addLayout(row(button('Add to series', self.addRequested.emit, self, primary=True), None,
                             *(button(name, fn, self) for name, fn in actions.items())))

    def update_result(self, result: Result | None):
        previous, self.result = self.result, result
        if result is None:
            self.report.setPlainText('')
            return message(self.plot, 'No pairs included')
        energy = result.spectra.energy
        for widget in (self.slider, self.split):
            widget.blockSignals(True)
        self.slider.setRange(0, len(energy) - 1)
        self.split.setRange(float(energy.min()), float(energy.max()))
        for widget in (self.slider, self.split):
            widget.blockSignals(False)
        if previous is None or previous.metadata.element != result.metadata.element:
            self.element.setText(result.metadata.element)
            self._element_changed(calculate=False)
        if previous is None or previous.metadata.edge != result.metadata.edge or not self.split.value():
            self.reset_split()
        else:
            self.calculate()

    def _element_changed(self, *_, calculate: bool = True):
        holes = n_holes(self.element.text().strip(), self.oxidation.value())
        if holes is None:
            self.holes_note.setText(f"unknown for {self.element.text()}: enter n_holes")
        else:
            self.holes_note.setText(f"from {self.element.text()}{self.oxidation.value():+d}" if self.oxidation.value()
                                    else f"from neutral {self.element.text()}")
            self.holes.blockSignals(True)
            self.holes.setValue(holes)
            self.holes.blockSignals(False)
        if calculate:
            self.calculate()

    def reset_split(self):
        if self.result:
            self.set_split(self.result.default_split_energy())

    def set_split(self, energy: float):
        self.split.setValue(energy)  # calls _split_changed

    def _split_changed(self, energy: float):
        if self.result is None:
            return
        self.slider.blockSignals(True)
        self.slider.setValue(int(np.argmin(abs(self.result.spectra.energy - energy))))
        self.slider.blockSignals(False)
        self.calculate()

    def _slider_moved(self, index: int):
        if self.result is not None:
            self.split.setValue(float(self.result.spectra.energy[index]))

    def _clicked(self, event):
        if event.dblclick:
            self.popout()
        elif event.inaxes is self.plot.axes[1] and event.xdata is not None:
            self.set_split(event.xdata)

    def calculate(self, *_):
        result = self.result
        if result is None:
            return
        try:
            orbital, spin = result.sum_rules(self.holes.value(), self.split.value())
            self.values['L'].setText(f"{orbital:.3f}")
            self.values['S'].setText(f"{spin:.3f}")
            self.values['L/S'].setText(f"{orbital / spin:.3f}" if spin else '–')
            self.report.setPlainText(result.report())
        except Exception as e:
            self.report.setPlainText(f"Sum rules failed: {e}")
        self.plot.clear()
        draw_sum_rules(self.plot.axes, result, self.split.value())
        self.plot.style_axes()
        self.plot.draw()

    def popout(self):
        if self.result:
            result, split = self.result, self.split.value()
            popout(f"Sum rules: {result.label()}", lambda axes: draw_sum_rules(axes, result, split), 2, sharex=True)


class SeriesPanel(QtWidgets.QWidget):
    """Results added to the series, plotted against field or temperature"""
    COLUMNS = ['Result', 'B (T)', 'T (K)', 'holes', 'split (eV)', 'L', 'S', 'L/S']

    def __init__(self, results: list[Result], actions: dict, parent=None):
        super().__init__(parent)
        self.results = results  # shared with the window
        self.table = QtWidgets.QTableWidget(0, len(self.COLUMNS), alternatingRowColors=True)
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.itemChanged.connect(lambda *_: self.draw())
        self.x_axis = QtWidgets.QComboBox()
        self.x_axis.addItems(list(SERIES_AXES))
        self.kind = QtWidgets.QComboBox()
        self.kind.addItems(SERIES_PLOTS)
        self.energy = QtWidgets.QDoubleSpinBox(decimals=2, maximum=1e5, suffix=' eV', keyboardTracking=False,
                                               toolTip='Energy of the dichroism signal to plot')
        for widget in (self.x_axis, self.kind):
            widget.currentTextChanged.connect(lambda *_: self.draw())
        self.energy.valueChanged.connect(lambda *_: self.draw())
        self.plot = PlotCanvas(self)
        self.plot.toolbar_row.addWidget(tool_button('⤢', self.popout, 'Open in a new window'))
        self.plot.canvas.mpl_connect('button_press_event', lambda e: e.dblclick and self.popout())

        top = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(top)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.addWidget(self.table)
        layout.addLayout(row(button('Remove', self.remove, self), None,
                             *(button(name, fn, self) for name, fn in actions.items())))
        bottom = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(bottom)
        layout.setContentsMargins(0, 0, 0, 0)
        controls = QtWidgets.QGridLayout()
        controls.addWidget(QtWidgets.QLabel('Plot'), 0, 0)
        controls.addWidget(self.kind, 0, 1)
        controls.addWidget(self.energy, 0, 2)
        controls.addWidget(QtWidgets.QLabel('against'), 1, 0)
        controls.addWidget(self.x_axis, 1, 1)
        controls.setColumnStretch(3, 1)
        layout.addLayout(controls)
        layout.addWidget(self.plot, stretch=1)
        splitter = QtWidgets.QSplitter(Qt.Vertical, childrenCollapsible=False)
        splitter.addWidget(top)
        splitter.addWidget(bottom)
        splitter.setStretchFactor(1, 2)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(splitter)
        self.refresh()

    def selected_results(self) -> list[Result]:
        return [r for n, r in enumerate(self.results)
                if self.table.item(n, 0) and self.table.item(n, 0).checkState() == Qt.Checked]

    def add(self, result: Result):
        self.results.append(result)
        if not self.energy.value():
            self.energy.setValue(result.peak_energy())
        self.refresh()

    def remove(self):
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for n in rows:
            del self.results[n]
        self.refresh()

    def refresh(self):
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.results))
        _, rows = series_table(self.results)
        for n, values in enumerate(rows):
            label, field, temp, holes, split, orbital, spin, ratio, _ = values
            texts = [label, f"{field:+.3g}", f"{temp:.3g}", f"{holes:.2f}", f"{split:.2f}",
                     f"{orbital:.3f}", f"{spin:.3f}", f"{ratio:.3f}"]
            for column, text in enumerate(texts):
                item = QtWidgets.QTableWidgetItem(text)
                if column == 0:
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(Qt.Checked)
                    item.setToolTip(self.results[n].report())
                self.table.setItem(n, column, item)
        self.table.blockSignals(False)
        self.draw()

    def draw(self):
        self.energy.setEnabled(self.kind.currentText() == 'Dichroism at energy')
        results = self.selected_results()
        if not results:
            return message(self.plot, 'Use "Add to series" on the Sum rules tab to collect results here')
        self.plot.clear()
        draw_series(self.plot.axes, results, self.x_axis.currentText(), self.kind.currentText(), self.energy.value())
        self.plot.style_axes()
        self.plot.draw()

    def popout(self):
        results, x, kind, energy = self.selected_results(), self.x_axis.currentText(), self.kind.currentText(), \
            self.energy.value()
        if results:
            popout(f"Series: {kind}", lambda axes: draw_series(axes, results, x, kind, energy))
