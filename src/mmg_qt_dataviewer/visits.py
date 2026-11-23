"""
DLS Visits - recent visits for each beamline
"""
import os
from datetime import datetime

from PySide6 import QtWidgets

from mmg_toolbox.utils.env_functions import get_dls_visits, get_notebook_directory, scan_number_mapping
from .config import BEAMLINE_CONFIG
from .common import add_menus, show_window


def latest(files: dict[int, str]) -> str:
    """Count of files and the number and time of the latest one"""
    if not files:
        return '0'
    number, path = list(files.items())[-1]
    return f"{len(files)}, #{number} ({datetime.fromtimestamp(os.path.getmtime(path)):%Y-%m-%d %H:%M})"


class VisitViewer(QtWidgets.QMainWindow):
    """Table of recent visits per beamline, with scan and notebook counts"""

    def __init__(self, config: dict, open_visit=None, max_visits: int = 5):
        super().__init__()
        self.setWindowTitle('DLS Visits')
        self.config = config
        self.open_visit = open_visit
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(['Visit', 'Scans', 'Notebooks', 'Folder'])
        self.tree.itemDoubleClicked.connect(self.on_double_click)
        for beamline in BEAMLINE_CONFIG:
            parent = QtWidgets.QTreeWidgetItem(self.tree, [beamline])
            for visit, folder in list(get_dls_visits(beamline, max_visits=max_visits).items()):
                scans = scan_number_mapping(folder)
                notebooks = scan_number_mapping(get_notebook_directory(folder), extension='.ipynb')
                QtWidgets.QTreeWidgetItem(parent, [visit, latest(scans), latest(notebooks), folder])
            parent.setExpanded(True)
        self.setCentralWidget(self.tree)
        self.resize(1000, 600)
        add_menus(self, {})

    def on_double_click(self, item: QtWidgets.QTreeWidgetItem):
        folder = item.text(3)
        if not folder:
            return
        if self.open_visit:
            self.open_visit(folder)
        else:
            from .data_viewer import DataViewer
            show_window(DataViewer(folder, self.config))
