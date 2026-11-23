"""
Peak Fitting - fit peaks in a series of scans and plot the results against a metadata value
"""
import numpy as np
import hdfmap
from PySide6 import QtWidgets
from PySide6.QtCore import Qt

from mmg_toolbox.utils.experiment import Experiment
from mmg_toolbox.fitting import multipeakfit
from mmg_toolbox.fitting.models import PEAK_MODELS, BACKGROUND_MODELS
from .config import C
from .common import add_menus, PlotCanvas, button, labelled, monospace
from .multi_scan import ScanRange

FIT_PARAMETERS = ['amplitude', 'center', 'fwhm', 'background']


class PeakFitting(QtWidgets.QMainWindow):
    """Fit each scan in a series with the same model, then plot fit parameters against metadata"""

    def __init__(self, config: dict, scan_numbers: list[int] | None = None,
                 x_axis: str = '', y_axis: str = '', folder: str = '', metadata: str = ''):
        super().__init__()
        self.setWindowTitle('Peak Fitting')
        self.config = config
        self.results = {}  # scan number: FitResults
        self.map: hdfmap.NexusMap | None = None

        self.data_dir = QtWidgets.QLineEdit(folder or config.get(C.current_dir, ''))
        self.x_axis = QtWidgets.QLineEdit(x_axis or 'axes')
        self.y_axis = QtWidgets.QLineEdit(y_axis or 'signal')
        self.metadata = QtWidgets.QLineEdit(metadata or config.get(C.default_metadata, ''))
        self.range = ScanRange(self.data_dir.text, scan_numbers, self)
        self.n_peaks = QtWidgets.QSpinBox(minimum=0, maximum=10, value=1, toolTip='0 = find peaks automatically')
        self.power = QtWidgets.QDoubleSpinBox(maximum=1e9, toolTip='Minimum peak power when finding peaks')
        self.distance = QtWidgets.QSpinBox(minimum=1, maximum=1000, value=10, toolTip='Minimum points between peaks')
        self.model = QtWidgets.QComboBox()
        self.model.addItems(list(PEAK_MODELS))
        self.background = QtWidgets.QComboBox()
        self.background.addItems(list(BACKGROUND_MODELS))
        self.parameter = QtWidgets.QComboBox()
        self.parameter.addItems(FIT_PARAMETERS + ['All'])

        self.table = QtWidgets.QTreeWidget()
        self.table.setHeaderLabels(['Scan', 'Metadata', *FIT_PARAMETERS])
        self.table.currentItemChanged.connect(lambda *_: self.plot_scan())
        self.result_text = QtWidgets.QPlainTextEdit(readOnly=True, font=monospace())
        self.scan_plot = PlotCanvas(self)
        self.result_plot = PlotCanvas(self, 2, 2)

        options = QtWidgets.QHBoxLayout()
        for label, widget in [('N Peaks:', self.n_peaks), ('Power:', self.power), ('Distance:', self.distance),
                              ('Model:', self.model), ('Background:', self.background)]:
            options.addWidget(QtWidgets.QLabel(label))
            options.addWidget(widget)
        actions = QtWidgets.QHBoxLayout()
        actions.addWidget(button('Load Scans', self.load_scans, self))
        actions.addWidget(button('Fit All', self.fit_all, self))
        actions.addWidget(self.parameter)
        actions.addWidget(button('Plot Results', self.plot_results, self))

        left = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.addLayout(labelled('Data Dir:', self.data_dir))
        left_layout.addLayout(labelled('X:', self.x_axis))
        left_layout.addLayout(labelled('Y:', self.y_axis))
        left_layout.addLayout(labelled('Metadata:', self.metadata))
        left_layout.addWidget(self.range)
        left_layout.addLayout(options)
        left_layout.addLayout(actions)
        left_layout.addWidget(self.table, stretch=1)
        tabs = QtWidgets.QTabWidget()
        tabs.addTab(self.scan_plot, 'Scan')
        tabs.addTab(self.result_plot, 'Results')
        tabs.addTab(self.result_text, 'Fit Report')
        splitter = QtWidgets.QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(tabs)
        self.setCentralWidget(splitter)
        self.resize(1400, 800)
        add_menus(self, {}, config)
        if scan_numbers:
            self.load_scans()

    def load_scans(self):
        """Fill the table with the scans and their metadata values"""
        exp = Experiment(self.data_dir.text(), instrument=self.config.get(C.beamline))
        self.table.clear()
        self.results.clear()
        self.map = None
        for number in self.range.scan_numbers():
            filename = exp.get_scan_filename(number)
            self.map = self.map or hdfmap.create_nexus_map(filename)
            with hdfmap.load_hdf(filename) as hdf:
                value = self.map.eval(hdf, self.metadata.text(), np.nan) if self.metadata.text() else np.nan
            item = QtWidgets.QTreeWidgetItem([str(number), f"{np.mean(value):.4g}"])
            item.setData(0, Qt.UserRole, filename)
            item.setData(1, Qt.UserRole, float(np.mean(value)))
            item.setCheckState(0, Qt.Checked)
            self.table.addTopLevelItem(item)
        self.table.setCurrentItem(self.table.topLevelItem(0))

    def get_xy(self, filename: str) -> tuple[np.ndarray, np.ndarray]:
        with hdfmap.load_hdf(filename) as hdf:
            x = self.map.eval(hdf, self.x_axis.text(), np.arange(self.map.scannables_length()))
            y = self.map.eval(hdf, self.y_axis.text(), np.ones_like(x))
        return np.asarray(x, float), np.asarray(y, float)

    def fit(self, item: QtWidgets.QTreeWidgetItem):
        x, y = self.get_xy(item.data(0, Qt.UserRole))
        result = multipeakfit(
            xvals=x, yvals=y,
            npeaks=self.n_peaks.value() or None,
            min_peak_power=self.power.value() or None,
            peak_distance_idx=self.distance.value(),
            model=self.model.currentText(),
            background=self.background.currentText(),
        )
        self.results[item.text(0)] = result
        for col, name in enumerate(FIT_PARAMETERS, start=2):
            value, error = result.get_value(name)
            item.setText(col, f"{value:.4g} ± {error:.2g}")
        return result

    def plot_scan(self):
        item = self.table.currentItem()
        if item is None:
            return
        self.scan_plot.clear()
        ax = self.scan_plot.ax
        x, y = self.get_xy(item.data(0, Qt.UserRole))
        ax.plot(x, y, '.-', label=f"#{item.text(0)}")
        result = self.fit(item)
        ax.plot(*result.fit_data(), 'k--', label='fit')
        ax.set_xlabel(self.x_axis.text())
        ax.set_ylabel(self.y_axis.text())
        ax.legend(frameon=False)
        self.scan_plot.draw()
        self.result_text.setPlainText(str(result))

    def checked_items(self) -> list[QtWidgets.QTreeWidgetItem]:
        items = [self.table.topLevelItem(n) for n in range(self.table.topLevelItemCount())]
        return [item for item in items if item.checkState(0) == Qt.Checked]

    def fit_all(self):
        for item in self.checked_items():
            self.fit(item)
        self.plot_results()

    def plot_results(self):
        items = [item for item in self.checked_items() if item.text(0) in self.results]
        metadata = [item.data(1, Qt.UserRole) for item in items]
        option = self.parameter.currentText()
        parameters = FIT_PARAMETERS if option == 'All' else [option]
        self.result_plot.clear()
        for ax, name in zip(self.result_plot.axes, parameters):
            values, errors = zip(*[self.results[item.text(0)].get_value(name) for item in items]) if items else ([], [])
            ax.errorbar(metadata, values, errors, fmt='-o')
            ax.set_xlabel(self.metadata.text())
            ax.set_ylabel(name.capitalize())
        self.result_plot.draw()
