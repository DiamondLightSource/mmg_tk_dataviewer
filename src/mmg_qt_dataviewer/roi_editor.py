"""
ROI Editor - edit the image regions of interest (ROIs) in the config, like the tk RoiEditor
"""
from PySide6 import QtWidgets
from PySide6.QtCore import Qt

from .config import C, roi_params
from .common import button, show_error
from .style import row, fit_to_screen

# column name: tooltip, in the order of the config ROI values
COLUMNS = {
    'Name': "ROI name, creating signals like 'name_total'",
    'Centre i': 'Centre pixel along the first (vertical) image axis, or an expression such as pil3_centre_i',
    'Centre j': 'Centre pixel along the second (horizontal) image axis, or an expression',
    'Width i': 'Full width along the first image axis, in pixels',
    'Width j': 'Full width along the second image axis, in pixels',
    'Detector': 'Detector name',
    'Peak search': 'Centre the ROI on the largest pixel in the search region around Centre i, j',
    'Region i': 'Width of the peak search region along the first axis (blank for the whole image)',
    'Region j': 'Width of the peak search region along the second axis (blank for the whole image)',
}
PEAK = list(COLUMNS).index('Peak search')


def _number(text: str, name: str, required: bool = True) -> int | None:
    """Convert table text to an int, or None if it is empty and not required"""
    text = text.strip()
    if not text:
        if required:
            raise ValueError(f"{name} is empty")
        return None
    try:
        return int(float(text))
    except ValueError:
        raise ValueError(f"{name} must be a number, not '{text}'") from None


def _centre(text: str):
    """Centre pixels can be numbers or expressions evaluated in the file"""
    text = text.strip()
    try:
        return int(float(text))
    except ValueError:
        return text


class RoiEditor(QtWidgets.QDialog):
    """Table of the config ROIs. OK writes them to config[C.roi]."""

    def __init__(self, config: dict, detectors: list[str] | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Regions of Interest (ROIs)')
        self.config = config
        self.detectors = detectors or []
        self.table = QtWidgets.QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(list(COLUMNS))
        for n, tooltip in enumerate(COLUMNS.values()):
            self.table.horizontalHeaderItem(n).setToolTip(tooltip)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        for roi in config.get(C.roi) or []:
            if len(roi) in (6, 9):
                self.add_row(roi_params(roi))

        hint = QtWidgets.QLabel(
            "Each ROI adds signals such as 'name_total' to the plot. Centres can be pixel numbers "
            "or expressions. With Peak search, the ROI is centred on the largest pixel in the region around the centre.",
            objectName='muted', wordWrap=True)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addWidget(self.table, stretch=1)
        layout.addLayout(row(button('Add ROI', self.add_row, self), button('Duplicate', self.duplicate, self),
                             button('Remove', self.remove, self), None,
                             button('Copy code', self.copy_code, self)))
        layout.addWidget(buttons)
        fit_to_screen(self, 1000, 400)

    def add_row(self, roi: tuple | None = None):
        """Add an ROI to the table, or a new one with default values"""
        if not roi:
            name = f"roi{self.table.rowCount() + 1}"
            roi = (name, '', '', 30, 30, next(iter(self.detectors), 'IMAGE'), False, None, None)
        n = self.table.rowCount()
        self.table.insertRow(n)
        for column, value in enumerate(roi):
            if column == PEAK:
                item = QtWidgets.QTableWidgetItem()
                item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                item.setCheckState(Qt.Checked if value else Qt.Unchecked)
            else:
                item = QtWidgets.QTableWidgetItem('' if value is None else str(value))
            self.table.setItem(n, column, item)

    def duplicate(self):
        for n in sorted({index.row() for index in self.table.selectedIndexes()}):
            self.add_row(self.row_values(n, check=False))

    def remove(self):
        for n in sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(n)

    def row_values(self, n: int, check: bool = True) -> tuple:
        """Return the ROI config values in a table row"""
        text = [self.table.item(n, column).text() for column in range(len(COLUMNS))]
        name, cen_i, cen_j, wid_i, wid_j, detector, _, rgn_i, rgn_j = text
        peak = self.table.item(n, PEAK).checkState() == Qt.Checked
        if not check:
            return name, cen_i, cen_j, wid_i, wid_j, detector, peak, rgn_i, rgn_j
        if not name.strip():
            raise ValueError(f"ROI {n + 1} has no name")
        if not (cen_i.strip() and cen_j.strip()):
            raise ValueError(f"ROI '{name}' needs a centre")
        return (name.strip(), _centre(cen_i), _centre(cen_j), _number(wid_i, 'Width i'), _number(wid_j, 'Width j'),
                detector.strip(), peak, _number(rgn_i, 'Region i', False), _number(rgn_j, 'Region j', False))

    def rois(self) -> list[tuple]:
        rois = [self.row_values(n) for n in range(self.table.rowCount())]
        names = [roi[0] for roi in rois]
        if len(set(names)) < len(names):
            raise ValueError('ROI names must be different')
        return rois

    def copy_code(self):
        """Copy mmg_toolbox code that adds these ROIs to an Experiment"""
        code = ''.join(f"exp.add_roi({', '.join(repr(v) for v in roi)})\n" for roi in self.rois())
        QtWidgets.QApplication.clipboard().setText(code)

    def accept(self):
        try:
            self.config[C.roi] = self.rois()
        except ValueError as e:
            show_error(self, e)
            return
        super().accept()
