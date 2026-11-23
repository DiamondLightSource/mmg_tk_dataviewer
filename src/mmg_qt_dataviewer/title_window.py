"""
Beamline Data Viewer - the start-up window for choosing an experiment
"""
import os

from PySide6 import QtWidgets

from mmg_toolbox.utils.env_functions import get_dls_visits
from mmg_toolbox.utils.file_functions import folder_summary_line
from mmg_toolbox.beamline_metadata.default_scripts import create_beamline_scripts
from .config import C, BEAMLINE_CONFIG, get_config, save_config
from .common import add_menus, show_window, select_folder, button
from .style import card, form, row, heading, fit_to_screen
from .processing import processing_menu


class TitleWindow(QtWidgets.QMainWindow):
    """Choose a beamline visit and the data, analysis and notebook folders"""

    def __init__(self, beamline: str | None = None):
        super().__init__()
        self.setWindowTitle('Beamline Data Viewer')
        self.config = get_config(beamline=beamline)
        self.visits: dict[str, str] = {}

        self.title = heading()
        self.visit = QtWidgets.QComboBox()
        self.visit.activated.connect(lambda: self.set_data_dir(self.visits[self.visit.currentText()]))
        self.summary = QtWidgets.QLabel(objectName='muted', wordWrap=True)
        self.data_dir = QtWidgets.QLineEdit(placeholderText='Folder containing NeXus scan files')
        self.data_dir.returnPressed.connect(lambda: self.set_data_dir(self.data_dir.text()))
        self.proc_dir = QtWidgets.QLineEdit(placeholderText='Folder for processing scripts and outputs')
        self.notebook_dir = QtWidgets.QLineEdit(placeholderText='Folder of processed Jupyter notebooks')

        def browse(line_edit: QtWidgets.QLineEdit, setter=None):
            def fn():
                folder = select_folder(self, line_edit.text())
                if folder:
                    (setter or line_edit.setText)(folder)
            return row(line_edit, button('Browse', fn), stretch=0)

        experiment = card(layout=form(
            ('Visit', row(self.visit, button('Check files', lambda: self.open_browser('nexus'), self), stretch=0)),
            ('', self.summary),
        ), title='Experiment')
        folders = card(layout=form(
            ('Data', browse(self.data_dir, self.set_data_dir)),
            ('Analysis', browse(self.proc_dir)),
            ('Notebooks', browse(self.notebook_dir)),
        ), title='Folders')
        actions = QtWidgets.QGridLayout()
        for n, (text, fn, primary) in enumerate([
                ('Open Data Viewer', self.open_data_viewer, True),
                ('Processing', self.open_multi_scan, False),
                ('Notebook Browser', lambda: self.open_browser('jupyter'), False),
                ('Log Viewer', self.open_log_viewer, False)]):
            actions.addWidget(button(text, fn, self, primary=primary), 0, n)

        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(12)
        layout.addWidget(self.title)
        layout.addWidget(QtWidgets.QLabel('Choose an experiment, then open the data viewer or a processing tool.',
                                          objectName='muted', wordWrap=True))
        layout.addWidget(experiment)
        layout.addWidget(folders)
        layout.addLayout(actions)
        layout.addStretch()
        self.setCentralWidget(central)
        fit_to_screen(self, 860, 400)

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
        self.title.setText(f"{beamline.upper()} Data Viewer")
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
