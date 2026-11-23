"""
XMCD Visualiser - average polarisation pairs, compare processed spectra and apply the sum rules
"""
import os

from PySide6 import QtWidgets
from PySide6.QtCore import Qt

from mmg_toolbox.utils.experiment import Experiment
from mmg_toolbox.xas import SpectraContainerSubtraction, polarised_pairs, average_scans
from mmg_toolbox.xas.spectra import BACKGROUND_FUNCTIONS
from mmg_toolbox.xas.nxxas_loader import load_xas_scans
from .config import C
from .common import add_menus, PlotCanvas, button, labelled, monospace, select_folder, select_hdf_files


class XMCDVisualiser(QtWidgets.QMainWindow):
    """Three tabs: Average Data, Compare Data and Sum Rule Analysis"""

    def __init__(self, config: dict, scan_numbers: list[int] | None = None, folder: str = ''):
        super().__init__()
        self.setWindowTitle('XMCD Visualiser')
        self.config = config
        self.folder = folder or config.get(C.current_dir, '')
        self.save_folder = config.get(C.current_proc) or self.folder
        self.average = AverageTab(self, ', '.join(str(n) for n in scan_numbers or []))
        self.compare = CompareTab(self)
        self.sum_rules = SumRulesTab(self)
        tabs = QtWidgets.QTabWidget()
        tabs.addTab(self.average, 'Average Data')
        tabs.addTab(self.compare, 'Compare Data')
        tabs.addTab(self.sum_rules, 'Sum Rule Analysis')
        self.setCentralWidget(tabs)
        self.resize(1400, 900)
        add_menus(self, {'File': {
            'Set Data path': lambda: self._set('folder'),
            'Set Save path': lambda: self._set('save_folder'),
        }}, config)

    def _set(self, attr: str):
        folder = select_folder(self, getattr(self, attr))
        if folder:
            setattr(self, attr, folder)

    def experiment(self) -> Experiment:
        return Experiment(self.folder, instrument=self.config.get(C.beamline))

    def save(self, spectra: SpectraContainerSubtraction, mode: str, extension: str):
        filename = os.path.join(self.save_folder, spectra.label() + extension)
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(self, 'Save', filename)
        if filename and extension == '.nxs':
            spectra.write_nexus(filename)
        elif filename:
            spectra.write_csv(filename, mode)


class AverageTab(QtWidgets.QWidget):
    """Find polarisation pairs, plot each pair's difference and average the selected pairs"""

    def __init__(self, base: XMCDVisualiser, scan_range: str = ''):
        super().__init__()
        self.base = base
        self.spectra: SpectraContainerSubtraction | None = None
        self.scan_range = QtWidgets.QLineEdit(scan_range, placeholderText='e.g. 1234-1243')
        self.dls_loader = QtWidgets.QCheckBox('DLS Loader')
        self.mode = QtWidgets.QComboBox()
        self.background = QtWidgets.QComboBox()
        self.background.addItems(['None', *BACKGROUND_FUNCTIONS])
        self.pairs = QtWidgets.QTreeWidget()
        self.pairs.setHeaderLabels(['Scan 1', 'Scan 2'])
        self.pairs.itemChanged.connect(lambda *_: self.plot_average())
        self.pair_plot = PlotCanvas(self)
        self.average_plot = PlotCanvas(self, 3, 1)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addWidget(button('Find Pairs', self.find_pairs, self))
        buttons.addWidget(button('Plot', self.plot_pairs, self))
        save = QtWidgets.QHBoxLayout()
        save.addWidget(button('Add to Comparison', lambda: self.spectra and base.compare.add(self.spectra), self))
        save.addWidget(button('Save NeXus', lambda: self.spectra and base.save(self.spectra, self.mode.currentText(), '.nxs'), self))
        save.addWidget(button('Save CSV', lambda: self.spectra and base.save(self.spectra, self.mode.currentText(), '.csv'), self))
        left = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.addLayout(labelled('Scans:', self.scan_range, self.dls_loader))
        left_layout.addLayout(labelled('Mode:', self.mode))
        left_layout.addLayout(labelled('Background:', self.background))
        left_layout.addLayout(buttons)
        left_layout.addWidget(QtWidgets.QLabel('Pairs (untick to exclude from the average)'))
        left_layout.addWidget(self.pairs)
        left_layout.addLayout(save)
        splitter = QtWidgets.QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(self.pair_plot)
        splitter.addWidget(self.average_plot)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(splitter)
        self._processed = {}  # (scan1, scan2): (processed1, processed2)

    def find_pairs(self):
        from mmg_toolbox.utils.misc_functions import string2numbers
        scans = self.base.experiment().load_xas(*string2numbers(self.scan_range.text()),
                                                 dls_loader=self.dls_loader.isChecked())
        if not scans:
            return
        self.mode.clear()
        self.mode.addItems(list(scans[0].spectra))
        self.pairs.blockSignals(True)
        self.pairs.clear()
        for s1, s2 in polarised_pairs(*scans):
            item = QtWidgets.QTreeWidgetItem([str(s1.metadata.scan_no), str(s2.metadata.scan_no)])
            item.setCheckState(0, Qt.Checked)
            self.pairs.addTopLevelItem(item)
        self.pairs.blockSignals(False)
        self.plot_pairs()

    def process_pairs(self):
        """Load, normalise and remove the background from each pair"""
        exp = self.base.experiment()
        background = self.background.currentText()
        self._processed.clear()
        for n in range(self.pairs.topLevelItemCount()):
            item = self.pairs.topLevelItem(n)
            s1, s2 = exp.load_xas(int(item.text(0)), int(item.text(1)), dls_loader=self.dls_loader.isChecked())
            s1, s2 = s1.divide_by_preedge(), s2.divide_by_preedge()
            if background != 'None':
                s1, s2 = s1.remove_background(background), s2.remove_background(background)
            self._processed[(item.text(0), item.text(1))] = (s1, s2)

    def plot_pairs(self):
        self.process_pairs()
        mode = self.mode.currentText()
        self.pair_plot.clear()
        ax = self.pair_plot.ax
        for (n1, n2), (s1, s2) in self._processed.items():
            difference = (s1 - s2).spectra[mode]
            ax.plot(difference.energy, difference.signal, label=f"{n1} - {n2}")
        ax.set_title('Pair differences')
        ax.set_xlabel('E [eV]')
        ax.legend(frameon=False, fontsize=8)
        self.pair_plot.draw()
        self.plot_average()

    def plot_average(self):
        checked = [self.pairs.topLevelItem(n) for n in range(self.pairs.topLevelItemCount())]
        pairs = [self._processed[(i.text(0), i.text(1))] for i in checked
                 if i.checkState(0) == Qt.Checked and (i.text(0), i.text(1)) in self._processed]
        if not pairs:
            return
        mode = self.mode.currentText()
        self.spectra = average_scans(*[p[0] for p in pairs]) - average_scans(*[p[1] for p in pairs])
        self.average_plot.clear()
        ax1, ax2, ax3 = self.average_plot.axes
        for ax, container in [(ax1, self.spectra.spectra1), (ax2, self.spectra.spectra2)]:
            for parent in container.parents:
                spectrum = parent.spectra[mode]
                ax.plot(spectrum.energy, spectrum.signal, label=parent.name)
            ax.set_title(container.name, fontsize=9)
            ax.legend(frameon=False, fontsize=7)
        mcd = self.spectra.spectra[mode]
        ax3.plot(mcd.energy, mcd.signal, 'k')
        ax3.set_title(self.spectra.label(), fontsize=9)
        ax3.set_xlabel('E [eV]')
        self.average_plot.draw()
        self.base.sum_rules.update_spectra(self.spectra, mode)


class CompareTab(QtWidgets.QWidget):
    """Plot processed XMCD spectra together"""

    def __init__(self, base: XMCDVisualiser):
        super().__init__()
        self.base = base
        self.spectra: dict[str, SpectraContainerSubtraction] = {}
        self.list = QtWidgets.QListWidget()
        self.list.itemChanged.connect(lambda *_: self.plot())
        self.mode = QtWidgets.QComboBox()
        self.mode.currentTextChanged.connect(lambda *_: self.plot())
        self.figure = PlotCanvas(self)
        left = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.addWidget(button('Browse Data', self.browse, self))
        left_layout.addLayout(labelled('Mode:', self.mode))
        left_layout.addWidget(self.list)
        left_layout.addWidget(button('Plot 3D', self.plot_3d, self))
        splitter = QtWidgets.QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(self.figure)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(splitter)

    def browse(self):
        for filename in select_hdf_files(self, self.base.save_folder):
            for spectra in load_xas_scans(filename):
                self.add(spectra)

    def add(self, spectra):
        name = spectra.label()
        self.spectra[name] = spectra
        if self.mode.findText(next(iter(spectra.spectra))) < 0:
            self.mode.addItems([m for m in spectra.spectra if self.mode.findText(m) < 0])
        item = QtWidgets.QListWidgetItem(name)
        item.setCheckState(Qt.Checked)
        self.list.addItem(item)
        self.plot()

    def checked(self) -> list:
        items = [self.list.item(n) for n in range(self.list.count())]
        return [self.spectra[i.text()] for i in items if i.checkState() == Qt.Checked]

    def plot(self):
        mode = self.mode.currentText()
        self.figure.clear()
        for spectra in self.checked():
            if mode in spectra.spectra:
                spectrum = spectra.spectra[mode]
                self.figure.ax.plot(spectrum.energy, spectrum.signal, label=spectra.label())
        self.figure.ax.set_xlabel('E [eV]')
        self.figure.ax.legend(frameon=False, fontsize=8)
        self.figure.draw()

    def plot_3d(self):
        import matplotlib.pyplot as plt
        mode = self.mode.currentText()
        ax = plt.figure().add_subplot(projection='3d')
        for n, spectra in enumerate(self.checked()):
            spectrum = spectra.spectra[mode]
            ax.plot(spectrum.energy, [n] * len(spectrum.energy), spectrum.signal, label=spectra.label())
        ax.set_xlabel('E [eV]')
        plt.show()


class SumRulesTab(QtWidgets.QWidget):
    """XMCD sum rules with an adjustable split energy between the two edges"""

    def __init__(self, base: XMCDVisualiser):
        super().__init__()
        self.base = base
        self.spectra: SpectraContainerSubtraction | None = None
        self.mode = ''
        self.split = QtWidgets.QDoubleSpinBox(decimals=2, maximum=1e6, singleStep=0.5)
        self.split.valueChanged.connect(lambda *_: self.update_plot())
        self.figure = PlotCanvas(self, 2, 1)
        self.report = QtWidgets.QPlainTextEdit(readOnly=True, font=monospace())
        right = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right)
        right_layout.addLayout(labelled('Split energy [eV]:', self.split))
        right_layout.addWidget(self.report)
        right_layout.addWidget(button('Add to Comparison', lambda: self.spectra and base.compare.add(self.spectra), self))
        right_layout.addWidget(button('Save NeXus', lambda: self.spectra and base.save(self.spectra, self.mode, '.nxs'), self))
        right_layout.addWidget(button('Save CSV', lambda: self.spectra and base.save(self.spectra, self.mode, '.csv'), self))
        splitter = QtWidgets.QSplitter()
        splitter.addWidget(self.figure)
        splitter.addWidget(right)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(splitter)

    def update_spectra(self, spectra: SpectraContainerSubtraction, mode: str):
        self.spectra, self.mode = spectra, mode
        mcd = spectra.spectra[mode]
        self.split.blockSignals(True)
        self.split.setRange(min(mcd.energy), max(mcd.energy))
        self.split.setValue(mcd.get_split_energy(spectra.get_edges()))
        self.split.blockSignals(False)
        self.update_plot()

    def update_plot(self):
        if self.spectra is None:
            return
        split = self.split.value()
        self.figure.clear()
        top, bottom = self.figure.axes
        for parent in self.spectra.parents:
            parent.spectra[self.mode].plot(ax=top, label=parent.name)
        top.set_ylabel(self.mode)
        top.legend(frameon=False)
        self.spectra.spectra[self.mode].plot_sum_rules_ratio(ax=bottom, split_energy=split)
        for ax in (top, bottom):
            ax.axvline(split, color='r', alpha=0.5)
        bottom.set_xlabel('E [eV]')
        self.figure.draw()
        self.report.setPlainText(self.spectra.sum_rules_report(mode=self.mode, split_energy=split))
