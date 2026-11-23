"""
Line plot and detector image panels for NeXus scan files
"""
import os

import numpy as np
import hdfmap
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from matplotlib.widgets import RectangleSelector

from mmg_toolbox.utils.file_functions import get_scan_number, read_tiff
from mmg_toolbox.fitting import multipeakfit
from mmg_toolbox.fitting.models import PEAK_MODELS
from .config import C, COLORMAPS
from .style import fit_to_screen, CURRENT
from .common import PlotCanvas, show_window, select_hdf_files


def menu_button(text: str, menu: QtWidgets.QMenu, tooltip: str = '') -> QtWidgets.QToolButton:
    """Tool button that opens a menu"""
    btn = QtWidgets.QToolButton(text=text + ' ▾', toolTip=tooltip)
    btn.setMenu(menu)
    btn.setPopupMode(QtWidgets.QToolButton.InstantPopup)
    return btn


def checkable(menu: QtWidgets.QMenu, text: str, checked: bool = False) -> QAction:
    action = menu.addAction(text)
    action.setCheckable(True)
    action.setChecked(checked)
    return action


def widget_action(menu: QtWidgets.QMenu, layout: QtWidgets.QLayout):
    """Put a layout of widgets inside a menu"""
    widget = QtWidgets.QWidget()
    widget.setLayout(layout)
    layout.setContentsMargins(12, 4, 12, 4)
    action = QtWidgets.QWidgetAction(menu)
    action.setDefaultWidget(widget)
    menu.addAction(action)


def axis_row(*pairs) -> QtWidgets.QHBoxLayout:
    """Row of (label, widget, extra) for compact axis selection"""
    row = QtWidgets.QHBoxLayout()
    for label, widget, extra in pairs:
        row.addWidget(QtWidgets.QLabel(label, objectName='muted'))
        row.addWidget(widget, stretch=1)
        row.addWidget(extra)
        row.addSpacing(8)
    return row


def load_xy(hdf_map: hdfmap.NexusMap, filename: str, x_expr: str, y_expr: str) -> tuple[np.ndarray, np.ndarray]:
    """Evaluate x and y expressions in a NeXus file"""
    with hdfmap.load_hdf(filename) as hdf:
        default = np.arange(hdf_map.scannables_length())
        x = np.asarray(hdf_map.eval(hdf, x_expr, default), dtype=float)
        y = np.asarray(hdf_map.eval(hdf, y_expr, default), dtype=float)
    return x, y


class LinePlot(QtWidgets.QWidget):
    """
    1D line plot of one or more scans with a choice of x and y axes.
    Axes can be chosen from the scannables or typed as an expression.
    With axis_list=True, a list beside the plot allows several y-axes to be plotted together.
    """

    def __init__(self, config: dict, parent=None, axis_list: bool = False):
        super().__init__(parent)
        self.config = config
        self.axis_list = axis_list
        self.files: list[str] = []
        self.map: hdfmap.NexusMap | None = None

        self.x_axis = QtWidgets.QComboBox(editable=True, minimumContentsLength=8)
        self.y_axis = QtWidgets.QComboBox(editable=True, minimumContentsLength=8)
        self.fix_x = QtWidgets.QCheckBox('Fix', toolTip='Keep this x-axis when changing scan')
        self.fix_y = QtWidgets.QCheckBox('Fix', toolTip='Keep this y-axis when changing scan')
        self.error = QtWidgets.QLabel(objectName='error', wordWrap=True)
        self.plot = PlotCanvas(self)
        self.index_line = None
        self.y_list = QtWidgets.QListWidget(toolTip='Select one or more values to plot (Ctrl/Shift for several)')
        self.y_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.y_list.setMaximumWidth(220)
        self.y_list.itemSelectionChanged.connect(self.on_list_select)

        # signal options menu
        options_menu = QtWidgets.QMenu(self)
        self.options = {name: checkable(options_menu, name) for name in ['Normalise', 'Log', 'Diff', 'Inverse']}
        # fit: click to toggle, arrow for settings
        self.n_peaks = QtWidgets.QSpinBox(minimum=1, maximum=10, value=1)
        self.model = QtWidgets.QComboBox()
        self.model.addItems(list(PEAK_MODELS))
        fit_menu = QtWidgets.QMenu(self)
        fit_form = QtWidgets.QFormLayout()
        fit_form.addRow('Peaks', self.n_peaks)
        fit_form.addRow('Model', self.model)
        widget_action(fit_menu, fit_form)
        self.fit = QtWidgets.QToolButton(text='Fit', checkable=True, toolTip='Fit peaks to the first line')
        self.fit.setMenu(fit_menu)
        self.fit.setPopupMode(QtWidgets.QToolButton.MenuButtonPopup)
        analysis_menu = QtWidgets.QMenu(self)
        analysis_menu.addAction('Multi-Scan Analysis').triggered.connect(self.open_multi_scan)
        analysis_menu.addAction('Peak Fitting').triggered.connect(self.open_peak_fit)

        self.x_axis.lineEdit().returnPressed.connect(self.update_plot)
        self.x_axis.activated.connect(self.update_plot)
        self.y_axis.lineEdit().returnPressed.connect(self.on_y_axis_change)
        self.y_axis.activated.connect(self.on_y_axis_change)
        for widget in (*self.options.values(), self.fit):
            widget.toggled.connect(self.update_plot)
        self.n_peaks.valueChanged.connect(self.update_plot)
        self.model.currentTextChanged.connect(self.update_plot)

        self.plot.toolbar_row.addWidget(menu_button('Options', options_menu, 'Signal options'))
        self.plot.toolbar_row.addWidget(self.fit)
        self.plot.toolbar_row.addWidget(menu_button('Analyse', analysis_menu, 'Open analysis windows'))

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(axis_row(('X', self.x_axis, self.fix_x), ('Y', self.y_axis, self.fix_y)))
        plot_row = QtWidgets.QHBoxLayout()
        plot_row.addWidget(self.plot, stretch=1)
        plot_row.addWidget(self.y_list)
        self.y_list.setHidden(not axis_list)
        layout.addLayout(plot_row, stretch=1)
        layout.addWidget(self.error)

    def update_files(self, files: list[str], hdf_map: hdfmap.NexusMap | None = None):
        self.files = files
        self.map = hdf_map or hdfmap.create_nexus_map(files[0])
        roi_totals = [f"{roi[0]}_total" for roi in self.config.get(C.roi, [])]
        names = list(self.map.scannables) + [n for n in roi_totals if n in self.map.combined]
        axes, signals = self.map.nexus_default_names()
        for combo, fix, default in [(self.x_axis, self.fix_x, axes), (self.y_axis, self.fix_y, signals)]:
            current = combo.currentText()
            combo.clear()
            combo.addItems(names)
            combo.setCurrentText(current if fix.isChecked() else next(iter(default), ''))
        self.y_list.blockSignals(True)
        self.y_list.clear()
        self.y_list.addItems(names)
        self.y_list.blockSignals(False)
        self.on_y_axis_change()

    def on_y_axis_change(self):
        """Select the y-axis in the list, adding it if it isn't there, then plot"""
        name = self.y_axis.currentText()
        items = self.y_list.findItems(name, Qt.MatchExactly)
        if not items and name:
            self.y_list.addItem(name)
            items = self.y_list.findItems(name, Qt.MatchExactly)
        self.y_list.blockSignals(True)
        self.y_list.clearSelection()
        for item in items:
            item.setSelected(True)
            self.y_list.scrollToItem(item)
        self.y_list.blockSignals(False)
        self.update_plot()

    def on_list_select(self):
        """Plot the y-axes selected in the list"""
        names = self.y_names()
        if names:
            self.y_axis.setCurrentText(names[0])
            self.update_plot()

    def y_names(self) -> list[str]:
        """y-axes to plot: those selected in the list, or the y-axis box"""
        if self.axis_list and self.y_list.selectedItems():
            return [item.text() for item in self.y_list.selectedItems()]
        return [self.y_axis.currentText()]

    def signal(self, name: str | None = None) -> str:
        """y-axis expression (by default from the y-axis box) including the selected options"""
        signal = name or self.y_axis.currentText()
        if self.options['Normalise'].isChecked():
            signal += self.config.get(C.normalise_factor, '')
        if self.options['Log'].isChecked():
            signal = f"log10({signal})"
        if self.options['Diff'].isChecked():
            signal = f"gradient({signal})"
        if self.options['Inverse'].isChecked():
            signal = f"1/({signal})"
        return signal

    def get_data(self) -> list[tuple[np.ndarray, np.ndarray, str]]:
        """Return [(x, y, label), ...] for each file and y-axis"""
        names = self.y_names()
        data = []
        for f in self.files:
            for name in names:
                label = f"#{get_scan_number(f)}" if len(self.files) > 1 else ''
                label = f"{label} {name}".strip() if len(names) > 1 else label
                data.append((*load_xy(self.map, f, self.x_axis.currentText(), self.signal(name)), label))
        return data

    def update_plot(self):
        if not self.files:
            return
        self.error.clear()
        self.plot.clear()
        ax = self.plot.ax
        try:
            data = self.get_data()
            for x, y, label in data:
                ax.plot(x, y, marker=self.config.get(C.plot_marker) or '.',
                        linestyle=self.config.get(C.plot_linestyle) or '-', label=label)
            if self.fit.isChecked():
                x, y, label = data[0]
                result = multipeakfit(x, y, npeaks=self.n_peaks.value(), model=self.model.currentText())
                ax.plot(*result.fit_data(), '--', color=CURRENT['muted'], label='fit')
            with hdfmap.load_hdf(self.files[0]) as hdf:
                ax.set_title(self.map.format_hdf(hdf, self.config.get(C.scan_title, '{filename}')), fontsize=10)
            ax.set_xlabel(self.x_axis.currentText())
            ax.set_ylabel(self.signal())
            if len(data) > 1 or self.fit.isChecked():
                ax.legend(frameon=False)
        except Exception as e:
            self.error.setText(f"Error: {e}")
        self.index_line = ax.axvline(np.nan, color='grey', alpha=0.5)
        self.plot.draw()

    def set_index(self, index: int):
        """Show a vertical line at the scan point index"""
        lines = self.plot.ax.get_lines()
        if self.index_line is None or not lines:
            return
        x = lines[0].get_xdata()
        if 0 <= index < len(x):
            self.index_line.set_xdata([x[index], x[index]])
            self.plot.draw()

    def scan_numbers(self) -> list[int]:
        return [get_scan_number(f) for f in self.files]

    def open_multi_scan(self):
        from .multi_scan import MultiScanAnalysis
        show_window(MultiScanAnalysis(self.config, self.scan_numbers(), self.x_axis.currentText(), self.signal()))

    def open_peak_fit(self):
        from .peak_fit import PeakFitting
        show_window(PeakFitting(self.config, self.scan_numbers(), self.x_axis.currentText(), self.signal()))


class ImagePlot(QtWidgets.QWidget):
    """
    Detector image at one point of a scan, with an index slider, image options and ROIs.
    Emits indexChanged(int) when the scan point changes.
    """
    indexChanged = Signal(int)

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.filename = ''
        self.map: hdfmap.NexusMap | None = None

        self.detector = QtWidgets.QComboBox(toolTip='Detector')
        self.slider = QtWidgets.QSlider(Qt.Horizontal, toolTip='Scan point')
        self.index = QtWidgets.QSpinBox(toolTip='Scan point')
        self.colormap = QtWidgets.QComboBox()
        self.colormap.addItems(COLORMAPS)
        self.colormap.setCurrentText(config.get(C.default_colormap, 'viridis'))
        self.fix_clim = QtWidgets.QCheckBox('Fix')
        self.cmin = QtWidgets.QDoubleSpinBox(maximum=1e12, decimals=1)
        self.cmax = QtWidgets.QDoubleSpinBox(maximum=1e12, decimals=1, value=1000)
        self.error = QtWidgets.QLabel(objectName='error', wordWrap=True)
        self.plot = PlotCanvas(self)

        options_menu = QtWidgets.QMenu(self)
        self.flip_x = checkable(options_menu, 'Flip x', config.get(C.image_flip_x, False))
        self.flip_y = checkable(options_menu, 'Flip y', config.get(C.image_flip_y, True))
        self.log = checkable(options_menu, 'Log scale', config.get(C.image_log, False))
        options_menu.addSeparator()
        clim = QtWidgets.QHBoxLayout()
        for widget in (self.fix_clim, self.cmin, self.cmax):
            clim.addWidget(widget)
        form = QtWidgets.QFormLayout()
        form.addRow('Colormap', self.colormap)
        form.addRow('Colour limits', clim)
        widget_action(options_menu, form)
        self.selector = RectangleSelector(self.plot.ax, self._roi_drawn, useblit=True, interactive=False)
        self.selector.set_active(False)

        self.slider.valueChanged.connect(self.index.setValue)
        self.index.valueChanged.connect(self.slider.setValue)
        self.index.valueChanged.connect(self.update_image)
        self.detector.currentTextChanged.connect(self.update_image)
        for widget in (self.flip_x, self.flip_y, self.log, self.fix_clim):
            widget.toggled.connect(self.update_image)
        for widget in (self.cmin, self.cmax):
            widget.valueChanged.connect(self.update_image)
        self.colormap.currentTextChanged.connect(self.update_image)

        draw_roi = QtWidgets.QToolButton(text='Draw ROI', checkable=True,
                                         toolTip='Drag a rectangle on the image to add a region of interest')
        draw_roi.toggled.connect(self.selector.set_active)
        for widget in (self.detector, menu_button('Options', options_menu, 'Image options'), draw_roi):
            self.plot.toolbar_row.addWidget(widget)
        scrubber = QtWidgets.QHBoxLayout()
        scrubber.setContentsMargins(8, 2, 8, 6)
        scrubber.addWidget(self.slider, stretch=1)
        scrubber.addWidget(self.index)
        self.plot.layout().addLayout(scrubber)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.plot, stretch=1)
        layout.addWidget(self.error)

    def update_file(self, filename: str, hdf_map: hdfmap.NexusMap | None = None):
        self.filename = filename
        self.map = hdf_map or hdfmap.create_nexus_map(filename)
        self.add_config_rois()
        n_points = max(self.map.scannables_length() - 1, 0)
        self.slider.setMaximum(n_points)
        self.index.setMaximum(n_points)
        self.detector.blockSignals(True)
        self.detector.clear()
        self.detector.addItems(list(self.map.image_data))
        self.detector.blockSignals(False)
        self.setVisible(bool(self.map.image_data))
        self.update_image()

    def add_config_rois(self):
        """Add ROIs from the config to the hdfmap, creating names like 'roi_total'"""
        for name, cen_i, cen_j, wid_i, wid_j, det_name in self.config.get(C.roi, []):
            if det_name in self.map.image_data:
                self.map.add_roi(name, cen_i, cen_j, wid_i, wid_j, det_name)

    def get_image(self) -> np.ndarray:
        index = self.index.value()
        image_index = self.map.get_image_index(index)
        self.map.set_image_path(self.map.image_data[self.detector.currentText()])
        with hdfmap.load_hdf(self.filename) as hdf:
            image = self.map.get_image(hdf, image_index)
        folder = os.path.dirname(self.filename)
        if isinstance(image, str):  # image stored as a TIFF file path
            image = read_tiff(os.path.join(folder, image))
        elif image.ndim == 0:  # image stored as a TIFF file number
            scan_number = get_scan_number(self.filename)
            image = read_tiff(os.path.join(folder, f"{scan_number}-{self.detector.currentText()}-files/{image:05.0f}.tif"))
        return np.asarray(image, dtype=float)

    def update_image(self):
        if not self.map or not self.detector.currentText():
            return
        self.error.clear()
        self.plot.clear()
        ax = self.plot.ax
        try:
            image = self.get_image()
            if self.log.isChecked():
                image = np.log10(image + 1)
            clim = (self.cmin.value(), self.cmax.value()) if self.fix_clim.isChecked() else None
            ax.imshow(image, cmap=self.colormap.currentText(), clim=clim, origin='upper')
            if self.flip_x.isChecked():
                ax.invert_xaxis()
            if self.flip_y.isChecked():
                ax.invert_yaxis()
            self.plot_rois()
            ax.set_title(f"{self.detector.currentText()} [{self.index.value()}]", fontsize=10)
            ax.grid(False)
        except Exception as e:
            self.error.setText(f"Error loading image: {e}")
        self.plot.draw()
        self.indexChanged.emit(self.index.value())

    def plot_rois(self):
        with hdfmap.load_hdf(self.filename) as hdf:
            for name, cen_i, cen_j, wid_i, wid_j, det_name in self.config.get(C.roi, []):
                if det_name == self.detector.currentText():
                    ci, cj, wi, wj = self.map.eval(hdf, f"{cen_i},{cen_j},{wid_i},{wid_j}")
                    x = [cj - wj // 2, cj + wj // 2, cj + wj // 2, cj - wj // 2, cj - wj // 2]
                    y = [ci - wi // 2, ci - wi // 2, ci + wi // 2, ci + wi // 2, ci - wi // 2]
                    self.plot.ax.plot(x, y, '-', color='#f97316', lw=2, scalex=False, scaley=False)
                    self.plot.ax.text(max(x), min(y), name, va='bottom')

    def _roi_drawn(self, press, release):
        """Add a new ROI to the config from a rectangle drawn on the image"""
        i0, i1 = sorted([press.ydata, release.ydata])
        j0, j1 = sorted([press.xdata, release.xdata])
        name = f"roi{len(self.config.get(C.roi, [])) + 1}"
        roi = (name, int((i0 + i1) / 2), int((j0 + j1) / 2), int(i1 - i0), int(j1 - j0), self.detector.currentText())
        self.config.setdefault(C.roi, []).append(roi)
        self.add_config_rois()
        self.update_image()


class PlotWindow(QtWidgets.QMainWindow):
    """Window with a line plot and/or detector image for NeXus files"""

    def __init__(self, files: list[str], config: dict, line: bool = True, image: bool = True):
        from .common import add_menus
        super().__init__()
        self.setWindowTitle('NeXus Plot' if line else 'NeXus Image')
        self.line = LinePlot(config) if line else None
        self.image = ImagePlot(config) if image else None
        splitter = QtWidgets.QSplitter(Qt.Vertical)
        for widget in (self.line, self.image):
            if widget:
                splitter.addWidget(widget)
        if self.line and self.image:
            self.image.indexChanged.connect(self.line.set_index)
        self.setCentralWidget(splitter)
        add_menus(self, {'File': {'Open': self.open_files}}, config)
        self.update_files(files)
        fit_to_screen(self, 800, 800 if line and image else 500)

    def open_files(self):
        files = select_hdf_files(self)
        if files:
            self.update_files(files)

    def update_files(self, files: list[str]):
        if not files:
            return
        hdf_map = hdfmap.create_nexus_map(files[0])
        if self.image:
            self.image.update_file(files[0], hdf_map)  # adds ROIs to the map first
        if self.line:
            self.line.update_files(files, hdf_map)


def open_plot_window(files: list[str], config: dict):
    return show_window(PlotWindow(files, config, line=True, image=False))


def open_image_window(filename: str, config: dict):
    return show_window(PlotWindow([filename], config, line=False, image=True))
