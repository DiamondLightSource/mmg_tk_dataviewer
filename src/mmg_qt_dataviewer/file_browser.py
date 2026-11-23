"""
File browsers: any files, NeXus files (with a dataset value column) or Jupyter notebooks
"""
import os

import h5py
import hdfmap
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, QDir

from .common import add_menus, show_window, select_folder, button, open_terminal, start_jupyter

TITLES = {'any': 'File Browser', 'nexus': 'NeXus File Browser', 'jupyter': 'Jupyter Notebook Browser'}
FILTERS = {'any': [], 'nexus': ['*.nxs', '*.h5', '*.hdf', '*.hdf5'], 'jupyter': ['*.ipynb', '*.html']}


class FileBrowser(QtWidgets.QMainWindow):
    """Folder tree with navigation, search and right-click actions"""

    def __init__(self, folder: str | None = None, mode: str = 'any', config: dict | None = None):
        super().__init__()
        self.setWindowTitle(TITLES[mode])
        self.mode = mode
        self.config = config or {}

        self.model = QtWidgets.QFileSystemModel()
        self.model.setRootPath('')
        self.model.setNameFilters(FILTERS[mode])
        self.model.setNameFilterDisables(False)
        self.tree = QtWidgets.QTreeView()
        self.tree.setModel(self.model)
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(3, Qt.DescendingOrder)  # newest first
        self.tree.setColumnWidth(0, 300)
        self.tree.doubleClicked.connect(self.on_double_click)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.context_menu)

        self.folder = QtWidgets.QLineEdit()
        self.folder.returnPressed.connect(lambda: self.set_folder(self.folder.text()))
        self.show_hidden = QtWidgets.QCheckBox('Show hidden')
        self.show_hidden.toggled.connect(self.update_filter)
        self.search = QtWidgets.QLineEdit(placeholderText='Filter filenames, e.g. *1234*')
        self.search.textChanged.connect(self.update_filter)

        # NeXus mode: show the value of a dataset for the selected file
        self.dataset = QtWidgets.QLineEdit('(cmd|user_command|scan_command)')
        self.dataset_value = QtWidgets.QLabel(wordWrap=True)
        self.tree.selectionModel().currentChanged.connect(self.show_dataset)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(button('Up', lambda: self.set_folder(os.path.dirname(self.folder.text()))))
        top.addWidget(button('Home', lambda: self.set_folder(os.path.expanduser('~'))))
        top.addWidget(self.folder, stretch=1)
        top.addWidget(button('Browse', self.browse))
        bottom = QtWidgets.QHBoxLayout()
        bottom.addWidget(self.search, stretch=1)
        bottom.addWidget(self.show_hidden)
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.addLayout(top)
        layout.addLayout(bottom)
        layout.addWidget(self.tree)
        if mode == 'nexus':
            row = QtWidgets.QHBoxLayout()
            row.addWidget(QtWidgets.QLabel('Dataset:'))
            row.addWidget(self.dataset, stretch=1)
            layout.addLayout(row)
            layout.addWidget(self.dataset_value)
        self.setCentralWidget(central)
        self.resize(900, 700)
        add_menus(self, {})
        self.set_folder(folder or os.path.expanduser('~'))

    def set_folder(self, folder: str):
        if os.path.isdir(folder):
            self.folder.setText(folder)
            self.tree.setRootIndex(self.model.index(folder))

    def browse(self):
        folder = select_folder(self, self.folder.text())
        if folder:
            self.set_folder(folder)

    def update_filter(self):
        filters = QDir.AllEntries | QDir.NoDotAndDotDot | QDir.AllDirs
        if self.show_hidden.isChecked():
            filters |= QDir.Hidden
        self.model.setFilter(filters)
        search = self.search.text()
        self.model.setNameFilters([search] if search else FILTERS[self.mode])

    def selected_path(self) -> str:
        return self.model.filePath(self.tree.currentIndex())

    def on_double_click(self, index):
        path = self.model.filePath(index)
        if os.path.isdir(path):
            self.set_folder(path)
        else:
            self.open_file(path)

    def open_file(self, path: str):
        from .nexus_viewer import NexusViewer
        if path.endswith('.ipynb'):
            start_jupyter(file=path)
        elif path.endswith('.html'):
            import webbrowser
            webbrowser.open(f"file://{path}")
        elif h5py.is_hdf5(path):
            show_window(NexusViewer(path, self.config))
        else:
            from .common import TextWindow
            with open(path, errors='replace') as f:
                show_window(TextWindow(f.read(100_000), os.path.basename(path)))

    def show_dataset(self, index):
        path = self.model.filePath(index)
        if self.mode != 'nexus' or not os.path.isfile(path):
            return
        try:
            hdf_map = hdfmap.create_nexus_map(path)
            with hdfmap.load_hdf(path) as hdf:
                self.dataset_value.setText(str(hdf_map.eval(hdf, self.dataset.text())))
        except Exception as e:
            self.dataset_value.setText(f"Error: {e}")

    def context_menu(self, pos):
        from .plots import open_plot_window, open_image_window
        path = self.selected_path()
        folder = path if os.path.isdir(path) else os.path.dirname(path)
        menu = QtWidgets.QMenu(self)
        menu.addAction('Copy path').triggered.connect(lambda: QtWidgets.QApplication.clipboard().setText(path))
        menu.addAction('Open terminal here').triggered.connect(lambda: open_terminal(folder))
        menu.addAction('Start Jupyter here').triggered.connect(lambda: start_jupyter(folder))
        if os.path.isfile(path):
            menu.addAction('Open').triggered.connect(lambda: self.open_file(path))
            if self.mode == 'nexus':
                menu.addAction('Open Plot').triggered.connect(lambda: open_plot_window([path], self.config))
                menu.addAction('Open Image').triggered.connect(lambda: open_image_window(path, self.config))
        menu.exec(self.tree.viewport().mapToGlobal(pos))
