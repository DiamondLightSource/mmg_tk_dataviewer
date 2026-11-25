"""
Generate screenshots of the main Qt Data Viewer windows (light theme)

    $ uv run python docs/generate_qt_ui_images.py [OUTPUT_FOLDER]

Windows are rendered off-screen on a simulated 1920x1080 screen, so no display is needed.
Example scans are generated with the test fixture in tests/test_qt_dataviewer.py.
"""
import os
import sys
import json
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, 'docs', 'images', 'mmg_qt_dataviewer')
DATA = os.path.join(tempfile.gettempdir(), 'dls', 'i16', 'data', '2026', 'mm12345-1')  # example visit folder

# off-screen Qt platform with a fixed screen size, set before PySide6 is imported
screen = {"screens": [{"name": "s", "x": 0, "y": 0, "width": 1920, "height": 1080, "logicalDpi": 96, "dpr": 1}]}
screen_file = os.path.join(tempfile.mkdtemp(), 'screen.json')
with open(screen_file, 'w') as f:
    json.dump(screen, f)
os.environ['QT_QPA_PLATFORM'] = f'offscreen:configfile={screen_file}'
sys.path[:0] = [os.path.join(REPO, 'src'), REPO]

from PySide6.QtCore import Qt
from tests.test_qt_dataviewer import make_scan
from mmg_qt_dataviewer.common import get_app
from mmg_qt_dataviewer.config import default_config, C
from mmg_qt_dataviewer import (data_viewer, title_window, nexus_viewer, multi_scan, peak_fit, xmcd,
                               config_editor, file_browser, plots, editors, processing)

# example data
os.makedirs(DATA, exist_ok=True)
os.makedirs(OUTPUT, exist_ok=True)
for n in range(1001, 1021):
    filename = os.path.join(DATA, f'i16-{n}.nxs')
    if not os.path.exists(filename):
        make_scan(filename, n)
FILES = [os.path.join(DATA, 'i16-1005.nxs')]

app = get_app(theme='light')
config = default_config('i16')
config[C.current_dir] = DATA
config[C.roi] = []
config[C.metadata_string] = '{filename}\n{filepath}\ncmd = {scan_command}\nshape = {total.shape}'


def python_editor():
    values = processing.template_replacements(config, DATA, FILES, ('x', 'total'))
    script = processing.generate_script(next(iter(processing.SCRIPTS)), **values)
    return editors.PythonEditor(script, os.path.join(DATA, 'example_script.py'))


WINDOWS = {
    'title_window': lambda: title_window.TitleWindow('i16'),
    'data_viewer': lambda: data_viewer.DataViewer(DATA, config),
    'nexus_viewer': lambda: nexus_viewer.NexusViewer(FILES[0], config),
    'plot_window': lambda: plots.PlotWindow(FILES, config, line=True, image=False),
    'image_window': lambda: plots.PlotWindow(FILES, config, line=False, image=True),
    'multi_scan_analysis': lambda: multi_scan.MultiScanAnalysis(config, [1001, 1002, 1003], 'x', 'total', DATA),
    'peak_fitting': lambda: peak_fit.PeakFitting(config, list(range(1001, 1011)), 'x', 'total', DATA,
                                                 'entry_identifier'),
    'xmcd_visualiser': lambda: xmcd.XMCDVisualiser(config, [1001], DATA),
    'file_browser': lambda: file_browser.FileBrowser(DATA, 'nexus', config),
    'python_editor': python_editor,
    'config_editor': lambda: config_editor.ConfigEditor(dict(config)),
}


def prepare(name, window):
    """Put each window into an interesting state before the screenshot"""
    if name == 'title_window':
        window.set_data_dir(DATA)
    elif name == 'data_viewer':
        while window.scans._pending:
            window.scans._load_next_metadata()
        window.scans.select_first()
    elif name == 'nexus_viewer':
        window.tree.expandAll()
        window.tree.setCurrentItem(window.tree.findItems('total', Qt.MatchRecursive)[0])
        window.expression.setText('mean(total)')
        window.evaluate()
    elif name == 'peak_fitting':
        window.fit_all()


for name, make in WINDOWS.items():
    window = make()
    window.show()
    app.processEvents()
    prepare(name, window)
    for _ in range(30):
        app.processEvents()
    filename = os.path.join(OUTPUT, f'{name}.png')
    window.grab().save(filename)
    print(f"{name}: {window.width()} x {window.height()} -> {filename}")
    window.close()
