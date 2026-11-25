"""
Scan browser (table of XAS scans with a preview plot) and the list of scan pairs
"""
import os

from PySide6 import QtWidgets
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QBrush, QColor

from mmg_toolbox.utils.file_functions import list_files, get_scan_number
from mmg_toolbox.utils.misc_functions import string2numbers
from mmg_toolbox.xas import SpectraContainer
from ..common import PlotCanvas, popout, select_folder, select_hdf_files, tool_button, button
from ..style import CURRENT, row
from .analysis import Pair, find_pairs, load_scan
from .draw import draw_scans

PATH = Qt.UserRole
COLUMNS = ['Scan', 'Pol', 'B (T)', 'T (K)', 'Edge', 'Energy (eV)', 'Command']


class ScanBrowser(QtWidgets.QWidget):
    """
    Table of XAS scans in a folder, loaded one at a time in the background, with a preview plot
    of the selected scans. Use the arrow keys to step through the scans.
    """
    loaded = Signal()  # all scans in the table have been loaded
    pairRequested = Signal()  # 'Add selected pair' in the right-click menu
    autoPairRequested = Signal()
    selectionChanged = Signal()

    def __init__(self, folder: str = '', parent=None):
        super().__init__(parent)
        self.scans: dict[str, SpectraContainer] = {}  # filename: raw scan
        self.errors: dict[str, str] = {}
        self._queue: list[QtWidgets.QTreeWidgetItem] = []
        self.process = lambda scan: scan  # set by the window to apply the processing chain
        self.mode = lambda: 'tey'

        self.folder = QtWidgets.QLineEdit(folder, placeholderText='Folder of NeXus scan files')
        self.folder.returnPressed.connect(self.reload)
        self.numbers = QtWidgets.QLineEdit(placeholderText='Scans, e.g. 1001-1016 (blank = all)')
        self.numbers.returnPressed.connect(self.reload)
        self.dls_loader = QtWidgets.QCheckBox('DLS loader', checked=True,
                                              toolTip='Read files using the beamline metadata (hdfmap)')
        self.dls_loader.toggled.connect(lambda: (self.scans.clear(), self.reload()))
        self.search = QtWidgets.QLineEdit(placeholderText='Filter…', clearButtonEnabled=True)
        self.search.textChanged.connect(self._filter)

        self.tree = QtWidgets.QTreeWidget(rootIsDecorated=False, alternatingRowColors=True, uniformRowHeights=True)
        self.tree.setHeaderLabels(COLUMNS)
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.tree.itemSelectionChanged.connect(self._selection_changed)
        self.tree.setToolTip('Select two scans (Ctrl+click) and right-click to add them as a pair')
        self.tree.setContextMenuPolicy(Qt.ActionsContextMenu)
        self.tree.addAction(QAction('Add selected pair', self.tree, triggered=self.pairRequested.emit))
        self.tree.addAction(QAction('Auto-pair selected scans', self.tree, triggered=self.autoPairRequested.emit))
        self.tree.header().setStretchLastSection(True)
        for column, width in enumerate((60, 40, 50, 50, 60, 90)):
            self.tree.setColumnWidth(column, width)

        self.show_processed = QtWidgets.QCheckBox('Processed', checked=True, toolTip='Apply the processing chain')
        self.show_background = QtWidgets.QCheckBox('Background')
        for check in (self.show_processed, self.show_background):
            check.toggled.connect(self.draw_preview)
        self.preview = PlotCanvas(self)
        self.preview.toolbar_row.addWidget(self.show_processed)
        self.preview.toolbar_row.addWidget(self.show_background)
        self.preview.toolbar_row.addWidget(tool_button('⤢', self.popout_preview, 'Open in a new window'))
        self.preview.canvas.mpl_connect('button_press_event', lambda e: e.dblclick and self.popout_preview())

        top = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(top)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(row(self.folder, tool_button('…', self.browse, 'Choose folder'),
                             tool_button('+', self.browse_files, 'Add files'), stretch=0))
        layout.addLayout(row(self.numbers, self.dls_loader, button('Load', self.reload, self), stretch=0))
        layout.addWidget(self.search)
        layout.addWidget(self.tree)
        splitter = QtWidgets.QSplitter(Qt.Vertical, childrenCollapsible=False)
        splitter.addWidget(top)
        splitter.addWidget(self.preview)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        self.tree.setMinimumHeight(150)
        self.preview.setMinimumHeight(180)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(splitter)
        self._timer = QTimer(self, interval=0, timeout=self._load_next)

    def browse(self):
        folder = select_folder(self, self.folder.text())
        if folder:
            self.folder.setText(folder)
            self.reload()

    def browse_files(self):
        self.add_files(select_hdf_files(self, self.folder.text()))

    def reload(self):
        """List the files in the folder that match the scan numbers"""
        self.tree.clear()
        self._queue.clear()
        files = list_files(self.folder.text())
        if self.numbers.text().strip():
            numbers = set(string2numbers(self.numbers.text()))
            files = [f for f in files if get_scan_number(f) in numbers]
        self.add_files(sorted(files, key=get_scan_number))

    def set_scan_numbers(self, numbers: list[int]):
        self.numbers.setText(', '.join(str(n) for n in numbers))

    def add_files(self, files: list[str]):
        for filename in files:
            item = QtWidgets.QTreeWidgetItem(self.tree, [str(get_scan_number(filename))])
            item.setData(0, PATH, filename)
            item.setToolTip(0, filename)
            self._queue.append(item)
        self._timer.start()

    def _load_next(self):
        """Load one scan per event-loop cycle so the window stays responsive"""
        if not self._queue:
            self._timer.stop()
            self.loaded.emit()
            return
        item = self._queue.pop(0)
        filename = item.data(0, PATH)
        try:
            if filename not in self.scans:
                self.scans[filename] = load_scan(filename, self.dls_loader.isChecked())
            m = self.scans[filename].metadata
            energy = f"{min(m.energy):.0f}–{max(m.energy):.0f}"
            for column, text in enumerate([m.pol, f"{m.mag_field:+.3g}", f"{m.temp:.3g}",
                                           f"{m.element} {m.edge}", energy, str(m.cmd)], start=1):
                item.setText(column, text)
            item.setToolTip(6, str(m.cmd))
        except Exception as e:
            self.errors[filename] = str(e)
            item.setText(6, f"not loaded: {e}")
            item.setToolTip(6, str(e))
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            item.setForeground(6, QBrush(QColor(CURRENT['muted'])))

    def is_loading(self) -> bool:
        return bool(self._queue)

    def _items(self) -> list[QtWidgets.QTreeWidgetItem]:
        return [self.tree.topLevelItem(n) for n in range(self.tree.topLevelItemCount())]

    def loaded_scans(self) -> list[SpectraContainer]:
        """Loaded scans in table order"""
        files = (item.data(0, PATH) for item in self._items())
        return [self.scans[f] for f in files if f in self.scans]

    def selected_scans(self) -> list[SpectraContainer]:
        files = (item.data(0, PATH) for item in self.tree.selectedItems())
        return [self.scans[f] for f in files if f in self.scans]

    def mark_paired(self, filenames: set[str]):
        """Show scans that are already in a pair in a muted colour"""
        for item in self._items():
            colour = CURRENT['muted'] if item.data(0, PATH) in filenames else CURRENT['text']
            for column in range(5):
                item.setForeground(column, QBrush(QColor(colour)))

    def _filter(self, text: str):
        text = text.lower()
        for item in self._items():
            match = any(text in item.text(c).lower() for c in range(item.columnCount()))
            item.setHidden(bool(text) and not match)

    def _selection_changed(self):
        self.draw_preview()
        self.selectionChanged.emit()

    def _preview_scans(self) -> list[SpectraContainer]:
        scans = self.selected_scans()
        if self.show_processed.isChecked():
            scans = [self.process(scan) for scan in scans]
        return scans

    def draw_preview(self):
        self.preview.clear()
        try:
            scans = self._preview_scans()
            draw_scans(self.preview.axes, scans, self.mode(), self.show_background.isChecked())
        except Exception as e:
            self.preview.ax.text(0.5, 0.5, str(e), ha='center', va='center', wrap=True,
                                 transform=self.preview.ax.transAxes, color=CURRENT['muted'])
        self.preview.style_axes()
        self.preview.draw()

    def popout_preview(self):
        scans, mode, bkg = self._preview_scans(), self.mode(), self.show_background.isChecked()
        names = ', '.join(str(s.metadata.scan_no) for s in scans)
        popout(f"Scans {names}", lambda axes: draw_scans(axes, scans, mode, bkg))


class PairList(QtWidgets.QWidget):
    """
    Pairs of scans to subtract: found automatically by opposite polarisation or field,
    or made from two scans selected in the scan browser
    """
    changed = Signal()
    pairSelected = Signal(int)

    def __init__(self, pairs: list[Pair], browser: ScanBrowser, parent=None):
        super().__init__(parent)
        self.pairs = pairs  # shared with the window
        self.browser = browser
        self.by = QtWidgets.QComboBox()
        self.by.addItems(['Polarisation', 'Field'])
        self.by.setToolTip('Auto-pair scans with opposite polarisation at the same field,\n'
                           'or opposite field at the same polarisation')
        self.tree = QtWidgets.QTreeWidget(rootIsDecorated=False, alternatingRowColors=True, uniformRowHeights=True)
        self.tree.setHeaderLabels(['Pair', 'Condition', ''])
        self.tree.setColumnWidth(0, 150)
        self.tree.setColumnWidth(1, 190)
        self.tree.setMinimumHeight(110)
        self.tree.itemSelectionChanged.connect(self._selected)
        self.tree.itemDoubleClicked.connect(lambda *_: self.swap())

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        auto = button('Auto-pair', self.auto_pair, self, primary=True)
        auto.setToolTip('Replace the pairs with pairs found automatically, by opposite polarisation or field,\n'
                        'from the scans selected in the Scans table (or from all loaded scans if fewer\n'
                        'than two are selected). Scans are only paired with the same element and temperature.')
        add = button('Add selected pair', self.pair_selected, self)
        add.setToolTip('Add the two scans selected in the Scans table (Ctrl+click to select two) as a new pair')
        hint = QtWidgets.QLabel('Select two scans in the Scans table and click Add selected pair, '
                                'or use Auto-pair to pair scans automatically.', objectName='muted', wordWrap=True)
        layout.addWidget(hint)
        layout.addLayout(row(QtWidgets.QLabel('By'), self.by, auto, None))
        layout.addWidget(self.tree)
        layout.addLayout(row(add, button('Swap', self.swap, self), button('Remove', self.remove, self),
                             button('Clear', self.clear, self), None))

    def auto_pair(self):
        """Pair the selected scans, or all loaded scans if fewer than two are selected"""
        scans = self.browser.selected_scans()
        if len(scans) < 2:
            scans = self.browser.loaded_scans()
        if not scans:
            raise ValueError('No scans are loaded')
        self.pairs[:] = [Pair(s1, s2) for s1, s2 in find_pairs(scans, self.by.currentText().lower())]
        if not self.pairs:
            raise ValueError(f"No pairs with opposite {self.by.currentText().lower()} were found")
        self.refresh()
        self.changed.emit()

    def pair_selected(self):
        scans = self.browser.selected_scans()
        if len(scans) != 2:
            raise ValueError('Select exactly two scans in the scan table')
        self.pairs.append(Pair(*scans))
        self.pairs.sort(key=lambda p: min(p.numbers()))
        self.refresh()
        self.changed.emit()

    def current(self) -> int:
        index = self.tree.indexOfTopLevelItem(self.tree.currentItem()) if self.tree.currentItem() else -1
        return index

    def swap(self):
        n = self.current()
        if n >= 0:
            pair = self.pairs[n]
            self.pairs[n] = Pair(pair.scan2, pair.scan1, pair.include)
            self.refresh()
            self.changed.emit()

    def remove(self):
        n = self.current()
        if n >= 0:
            del self.pairs[n]
            self.refresh()
            self.changed.emit()

    def clear(self):
        self.pairs.clear()
        self.refresh()
        self.changed.emit()

    def refresh(self):
        current = self.current()
        self.tree.clear()
        for pair in self.pairs:
            warnings = pair.warnings()
            item = QtWidgets.QTreeWidgetItem(self.tree, [pair.label(), pair.condition(), '⚠' if warnings else ''])
            item.setToolTip(0, '\n'.join(os.path.basename(f) for f in pair.files()))
            item.setToolTip(2, '\n'.join(warnings))
            if not pair.include:
                for column in range(3):
                    item.setForeground(column, QBrush(QColor(CURRENT['muted'])))
        if 0 <= current < self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(current))
        self.browser.mark_paired({f for pair in self.pairs for f in pair.files()})

    def _selected(self):
        if self.current() >= 0:
            self.pairSelected.emit(self.current())
