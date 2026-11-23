"""
Shared Qt helpers: application, menus, plot canvas, dialogs
"""
import os
import sys
import subprocess
import webbrowser

from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT

from mmg_toolbox import version_info

DOCS_URL = 'https://diamondlightsource.github.io/mmg_toolbox'
WINDOWS = []  # keep references to open windows so they aren't garbage collected


def get_app() -> QtWidgets.QApplication:
    """Return the running QApplication, creating it if required"""
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)


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
    return QFontDatabase.systemFont(QFontDatabase.FixedFont)


def add_menus(window: QtWidgets.QMainWindow, menus: dict, config: dict | None = None):
    """
    Add menus to a main window from a nested dict
        {'File': {'Open': open_fn, 'Recent': {'a': fn_a}}}
    The standard Config and Help menus are added at the end.
    """
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


def button(text: str, fn, parent=None) -> QtWidgets.QPushButton:
    btn = QtWidgets.QPushButton(text)
    btn.clicked.connect(lambda *_: run_safely(parent or btn, fn))
    return btn


class PlotCanvas(QtWidgets.QWidget):
    """Matplotlib figure with navigation toolbar"""

    def __init__(self, parent=None, nrows: int = 1, ncols: int = 1, toolbar: bool = True):
        super().__init__(parent)
        self.figure = Figure(figsize=(6, 4), layout='tight')
        self.axes = self.figure.subplots(nrows, ncols, squeeze=False).flatten()
        self.ax = self.axes[0]
        self.canvas = FigureCanvasQTAgg(self.figure)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        if toolbar:
            layout.addWidget(NavigationToolbar2QT(self.canvas, self))
        layout.addWidget(self.canvas)

    def clear(self):
        for ax in self.axes:
            ax.clear()

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
        self.resize(700, 500)


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
    dialog.resize(600, 400)
    return edit.toPlainText() if dialog.exec() else None
