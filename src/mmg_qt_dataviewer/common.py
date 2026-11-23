"""
Shared Qt helpers: application, menus, plot canvas, dialogs
"""
import os
import sys
import subprocess
import webbrowser

from PySide6 import QtWidgets
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT

from mmg_toolbox import version_info
from .style import apply_theme, setup_fonts, style_axes, fit_to_screen

DOCS_URL = 'https://diamondlightsource.github.io/mmg_toolbox'
WINDOWS = []  # keep references to open windows so they aren't garbage collected


def get_app(theme: str = 'system') -> QtWidgets.QApplication:
    """Return the running QApplication, creating and styling it if required"""
    app = QtWidgets.QApplication.instance()
    if app is None:
        # crisp rendering at fractional scaling, e.g. 125% or 150% laptop screens
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
        app = QtWidgets.QApplication(sys.argv)
        app.setApplicationName('MMG Data Viewer')
        setup_fonts(app)
        apply_theme(app, theme)
    return app


def show_window(window: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """Show a window, starting the event loop if this is the first one"""
    app = get_app()
    WINDOWS.append(window)
    window.destroyed.connect(lambda *_: WINDOWS.remove(window) if window in WINDOWS else None)
    window.setAttribute(Qt.WA_DeleteOnClose)
    window.show()
    if len(WINDOWS) == 1 and not app.property('running'):
        app.setProperty('running', True)
        app.exec()
    return window


def monospace() -> QFont:
    font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
    font.setFamilies(['JetBrains Mono', 'Cascadia Mono', 'Consolas', 'DejaVu Sans Mono', 'Liberation Mono',
                      'Noto Sans Mono', font.family()])
    font.setStyleHint(QFont.Monospace)
    return font


def add_menus(window: QtWidgets.QMainWindow, menus: dict, config: dict | None = None):
    """
    Add menus to a main window from a nested dict
        {'File': {'Open': open_fn, 'Recent': {'a': fn_a}}}
    The standard View, Config and Help menus are added at the end.
    """
    def set_theme(theme: str):
        apply_theme(get_app(), theme)
        if config is not None:  # remember the choice for next time
            from .config import save_config
            config['theme'] = theme
            save_config(config)
    menus['View'] = {**menus.get('View', {}), 'Theme': {
        'System': lambda: set_theme('system'),
        'Light': lambda: set_theme('light'),
        'Dark': lambda: set_theme('dark'),
    }}
    if config is not None:
        from .config_editor import ConfigEditor
        from .config import save_config
        menus['Config'] = {
            'Edit Config.': lambda: show_window(ConfigEditor(config)),
            'Save Config.': lambda: save_config(config),
        }
    menus['Help'] = {
        'Docs': lambda: webbrowser.open(DOCS_URL),
        'About': lambda: QtWidgets.QMessageBox.about(window, 'About', version_info()),
    }

    def add(menu: QtWidgets.QMenu, items: dict):
        for name, item in items.items():
            if isinstance(item, dict):
                add(menu.addMenu(name), item)
            else:
                menu.addAction(name).triggered.connect(lambda *_, fn=item: run_safely(window, fn))
    add(window.menuBar(), menus)


def run_safely(parent: QtWidgets.QWidget, fn, *args, **kwargs):
    """Run a function, showing any exception in a message box"""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        show_error(parent, e)


def show_error(parent: QtWidgets.QWidget | None, message):
    QtWidgets.QMessageBox.warning(parent, 'Error', str(message))


def select_folder(parent, directory: str = '') -> str:
    return QtWidgets.QFileDialog.getExistingDirectory(parent, 'Select folder', directory)


def select_hdf_files(parent, directory: str = '') -> list[str]:
    files, _ = QtWidgets.QFileDialog.getOpenFileNames(
        parent, 'Select files', directory, 'NeXus files (*.nxs *.h5 *.hdf *.hdf5);;All files (*)')
    return files


def open_terminal(directory: str):
    from mmg_toolbox.utils.env_functions import open_terminal as _open
    _open(f"cd {directory}")


def start_jupyter(directory: str | None = None, file: str | None = None):
    """Start a jupyter notebook server in the background"""
    command = [sys.executable, '-m', 'jupyter', 'notebook']
    command.append(file if file else f'--ServerApp.root_dir={directory or os.getcwd()}')
    subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)


def stop_jupyter():
    subprocess.run([sys.executable, '-m', 'jupyter', 'server', 'stop'])


def labelled(label: str, widget: QtWidgets.QWidget, *extra: QtWidgets.QWidget) -> QtWidgets.QHBoxLayout:
    """Horizontal layout with a label, a widget and optional extras"""
    row = QtWidgets.QHBoxLayout()
    row.addWidget(QtWidgets.QLabel(label))
    row.addWidget(widget, stretch=1)
    for w in extra:
        row.addWidget(w)
    return row


def button(text: str, fn, parent=None, primary: bool = False) -> QtWidgets.QPushButton:
    btn = QtWidgets.QPushButton(text)
    btn.setProperty('primary', primary)
    btn.clicked.connect(lambda *_: run_safely(parent or btn, fn))
    return btn


def tool_button(text: str, fn, tooltip: str = '') -> QtWidgets.QToolButton:
    btn = QtWidgets.QToolButton(text=text, toolTip=tooltip)
    btn.clicked.connect(lambda *_: run_safely(btn, fn))
    return btn


class PlotCanvas(QtWidgets.QFrame):
    """
    Matplotlib figure in a rounded panel, with a compact navigation toolbar.
    Other widgets can be added to the toolbar row with plot.toolbar_row.addWidget(...)
    """

    def __init__(self, parent=None, nrows: int = 1, ncols: int = 1, toolbar: bool = True):
        super().__init__(parent, objectName='plot')
        self.figure = Figure(figsize=(5, 3), layout='constrained')
        self.axes = self.figure.subplots(nrows, ncols, squeeze=False).flatten()
        self.ax = self.axes[0]
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setMinimumSize(200, 150)
        self.toolbar_row = QtWidgets.QHBoxLayout()
        self.toolbar_row.setContentsMargins(4, 2, 4, 0)
        if toolbar:
            bar = NavigationToolbar2QT(self.canvas, self, coordinates=False)
            bar.setIconSize(QSize(18, 18))
            self.toolbar_row.addWidget(bar)
        self.toolbar_row.addStretch()
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)
        layout.addLayout(self.toolbar_row)
        layout.addWidget(self.canvas, stretch=1)
        self.style_axes()

    def style_axes(self):
        style_axes(self.figure, self.axes)

    def clear(self):
        for ax in self.axes:
            ax.clear()
        self.style_axes()

    def draw(self):
        self.canvas.draw_idle()


class TextWindow(QtWidgets.QMainWindow):
    """Window showing (optionally editable) text"""

    def __init__(self, text: str, title: str = 'Text', editable: bool = False):
        super().__init__()
        self.setWindowTitle(title)
        self.text = QtWidgets.QPlainTextEdit(text)
        self.text.setFont(monospace())
        self.text.setReadOnly(not editable)
        self.text.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.setCentralWidget(self.text)
        fit_to_screen(self, 700, 500)


def edit_text(parent, text: str, title: str = 'Edit text') -> str | None:
    """Modal dialog to edit text, returns new text or None if cancelled"""
    dialog = QtWidgets.QDialog(parent)
    dialog.setWindowTitle(title)
    edit = QtWidgets.QPlainTextEdit(text)
    edit.setFont(monospace())
    buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout = QtWidgets.QVBoxLayout(dialog)
    layout.addWidget(edit)
    layout.addWidget(buttons)
    fit_to_screen(dialog, 600, 400)
    return edit.toPlainText() if dialog.exec() else None
