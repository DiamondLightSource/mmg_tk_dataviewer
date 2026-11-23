"""
Config Editor - edit the settings saved in the user's config file
"""
import json
import os

from PySide6 import QtWidgets

from .config import C, COLORMAPS, BEAMLINE_CONFIG, default_config, save_config
from .common import add_menus, show_window, edit_text, TextWindow, button
from .style import card, form, row, grid, fit_to_screen, scrollable

# config name: label, for simple text settings
TEXT_SETTINGS = {
    C.conf_file: 'Config File',
    C.beamline: 'Beamline',
    C.normalise_factor: 'Normalise by',
    C.plot_marker: 'Marker',
    C.plot_linestyle: 'Line style',
    C.metadata_label: 'Metadata label',
    C.scan_title: 'Plot title',
    C.default_metadata: 'Default metadata',
}
BOOL_SETTINGS = {C.image_log: 'Log scale', C.image_flip_y: 'Flip y', C.image_flip_x: 'Flip x'}
# config name: label, for settings stored as JSON (dicts and lists)
JSON_SETTINGS = {C.metadata_list: 'Metadata columns', C.roi: 'Image ROIs'}


class ConfigEditor(QtWidgets.QMainWindow):
    """Edit config values. 'Update' changes this session, 'Save' also writes the config file."""

    def __init__(self, config: dict):
        super().__init__()
        self.setWindowTitle('Config Editor')
        self.config = config
        self.text = {name: QtWidgets.QLineEdit() for name in TEXT_SETTINGS}
        self.bools = {name: QtWidgets.QCheckBox(label) for name, label in BOOL_SETTINGS.items()}
        self.colormap = QtWidgets.QComboBox()
        self.colormap.addItems(COLORMAPS)

        def fields(*names):
            return form(*[(TEXT_SETTINGS[name], self.text[name]) for name in names])
        images = fields()
        images.addRow(QtWidgets.QLabel('Colormap', objectName='muted'), self.colormap)
        images.addRow(QtWidgets.QLabel('Options', objectName='muted'), row(*self.bools.values(), None))
        advanced = grid([button('Metadata expression…', lambda: self.edit(C.metadata_string))] + [
            button(f"{label}…", lambda n=name: self.edit_json(n)) for name, label in JSON_SETTINGS.items()
        ], columns=3)
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        layout.addWidget(card(layout=fields(C.beamline, C.conf_file, C.normalise_factor, C.default_metadata),
                              title='General'))
        layout.addWidget(card(layout=fields(C.scan_title, C.metadata_label, C.plot_marker, C.plot_linestyle),
                              title='Plots'))
        layout.addWidget(card(layout=images, title='Images'))
        layout.addWidget(card(layout=advanced, title='Advanced'))
        layout.addStretch()
        layout.addLayout(row(None, button('Apply', self.update_config, self),
                             button('Save', self.save, self, primary=True)))
        self.setCentralWidget(scrollable(central))
        fit_to_screen(self, 620, 720)

        add_menus(self, {
            'Config': {
                'Reset': lambda: self.set_values(default_config(self.text[C.beamline].text())),
                'Delete config file': self.delete_file,
                'View config file': self.view_file,
            },
            'Copy from Beamline': {bl: lambda b=bl: self.copy_beamline(b) for bl in BEAMLINE_CONFIG},
        })
        self.set_values(config)

    def set_values(self, config: dict):
        for name, widget in self.text.items():
            value = config.get(name)
            widget.setText('' if value is None else str(value))
        for name, widget in self.bools.items():
            widget.setChecked(bool(config.get(name, False)))
        self.colormap.setCurrentText(config.get(C.default_colormap, 'viridis'))

    def update_config(self):
        for name, widget in self.text.items():
            self.config[name] = widget.text() or None
        for name, widget in self.bools.items():
            self.config[name] = widget.isChecked()
        self.config[C.default_colormap] = self.colormap.currentText()
        self.close()

    def save(self):
        self.update_config()
        save_config(self.config)

    def edit(self, name: str):
        new = edit_text(self, self.config.get(name, ''), name)
        if new is not None:
            self.config[name] = new

    def edit_json(self, name: str):
        new = edit_text(self, json.dumps(self.config.get(name), indent=2), name)
        if new is not None:
            self.config[name] = json.loads(new)

    def copy_beamline(self, beamline: str):
        """Copy a beamline's defaults, keeping the current beamline"""
        current = self.text[C.beamline].text()
        self.set_values({**self.config, **BEAMLINE_CONFIG[beamline], C.beamline: current})

    def delete_file(self):
        filename = self.config.get(C.conf_file)
        if filename and os.path.isfile(filename):
            answer = QtWidgets.QMessageBox.question(self, 'Config', f"Delete config file?\n{filename}")
            if answer == QtWidgets.QMessageBox.Yes:
                os.remove(filename)

    def view_file(self):
        filename = self.config.get(C.conf_file)
        if filename and os.path.isfile(filename):
            with open(filename) as f:
                show_window(TextWindow(f.read(), filename))
