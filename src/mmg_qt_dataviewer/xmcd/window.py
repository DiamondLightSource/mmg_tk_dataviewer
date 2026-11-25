"""
XMCD Visualiser window
    left:   scans (with preview), pairs and the processing chain
    middle: grid of pairs, each with a checkbox to include it in the average
    right:  averages and dichroism, sum rules, and the series of results vs field or temperature
"""
import os
import copy
import csv

from PySide6 import QtWidgets
from PySide6.QtCore import Qt, QTimer

from mmg_toolbox.utils.env_functions import get_processing_directory
from mmg_toolbox.xas import SpectraContainer
from ..config import C
from ..common import add_menus, show_window, start_jupyter, run_safely
from ..style import card, fit_to_screen, scrollable
from .analysis import Pair, Result, apply_chain, series_table, to_script, to_notebook
from .scans import ScanBrowser, PairList
from .chain_editor import ChainEditor
from .grid import PairGrid
from .results import AveragePanel, SumRulesPanel, SeriesPanel

WIDE = 1100  # window width (pixels) above which the three panels sit side by side


class XMCDVisualiser(QtWidgets.QMainWindow):
    """Pair, process, inspect and average XAS scans, then calculate the dichroism and sum rules"""

    def __init__(self, config: dict, scan_numbers: list[int] | None = None, folder: str = ''):
        super().__init__()
        self.setWindowTitle('XMCD Visualiser')
        self.config = config
        folder = folder or config.get(C.current_dir, '')
        self.save_folder = config.get(C.current_proc) or (get_processing_directory(folder) if folder else '')
        self.pairs: list[Pair] = []
        self.results: list[Result] = []
        self.processed: dict[int, SpectraContainer] = {}  # id(raw scan): processed scan
        self.errors: dict[int, str] = {}
        self.result: Result | None = None

        self.browser = ScanBrowser(folder)
        self.pair_list = PairList(self.pairs, self.browser)
        self.chain = ChainEditor()
        self.grid = PairGrid()
        self.average = AveragePanel()
        self.sum_rules = SumRulesPanel({'Save NeXus…': self.save_nexus, 'Save CSV…': self.save_csv})
        self.series = SeriesPanel(self.results, {'Save table…': self.save_table,
                                                 'Save all NeXus…': self.save_series_nexus})
        self.browser.process = self.process_scan
        self.browser.mode = self.chain.current_mode

        # wiring
        self._reprocess_timer = QTimer(self, singleShot=True, interval=300, timeout=self.reprocess)
        self.browser.loaded.connect(self._scans_loaded)
        self.browser.pairRequested.connect(lambda: run_safely(self, self.pair_list.pair_selected))
        self.browser.autoPairRequested.connect(lambda: run_safely(self, self.pair_list.auto_pair))
        self.pair_list.changed.connect(self._pairs_changed)
        self.pair_list.pairSelected.connect(self.grid.show_pair)
        self.chain.changed.connect(self._reprocess_timer.start)
        self.grid.includeChanged.connect(self._includes_changed)
        self.grid.conditionChanged.connect(self.update_average)
        self.grid.backgroundChanged.connect(self.redraw_grid)
        self.sum_rules.addRequested.connect(self.add_to_series)

        # layout
        left = QtWidgets.QSplitter(Qt.Vertical, childrenCollapsible=False)
        left.addWidget(card(self.browser, title='Scans'))
        left.addWidget(card(self.pair_list, title='Pairs'))
        left.addWidget(card(self.chain, title='Processing'))
        left.setStretchFactor(0, 5)
        left.setStretchFactor(1, 3)
        left.setStretchFactor(2, 3)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.addTab(self.average, 'Average')
        self.tabs.addTab(self.sum_rules, 'Sum rules')
        self.tabs.addTab(self.series, 'Series')
        self.middle = card(self.grid, title='Pairs: processed spectra and difference')
        self.right = card(scrollable(self.tabs))  # scrolls if the window is too short for the sum rules
        self.right.setMinimumWidth(self.tabs.minimumSizeHint().width() + 40)  # card margins and scroll bar
        self.results_splitter = QtWidgets.QSplitter(Qt.Horizontal, childrenCollapsible=False)
        self.results_splitter.addWidget(self.middle)
        self.results_splitter.addWidget(self.right)
        self.main = QtWidgets.QSplitter(Qt.Horizontal, childrenCollapsible=False)
        left.setMinimumHeight(860)  # scrolls on short screens rather than squashing the scan table
        left_scroll = scrollable(left)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setMinimumWidth(max(340, left.minimumSizeHint().width() + 16))  # room for the scroll bar
        self.main.addWidget(left_scroll)
        self.main.addWidget(self.results_splitter)
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(self.main)
        self.setCentralWidget(central)
        add_menus(self, {
            'File': {
                'Open folder…': self.browser.browse,
                'Add files…': self.browser.browse_files,
                'Set save folder…': self.choose_save_folder,
            },
            'Export': {
                'Dichroism NeXus…': self.save_nexus,
                'Dichroism CSV…': self.save_csv,
                'Series NeXus files…': self.save_series_nexus,
                'Series table…': self.save_table,
                'Python script…': self.export_script,
                'Jupyter notebook…': self.export_notebook,
            },
        }, config)
        self.statusBar().showMessage('Loading scans…' if folder else 'Choose a folder of XAS scans (File > Open)')
        fit_to_screen(self, 2400, 1400)
        self._arrange()

        if scan_numbers:
            self.browser.set_scan_numbers(scan_numbers)
        if folder:
            self.browser.reload()

    """Layout"""

    def _arrange(self):
        """Three panels side by side on wide windows; results below the grid on narrow windows"""
        wide = self.width() >= WIDE
        orientation = Qt.Horizontal if wide else Qt.Vertical
        if self.results_splitter.orientation() != orientation or not self.main.sizes()[0]:
            self.results_splitter.setOrientation(orientation)
            left = max(self.main.widget(0).minimumWidth(), int(self.width() * 0.24))
            self.main.setSizes([left, self.width() - left])
            size = self.width() - left if wide else self.height()
            self.results_splitter.setSizes([int(size * 0.55), int(size * 0.45)])

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._arrange()

    """Processing"""

    def process_scan(self, scan: SpectraContainer) -> SpectraContainer:
        return apply_chain(scan, self.chain.steps)

    def _scans_loaded(self):
        scans = self.browser.loaded_scans()
        self._update_modes(scans)
        self.statusBar().showMessage(f"{len(scans)} XAS scans loaded from {self.browser.folder.text()}")
        if scans and not self.pairs:
            run_safely(self, self.pair_list.auto_pair)
        self.browser.draw_preview()

    def _update_modes(self, scans: list[SpectraContainer]):
        """Detection modes of the scans in the Mode menu (tey, tfy…)"""
        if scans:
            modes = list(dict.fromkeys(mode for scan in scans for mode in scan.spectra))
            self.chain.set_modes(modes, scans[0].metadata.default_mode)

    def _pairs_changed(self):
        self._update_modes([s for pair in self.pairs for s in (pair.scan1, pair.scan2)]
                           + self.browser.loaded_scans())
        self.grid.set_pairs(self.pairs)
        self.reprocess()

    def reprocess(self):
        """Apply the processing chain to every paired scan, then redraw everything"""
        QtWidgets.QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.processed.clear()
            self.errors.clear()
            failed_step, message = None, ''
            for scan in {id(s): s for pair in self.pairs for s in (pair.scan1, pair.scan2)}.values():
                processed = scan
                for n, step in enumerate(self.chain.steps):
                    try:
                        processed = step.apply(processed)
                    except Exception as e:
                        self.errors[id(scan)] = f"step {n + 1} ({step.label()}): {e}"
                        failed_step, message = n, str(e)
                        break
                self.processed[id(scan)] = processed
            self.chain.set_error(failed_step, message)
            self.redraw_grid()
            self.update_average()
            self.browser.draw_preview()
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

    def redraw_grid(self):
        self.grid.draw(self.processed, self.errors, self.chain.current_mode())

    def _includes_changed(self):
        self.pair_list.refresh()
        self.update_average()

    def update_average(self):
        """Average the included pairs at the selected condition and subtract them"""
        pairs = [p for p in self.grid.active_pairs() if p.include]
        failed = [p for p in pairs if id(p.scan1) in self.errors or id(p.scan2) in self.errors]
        if not pairs:
            self.result = None
            info = 'No pairs included: tick pairs in the grid to average them'
        elif failed:
            self.result = None
            info = f"Processing failed for {failed[0].label()}: {self.errors.get(id(failed[0].scan1)) or ''}"
        else:
            try:
                self.result = Result.calculate(pairs, self.processed, self.chain.steps, self.chain.current_mode(),
                                               self.browser.dls_loader.isChecked())
                info = f"{len(pairs)} pairs averaged: {self.result.label()}"
            except Exception as e:
                self.result = None
                info = f"Averaging failed: {e}"
        self.average.update_result(self.result, info)
        self.sum_rules.update_result(self.result)
        self.statusBar().showMessage(info)

    def add_to_series(self):
        if self.result is None:
            raise ValueError('There is no result to add')
        self.series.add(copy.copy(self.result))
        self.tabs.setCurrentWidget(self.series)

    """Saving and export"""

    def choose_save_folder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, 'Save folder', self.save_folder)
        if folder:
            self.save_folder = folder

    def _save_name(self, name: str, file_filter: str) -> str:
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Save as', os.path.join(self.save_folder, name), file_filter)
        if filename:
            self.save_folder = os.path.dirname(filename)
        return filename

    def _current_result(self) -> Result:
        if self.result is None:
            raise ValueError('There is no result: include some pairs first')
        return self.result

    def save_nexus(self):
        result = self._current_result()
        filename = self._save_name(result.file_name(), 'NeXus (*.nxs)')
        if filename:
            result.write_nexus(filename)
            self.statusBar().showMessage(f"Saved {filename}")

    def save_csv(self):
        result = self._current_result()
        filename = self._save_name(result.file_name('.csv'), 'CSV (*.csv)')
        if filename:
            result.diff.write_csv(filename, result.mode)
            self.statusBar().showMessage(f"Saved {filename}")

    def save_series_nexus(self):
        if not self.results:
            raise ValueError('The series is empty')
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, 'Save series to folder', self.save_folder)
        if folder:
            for result in self.results:
                result.write_nexus(os.path.join(folder, result.file_name()))
            self.statusBar().showMessage(f"Saved {len(self.results)} files to {folder}")

    def save_table(self):
        if not self.results:
            raise ValueError('The series is empty')
        filename = self._save_name('xmcd_series.csv', 'CSV (*.csv)')
        if filename:
            header, rows = series_table(self.results, self.series.energy.value() or None)
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(header)
                writer.writerows(rows)
            self.statusBar().showMessage(f"Saved {filename}")

    def _export_results(self) -> list[Result]:
        """The series, or the current result if the series is empty"""
        return list(self.results) or [self._current_result()]

    def export_script(self):
        from ..editors import PythonEditor
        results = self._export_results()
        filename = self._save_name('xmcd_analysis.py', 'Python (*.py)')
        if filename:
            script = to_script(results, self.save_folder)
            with open(filename, 'w') as f:
                f.write(script)
            show_window(PythonEditor(script, filename))

    def export_notebook(self):
        results = self._export_results()
        filename = self._save_name('xmcd_analysis.ipynb', 'Notebook (*.ipynb)')
        if filename:
            with open(filename, 'w') as f:
                f.write(to_notebook(results, self.save_folder))
            answer = QtWidgets.QMessageBox.question(self, 'Notebook', f"Start Jupyter to view notebook?\n{filename}")
            if answer == QtWidgets.QMessageBox.Yes:
                start_jupyter(file=filename)
