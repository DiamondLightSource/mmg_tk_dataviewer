"""
Beamline Data Viewer - the start-up window for choosing an experiment
"""
import os

from PySide6 import QtWidgets

from mmg_toolbox.utils.env_functions import get_dls_visits
from mmg_toolbox.utils.file_functions import folder_summary_line
from mmg_toolbox.beamline_metadata.default_scripts import create_beamline_scripts
from .config import C, BEAMLINE_CONFIG, get_config, save_config
from .common import add_menus, show_window, select_folder, button, labelled
from .processing import processing_menu


class TitleWindow(QtWidgets.QMainWindow):
    """Choose a beamline visit and the data, analysis and notebook folders"""

    def __init__(self, beamline: str | None = None):
        super().__init__()
        self.setWindowTitle('Beamline Data Viewer')
        self.config = get_config(beamline=beamline)
        self.visits: dict[str, str] = {}

        self.title = QtWidgets.QLabel(styleSheet='font-size: 18pt; font-weight: bold')
        self.visit = QtWidgets.QComboBox()
        self.visit.activated.connect(lambda: self.set_data_dir(self.visits[self.visit.currentText()]))
        self.summary = QtWidgets.QLabel()
        self.data_dir = QtWidgets.QLineEdit()
        self.data_dir.returnPressed.connect(lambda: self.set_data_dir(self.data_dir.text()))
        self.proc_dir = QtWidgets.QLineEdit()
        self.notebook_dir = QtWidgets.QLineEdit()

        def browse(line_edit: QtWidgets.QLineEdit, setter=None):
            def fn():
                folder = select_folder(self, line_edit.text())
                if folder:
                    (setter or line_edit.setText)(folder)
            return button('Browse', fn)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addWidget(button('Data Viewer', self.open_data_viewer, self))
        buttons.addWidget(button('Log Viewer', self.open_log_viewer, self))
        buttons.addWidget(button('Notebook Browser', lambda: self.open_browser('jupyter'), self))
        buttons.addWidget(button('Processing', self.open_multi_scan, self))
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.addWidget(self.title)
        layout.addLayout(labelled('Visit:', self.visit, button('Check', lambda: self.open_browser('nexus'), self)))
        layout.addWidget(self.summary)
        layout.addLayout(labelled('Data Dir:', self.data_dir, browse(self.data_dir, self.set_data_dir)))
        layout.addLayout(labelled('Analysis Dir:', self.proc_dir, browse(self.proc_dir)))
        layout.addLayout(labelled('Notebook Dir:', self.notebook_dir, browse(self.notebook_dir)))
        layout.addLayout(buttons)
        self.setCentralWidget(central)
        self.resize(800, 250)

        add_menus(self, {
            'File': {
                'File Browser': lambda: self.open_browser('any'),
                'NeXus File Browser': lambda: self.open_browser('nexus'),
                'NeXus File Viewer': self.open_nexus_viewer,
                'Jupyter Browser': lambda: self.open_browser('jupyter'),
                'Data Viewer': self.open_data_viewer,
                'Log Viewer': self.open_log_viewer,
                'Visit Viewer': self.open_visit_viewer,
            },
            'Processing': {
                **processing_menu(self, self.config, self.data_dir.text),
                'Create Example Scripts': self.create_scripts,
            },
            'Recent Folders': {
                folder: lambda f=folder: self.set_data_dir(f)
                for folder in self.config.get(C.recent_data_directories, [])
            },
            'Beamline': {bl: lambda b=bl: self.choose_beamline(b) for bl in BEAMLINE_CONFIG},
        }, self.config)
        self.choose_beamline(self.config.get(C.beamline) or 'i16')

    def choose_beamline(self, beamline: str):
        self.config.update(BEAMLINE_CONFIG.get(beamline, {}))
        self.title.setText(f"MMG Toolbox: {beamline}")
        self.visits = get_dls_visits(beamline)
        default = self.config.get(C.default_directory, '.')
        self.visits['default'] = default if os.path.isdir(default) else os.path.expanduser('~')
        self.visit.clear()
        self.visit.addItems(list(self.visits))
        self.set_data_dir(self.visits[self.visit.currentText()])

    def set_data_dir(self, folder: str):
        self.data_dir.setText(folder)
        self.summary.setText(folder_summary_line(folder) if os.access(folder, os.R_OK) else 'Folder is not readable')
        proc = os.path.join(folder, 'processing')
        notebooks = os.path.join(folder, 'processed', 'notebooks')
        self.proc_dir.setText(proc if os.path.isdir(proc) else '')
        self.notebook_dir.setText(notebooks if os.path.isdir(notebooks) else '')

    def update_config(self):
        """Store current folders in the config"""
        self.config[C.current_dir] = self.data_dir.text()
        self.config[C.current_proc] = self.proc_dir.text()
        self.config[C.current_nb] = self.notebook_dir.text()

    def open_data_viewer(self):
        from .data_viewer import DataViewer
        folder = self.data_dir.text()
        recent = [f for f in self.config.get(C.recent_data_directories, []) if f != folder]
        self.config[C.recent_data_directories] = [folder] + recent[:9]
        self.update_config()
        save_config(self.config)
        show_window(DataViewer(folder, self.config))

    def open_browser(self, mode: str):
        from .file_browser import FileBrowser
        folder = self.notebook_dir.text() if mode == 'jupyter' else self.data_dir.text()
        show_window(FileBrowser(folder or self.data_dir.text(), mode, self.config))

    def open_nexus_viewer(self):
        from .nexus_viewer import NexusViewer
        viewer = show_window(NexusViewer(config=self.config))
        viewer.browse()

    def open_log_viewer(self):
        from .editors import open_log_viewer
        open_log_viewer(self.data_dir.text())

    def open_multi_scan(self):
        from .multi_scan import MultiScanAnalysis
        self.update_config()
        show_window(MultiScanAnalysis(self.config, folder=self.data_dir.text()))

    def open_visit_viewer(self):
        from .visits import VisitViewer
        show_window(VisitViewer(self.config, self.set_data_dir))

    def create_scripts(self):
        beamline = self.config.get(C.beamline, '')
        folder = self.proc_dir.text()
        answer = QtWidgets.QMessageBox.question(
            self, 'Create Example Scripts', f"Create example scripts for {beamline.upper()} in:\n{folder}")
        if answer == QtWidgets.QMessageBox.Yes:
            create_beamline_scripts(beamline, folder)
