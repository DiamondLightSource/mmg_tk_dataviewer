"""
Multi-Scan Analysis - plot and process a set of scans together
"""
import asteval
import matplotlib.pyplot as plt
from PySide6 import QtWidgets

from mmg_toolbox.utils.experiment import Experiment
from mmg_toolbox.utils.env_functions import scan_number_mapping
from mmg_toolbox.scripts.scripts import SCRIPTS, NOTEBOOKS
from .config import C
from .common import add_menus, show_window, select_folder, button
from .style import card, form, row, grid, scrollable, fit_to_screen


class ScanRange(QtWidgets.QWidget):
    """Choose scan numbers: type a python expression or generate a range"""

    def __init__(self, folder_getter, scan_numbers: list[int] | None = None, parent=None):
        super().__init__(parent)
        self.folder_getter = folder_getter
        self.text = QtWidgets.QPlainTextEdit(str(list(scan_numbers or [])), maximumHeight=70)
        self.text.setPlaceholderText('e.g. [1234, 1235] or range(1234, 1240) or -1 for the last scan')
        self.first = QtWidgets.QSpinBox(maximum=10**9, toolTip='First scan')
        self.last = QtWidgets.QSpinBox(maximum=10**9, toolTip='Last scan')
        self.step = QtWidgets.QSpinBox(minimum=1, maximum=10**6, value=1, toolTip='Step')
        range_row = QtWidgets.QHBoxLayout()
        for widget in (self.first, QtWidgets.QLabel('to', objectName='muted'), self.last,
                       QtWidgets.QLabel('step', objectName='muted'), self.step):
            range_row.addWidget(widget)
        range_row.addWidget(button('Generate', self.generate))
        range_row.addStretch()
        range_row.addWidget(button('All scans', self.all_scans, self))
        range_row.addWidget(button('Choose…', self.select_scans, self))
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.text)
        layout.addLayout(range_row)

    def generate(self):
        self.text.setPlainText(f"range({self.first.value()}, {self.last.value() + 1}, {self.step.value()})")

    def all_scans(self):
        numbers = list(scan_number_mapping(self.folder_getter()))
        if numbers:
            self.first.setValue(numbers[0])
            self.last.setValue(numbers[-1])
        self.text.setPlainText(str(numbers))

    def select_scans(self):
        """Pick scans from a list showing their metadata"""
        from .scan_list import ScanList
        from mmg_toolbox.utils.file_functions import get_scan_number
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle('Select Scans')
        scans = ScanList(self.parent().config if hasattr(self.parent(), 'config') else {}, dialog)
        scans.add_folder(self.folder_getter())
        ok = button('Select', dialog.accept)
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.addWidget(scans)
        layout.addWidget(ok)
        fit_to_screen(dialog, 800, 600)
        if dialog.exec():
            self.text.setPlainText(str(sorted(get_scan_number(f) for f in scans.selected_files())))

    def scan_numbers(self) -> list[int]:
        text = self.text.toPlainText().strip()
        if not text:
            return []
        numbers = asteval.Interpreter(use_numpy=True)(text)
        numbers = [numbers] if isinstance(numbers, int) else list(numbers)
        all_numbers = list(scan_number_mapping(self.folder_getter()))
        return [all_numbers[n] if n < 1 else n for n in numbers]  # n < 1 counts back from the last scan


class MultiScanAnalysis(QtWidgets.QMainWindow):
    """Choose folders, axes and scans, then plot or process them"""

    def __init__(self, config: dict, scan_numbers: list[int] | None = None,
                 x_axis: str = '', y_axis: str = '', folder: str = ''):
        super().__init__()
        self.setWindowTitle('Multi-Scan Analysis')
        self.config = config
        self.data_dir = QtWidgets.QLineEdit(folder or config.get(C.current_dir, ''))
        self.proc_dir = QtWidgets.QLineEdit(config.get(C.current_proc, ''))
        self.x_axis = QtWidgets.QLineEdit(x_axis, placeholderText='x-axis, e.g. axes')
        self.y_axis = QtWidgets.QLineEdit(y_axis, placeholderText='y-axis, e.g. signal')
        self.metadata = QtWidgets.QLineEdit(config.get(C.default_metadata, ''))
        self.range = ScanRange(self.data_dir.text, scan_numbers, self)
        self.script = QtWidgets.QComboBox()
        self.script.addItems([f"script: {s}" for s in SCRIPTS] + [f"notebook: {n}" for n in NOTEBOOKS])

        def browse(line_edit):
            def fn():
                line_edit.setText(select_folder(self, line_edit.text()) or line_edit.text())
            return row(line_edit, button('Browse', fn), stretch=0)

        plots = grid([button(name, fn, self, primary=(name == 'Plot')) for name, fn in [
            ('Plot', self.plot), ('Plot lines', self.plot_lines), ('Plot metadata', self.plot_metadata),
            ('Multi-plot', self.multi_plot), ('Plot 2D', self.plot_2d), ('Plot 3D', self.plot_3d),
            ('Plot surface', self.plot_surf)]], columns=4)
        processing = grid([
            button('Peak fitting', self.open_peak_fit, self),
            button('XMCD', self.open_xmcd, self),
            button('Convert to .dat', self.convert_to_dat, self),
        ], columns=3)
        templates = row(self.script, button('Create', self.create_from_template, self), stretch=0)

        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        layout.addWidget(card(layout=form(
            ('Data', browse(self.data_dir)),
            ('Analysis', browse(self.proc_dir)),
        ), title='Folders'))
        layout.addWidget(card(layout=form(
            ('X', self.x_axis), ('Y', self.y_axis), ('Metadata', self.metadata),
        ), title='Axes'))
        layout.addWidget(card(self.range, title='Scans'))
        layout.addWidget(card(layout=plots, title='Plot'))
        layout.addWidget(card(layout=form(('Open', processing), ('Template', templates)), title='Process'))
        layout.addStretch()
        self.setCentralWidget(scrollable(central))
        fit_to_screen(self, 760, 760)
        add_menus(self, {}, config)

    def experiment(self) -> Experiment:
        return Experiment(self.data_dir.text(), instrument=self.config.get(C.beamline))

    def _args(self):
        return self.experiment(), self.range.scan_numbers(), self.x_axis.text(), self.y_axis.text(), self.metadata.text() or None

    def plot(self):
        exp, scans, x, y, _ = self._args()
        exp.plot.plot(*scans, xaxis=x, yaxis=y)
        plt.show()

    def plot_lines(self):
        exp, scans, x, y, value = self._args()
        exp.plot.multi_lines(*scans, xaxis=x, yaxis=y, value=value)
        plt.show()

    def plot_metadata(self):
        exp, scans, _, _, value = self._args()
        exp.plot.metadata(*scans, values=(value or '').split(','))
        plt.show()

    def multi_plot(self):
        exp, scans, x, y, value = self._args()
        exp.plot.multi_plot(*scans, xaxis=x, yaxis=y, value=value)
        plt.show()

    def plot_2d(self):
        exp, scans, x, y, value = self._args()
        exp.plot.surface_2d(*scans, xaxis=x, signal=y, values=value)
        plt.show()

    def plot_3d(self):
        exp, scans, x, y, value = self._args()
        exp.plot.lines_3d(*scans, xaxis=x, signal=y, values=value)
        plt.show()

    def plot_surf(self):
        exp, scans, x, y, value = self._args()
        exp.plot.surface_3d(*scans, xaxis=x, signal=y, values=value)
        plt.show()

    def open_peak_fit(self):
        from .peak_fit import PeakFitting
        show_window(PeakFitting(self.config, self.range.scan_numbers(), self.x_axis.text(),
                                self.y_axis.text(), self.data_dir.text(), self.metadata.text()))

    def open_xmcd(self):
        from .xmcd import XMCDVisualiser
        show_window(XMCDVisualiser(self.config, self.range.scan_numbers(), folder=self.data_dir.text()))

    def convert_to_dat(self):
        from nexus2srs import run_nexus2srs
        files = [self.experiment().get_scan_filename(n) for n in self.range.scan_numbers()]
        answer = QtWidgets.QMessageBox.question(self, 'Nexus2SRS', f"Convert {len(files)} NeXus files to .dat format?")
        if answer == QtWidgets.QMessageBox.Yes:
            run_nexus2srs('-tiff', *files)

    def create_from_template(self):
        from .processing import create_script, create_notebook_file
        kind, name = self.script.currentText().split(': ', 1)
        exp = self.experiment()
        files = [exp.get_scan_filename(n) for n in self.range.scan_numbers()]
        self.config[C.current_proc] = self.proc_dir.text()
        create = create_script if kind == 'script' else create_notebook_file
        create(self, name, self.config, self.data_dir.text(), files, (self.x_axis.text(), self.y_axis.text()))
