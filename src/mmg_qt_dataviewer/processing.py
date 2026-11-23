"""
Processing menu: multi-scan analysis, XMCD, scripts, notebooks, terminals and jupyter
"""
import os

from PySide6 import QtWidgets

from mmg_toolbox.utils.env_functions import get_processing_directory, get_notebook_directory
from mmg_toolbox.utils.file_functions import get_scan_number
from mmg_toolbox.scripts.scripts import generate_script, create_notebook, SCRIPTS, NOTEBOOKS, R
from .config import C
from .common import show_window, open_terminal, start_jupyter, stop_jupyter


def template_replacements(config: dict, folder: str, files: list[str], axes: tuple[str, str] = ('', '')) -> dict:
    """Values to fill into script and notebook templates"""
    values = {
        R.exp: folder,
        R.proc: config.get(C.current_proc) or get_processing_directory(folder),
        R.filepaths: ', '.join(f"'{f}'" for f in files),
        R.scannos: str([get_scan_number(f) for f in files]),
        R.beamline: config.get(C.beamline, ''),
        R.value: config.get(C.default_metadata, ''),
        R.title: f"Example Script: {os.path.basename(folder)}",
        R.description: 'Created by the Qt Data Viewer',
        R.xaxis: axes[0],
        R.yaxis: axes[1],
    }
    return values


def new_file_name(parent, folder: str, name: str, file_filter: str) -> str:
    filename, _ = QtWidgets.QFileDialog.getSaveFileName(parent, 'Save as', os.path.join(folder, name), file_filter)
    return filename


def create_script(parent, template: str, config: dict, folder: str, files: list[str], axes=('', '')):
    from .editors import PythonEditor
    values = template_replacements(config, folder, files, axes)
    filename = new_file_name(parent, values[R.proc], f"{template.replace(' ', '_')}.py", 'Python (*.py)')
    if filename:
        show_window(PythonEditor(generate_script(template, **values), filename))


def create_notebook_file(parent, template: str, config: dict, folder: str, files: list[str], axes=('', '')):
    values = template_replacements(config, folder, files, axes)
    filename = new_file_name(parent, values[R.proc], f"{template}.ipynb", 'Notebook (*.ipynb)')
    if filename:
        create_notebook(filename, template, **values)
        answer = QtWidgets.QMessageBox.question(parent, 'Notebook', f"Start Jupyter to view notebook?\n{filename}")
        if answer == QtWidgets.QMessageBox.Yes:
            start_jupyter(file=filename)


def processing_menu(parent, config: dict, folder_getter, files_getter=lambda: [],
                    axes_getter=lambda: ('', '')) -> dict:
    """Processing menu items, using functions that return the current folder, selected files and plot axes"""
    from .multi_scan import MultiScanAnalysis
    from .xmcd import XMCDVisualiser
    from .editors import PythonEditor

    def scan_numbers():
        return [get_scan_number(f) for f in files_getter()]

    def args():
        return config, folder_getter(), files_getter(), axes_getter()

    return {
        'Multi-Scan': lambda: show_window(MultiScanAnalysis(config, scan_numbers(), folder=folder_getter())),
        'XMCD Visualiser': lambda: show_window(XMCDVisualiser(config, scan_numbers(), folder=folder_getter())),
        'Script Editor': lambda: show_window(PythonEditor()),
        'Open a terminal': lambda: open_terminal(folder_getter()),
        'Start Jupyter (processing)': lambda: start_jupyter(get_processing_directory(folder_getter())),
        'Start Jupyter (notebooks)': lambda: start_jupyter(get_notebook_directory(folder_getter())),
        'Stop Jupyter servers': stop_jupyter,
        'Create Script': {
            f"{name}: {desc}": lambda n=name: create_script(parent, n, *args())
            for name, (_, desc) in SCRIPTS.items()
        },
        'Create Notebook': {
            f"{name}: {desc}": lambda n=name: create_notebook_file(parent, n, *args())
            for name, (_, desc) in NOTEBOOKS.items()
        },
    }
