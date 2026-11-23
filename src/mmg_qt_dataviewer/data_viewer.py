"""
NeXus Data Viewer - browse the scans in an experiment folder
"""
import os

import hdfmap
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, QTimer

from mmg_toolbox.utils.env_functions import get_scan_notebooks, get_notebook_directory
from mmg_toolbox.utils.file_functions import get_scan_number
from .config import C
from .common import add_menus, show_window, button, monospace, edit_text, run_safely, TextWindow
from .scan_list import ScanList
from .plots import LinePlot, ImagePlot
from .processing import processing_menu


class DetailsPanel(QtWidgets.QWidget):
    """Text summary of a scan, a python terminal and the scan's notebooks"""

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.filename = ''
        self.map: hdfmap.NexusMap | None = None

        self.text = QtWidgets.QPlainTextEdit(readOnly=True, font=monospace())
        self.text.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.text.setContextMenuPolicy(Qt.ActionsContextMenu)
        edit_action = self.text.addAction('Edit text')
        edit_action.triggered.connect(self.edit_expression)
        view_action = self.text.addAction('View metadata')
        view_action.triggered.connect(self.view_metadata)

        self.terminal = QtWidgets.QPlainTextEdit(readOnly=True, font=monospace(), maximumHeight=80)
        self.command = QtWidgets.QLineEdit(placeholderText='>> expression, e.g. mean(axes)')
        self.command.returnPressed.connect(self.run_command)
        self.notebooks = QtWidgets.QComboBox()

        terminal_row = QtWidgets.QHBoxLayout()
        terminal_row.addWidget(self.command)
        terminal_row.addWidget(button('CLS', self.terminal.clear))
        notebook_row = QtWidgets.QHBoxLayout()
        notebook_row.addWidget(self.notebooks, stretch=1)
        notebook_row.addWidget(button('Open', self.open_notebook, self))
        notebook_row.addWidget(button('Reprocess', self.reprocess_notebook, self))
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.text, stretch=1)
        layout.addWidget(self.terminal)
        layout.addLayout(terminal_row)
        layout.addLayout(notebook_row)

    def update_file(self, filename: str, hdf_map: hdfmap.NexusMap):
        self.filename = filename
        self.map = hdf_map
        self.update_text()
        self.notebooks.clear()
        for notebook in get_scan_notebooks(filename):
            self.notebooks.addItem(os.path.basename(notebook), notebook)

    def update_text(self):
        try:
            with hdfmap.load_hdf(self.filename) as hdf:
                self.text.setPlainText(self.map.format_hdf(hdf, self.config.get(C.metadata_string, '')))
        except Exception as e:
            self.text.setPlainText(f"Error: {e}")

    def edit_expression(self):
        new = edit_text(self, self.config.get(C.metadata_string, ''), 'Metadata expression')
        if new is not None:
            self.config[C.metadata_string] = new
            self.update_text()

    def view_metadata(self):
        with hdfmap.load_hdf(self.filename) as hdf:
            text = '\n'.join(f"{name} = {self.map.get_string(hdf, name)}" for name in self.map.values)
        show_window(TextWindow(text, 'Metadata'))

    def run_command(self):
        expression = self.command.text()
        try:
            with hdfmap.load_hdf(self.filename) as hdf:
                result = self.map.eval(hdf, expression)
        except Exception as e:
            result = e
        self.terminal.appendPlainText(f">> {expression}\n{result}")
        self.command.clear()

    def open_notebook(self):
        from mmg_toolbox.utils.nb_runner import view_jupyter_notebook
        if self.notebooks.currentData():
            view_jupyter_notebook(self.notebooks.currentData())

    def reprocess_notebook(self):
        from mmg_toolbox.utils.nb_runner import reprocess_notebook
        if self.notebooks.currentData():
            reprocess_notebook(self.notebooks.currentData())


class DataViewer(QtWidgets.QMainWindow):
    """Scan list, scan details, line plot and detector image for an experiment folder"""

    def __init__(self, folder: str | None = None, config: dict | None = None):
        from .config import get_config
        super().__init__()
        self.setWindowTitle('NeXus Data Viewer')
        self.config = config or get_config()

        self.scans = ScanList(self.config)
        self.details = DetailsPanel(self.config)
        self.line = LinePlot(self.config)
        self.image = ImagePlot(self.config)
        self.image.indexChanged.connect(self.line.set_index)
        self.scans.selectionChanged.connect(lambda files: run_safely(self, self.on_select, files))

        left = QtWidgets.QSplitter(Qt.Vertical)
        left.addWidget(self.scans)
        left.addWidget(self.details)
        right = QtWidgets.QSplitter(Qt.Vertical)
        right.addWidget(self.line)
        right.addWidget(self.image)
        main = QtWidgets.QSplitter()
        main.addWidget(left)
        main.addWidget(right)
        main.setStretchFactor(1, 2)
        self.setCentralWidget(main)
        self.resize(1400, 900)

        add_menus(self, {
            'File': {
                'New Data Viewer': lambda: show_window(DataViewer(config=self.config)),
                'Add Folder': self.scans.browse_folder,
                'File Browser': lambda: self._browser('any'),
                'NeXus File Browser': lambda: self._browser('nexus'),
                'Jupyter Browser': lambda: self._browser('jupyter'),
                'Log Viewer': self.open_log_viewer,
            },
            'Processing': processing_menu(self, self.config, self.scans.current_folder, self.scans.selected_files,
                                          lambda: (self.line.x_axis.currentText(), self.line.signal())),
        }, self.config)

        if folder:
            self.scans.add_folder(folder)
            QTimer.singleShot(100, self.scans.select_first)

    def on_select(self, files: list[str]):
        if not files:
            return
        self.config[C.current_dir] = os.path.dirname(files[0])
        self.scans.number.setValue(get_scan_number(files[0]))
        hdf_map = hdfmap.create_nexus_map(files[0])
        self.image.update_file(files[0], hdf_map)  # adds ROIs to the map
        self.details.update_file(files[0], hdf_map)
        self.line.update_files(files, hdf_map)

    def _browser(self, mode: str):
        from .file_browser import FileBrowser
        folder = self.scans.current_folder()
        if mode == 'jupyter':
            folder = get_notebook_directory(folder)
        show_window(FileBrowser(folder, mode, self.config))

    def open_log_viewer(self):
        from .editors import open_log_viewer
        open_log_viewer(self.scans.current_folder())
