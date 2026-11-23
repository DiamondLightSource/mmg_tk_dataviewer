"""
Tree of experiment folders and the scan files inside them, with metadata columns
"""
import os

import hdfmap
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, QTimer, Signal

from mmg_toolbox.utils.file_functions import list_files, get_scan_number, display_timestamp
from .config import C
from .common import select_folder, button

PATH_ROLE = Qt.UserRole


class ScanList(QtWidgets.QWidget):
    """
    Folders containing NeXus scan files, with metadata columns from config[metadata_list].
    Emits selectionChanged(list_of_files) when the scan selection changes.
    """
    selectionChanged = Signal(list)

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.metadata = dict(config.get(C.metadata_list, {}))
        self._pending = []  # tree items waiting for metadata
        self._map = None

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(['Scan', 'Modified', *self.metadata])
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.tree.itemSelectionChanged.connect(lambda: self.selectionChanged.emit(self.selected_files()))
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)

        self.number = QtWidgets.QSpinBox()
        self.number.setRange(0, 10**9)
        self.number.editingFinished.connect(lambda: self.select_scan(self.number.value()))
        self.search = QtWidgets.QLineEdit(placeholderText='Search...')
        self.search.textChanged.connect(self._filter)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(self.number)
        top.addWidget(button('-', lambda: self.step(-1)))
        top.addWidget(button('+', lambda: self.step(1)))
        top.addWidget(self.search, stretch=1)
        top.addWidget(button('Add Folder', self.browse_folder))
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top)
        layout.addWidget(self.tree)

        self._metadata_timer = QTimer(self, interval=0, timeout=self._load_next_metadata)
        self._poll_timer = QTimer(self, interval=5000, timeout=self.update_files)
        self._poll_timer.start()

    def add_folder(self, folder: str):
        folder = os.path.abspath(folder)
        item = QtWidgets.QTreeWidgetItem([os.path.basename(folder) or folder])
        item.setData(0, PATH_ROLE, folder)
        item.setToolTip(0, folder)
        self.tree.addTopLevelItem(item)
        self._add_files(item, list_files(folder))
        item.setExpanded(True)

    def _add_files(self, folder_item: QtWidgets.QTreeWidgetItem, files: list[str]):
        for file in files:
            item = QtWidgets.QTreeWidgetItem([str(get_scan_number(file)), display_timestamp(os.stat(file).st_mtime)])
            item.setData(0, PATH_ROLE, file)
            item.setToolTip(0, file)
            folder_item.insertChild(0, item)  # newest first
            self._pending.append(item)
        self._metadata_timer.start()

    def _load_next_metadata(self):
        """Fill metadata columns one file at a time, so the window stays responsive"""
        if not self._pending:
            self._metadata_timer.stop()
            return
        item = self._pending.pop(0)
        filename = item.data(0, PATH_ROLE)
        try:
            if self._map is None:
                self._map = hdfmap.create_nexus_map(filename)
            with hdfmap.load_hdf(filename) as hdf:
                for col, fmt in enumerate(self.metadata.values(), start=2):
                    item.setText(col, str(self._map.format_hdf(hdf, fmt)))
        except Exception as e:
            item.setText(2, str(e))

    def update_files(self):
        """Add any new files that have appeared in the folders"""
        for n in range(self.tree.topLevelItemCount()):
            folder_item = self.tree.topLevelItem(n)
            known = {folder_item.child(i).data(0, PATH_ROLE) for i in range(folder_item.childCount())}
            new = [f for f in list_files(folder_item.data(0, PATH_ROLE)) if f not in known]
            if new:
                self._add_files(folder_item, new)

    def browse_folder(self):
        folder = select_folder(self, self.config.get(C.current_dir, ''))
        if folder:
            self.add_folder(folder)

    def selected_files(self) -> list[str]:
        files = [item.data(0, PATH_ROLE) for item in self.tree.selectedItems()]
        return [f for f in files if os.path.isfile(f)]

    def current_folder(self) -> str:
        item = self.tree.currentItem() or self.tree.topLevelItem(0)
        if item is None:
            return self.config.get(C.current_dir, '')
        path = item.data(0, PATH_ROLE)
        return path if os.path.isdir(path) else os.path.dirname(path)

    def _scan_items(self) -> list[QtWidgets.QTreeWidgetItem]:
        return [self.tree.topLevelItem(n).child(i)
                for n in range(self.tree.topLevelItemCount())
                for i in range(self.tree.topLevelItem(n).childCount())]

    def select_first(self):
        items = self._scan_items()
        if items:
            self.tree.setCurrentItem(items[0])

    def select_scan(self, scan_number: int):
        for item in self._scan_items():
            if item.text(0) == str(scan_number):
                self.tree.setCurrentItem(item)
                return

    def step(self, direction: int):
        files = self.selected_files()
        if files:
            self.select_scan(get_scan_number(files[0]) + direction)

    def _filter(self, text: str):
        text = text.lower()
        for item in self._scan_items():
            match = any(text in item.text(c).lower() for c in range(item.columnCount()))
            item.setHidden(bool(text) and not match)

    def _context_menu(self, pos):
        from .nexus_viewer import NexusViewer
        from .plots import open_plot_window, open_image_window
        from .common import show_window
        files = self.selected_files()
        if not files:
            return
        menu = QtWidgets.QMenu(self)
        menu.addAction('Copy path').triggered.connect(
            lambda: QtWidgets.QApplication.clipboard().setText('\n'.join(files)))
        menu.addAction('Copy scan number').triggered.connect(
            lambda: QtWidgets.QApplication.clipboard().setText(', '.join(str(get_scan_number(f)) for f in files)))
        menu.addAction('Open NeXus Viewer').triggered.connect(lambda: show_window(NexusViewer(files[0], self.config)))
        menu.addAction('Open Plot').triggered.connect(lambda: open_plot_window(files, self.config))
        menu.addAction('Open Image').triggered.connect(lambda: open_image_window(files[0], self.config))
        menu.exec(self.tree.viewport().mapToGlobal(pos))
