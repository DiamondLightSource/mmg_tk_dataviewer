"""
Smoke tests for the Qt dataviewer: open each window on a small generated NeXus file.
Skipped if PySide6 (or the system libraries it needs) can't be loaded.
"""
import os

import numpy as np
import h5py
import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
QtWidgets = pytest.importorskip('PySide6.QtWidgets', exc_type=ImportError)


def make_scan(filename: str, scan_number: int, n_points: int = 11):
    """Write a minimal NeXus scan with a line scan and a detector image"""
    with h5py.File(filename, 'w') as nx:
        entry = nx.create_group('entry')
        entry.attrs['NX_class'] = 'NXentry'
        entry.attrs['default'] = 'data'
        entry.create_dataset('scan_command', data='scan x 0 1 0.1 pil 1')
        entry.create_dataset('entry_identifier', data=str(scan_number))
        x = np.linspace(0, 1, n_points)
        y = 100 * np.exp(-((x - 0.5) / 0.1) ** 2) + 5
        meas = entry.create_group('measurement')
        meas.attrs['NX_class'] = 'NXcollection'
        meas.create_dataset('x', data=x)
        meas.create_dataset('total', data=y)
        det = entry.create_group('instrument/pil')
        entry['instrument'].attrs['NX_class'] = 'NXinstrument'
        det.attrs['NX_class'] = 'NXdetector'
        det.create_dataset('data', data=np.random.rand(n_points, 20, 30))
        data = entry.create_group('data')
        data.attrs['NX_class'] = 'NXdata'
        data.attrs['signal'] = 'total'
        data.attrs['axes'] = ['x']
        data['x'] = meas['x']
        data['total'] = meas['total']


@pytest.fixture(scope='module')
def experiment(tmp_path_factory):
    folder = tmp_path_factory.mktemp('experiment')
    for n in (1001, 1002, 1003):
        make_scan(str(folder / f'i16-{n}.nxs'), n)
    return str(folder)


@pytest.fixture(scope='module')
def app():
    from mmg_qt_dataviewer.common import get_app
    return get_app()


@pytest.fixture
def config(experiment):
    from mmg_qt_dataviewer.config import default_config, C
    cfg = default_config('i16')
    cfg[C.current_dir] = experiment
    cfg[C.roi] = []
    return cfg


def test_data_viewer(app, experiment, config):
    from mmg_qt_dataviewer.data_viewer import DataViewer
    viewer = DataViewer(experiment, config)
    while viewer.scans._pending:
        viewer.scans._load_next_metadata()
    viewer.scans.select_first()
    files = viewer.scans.selected_files()
    assert len(files) == 1
    assert viewer.line.plot.ax.get_lines(), 'line plot is empty'
    assert viewer.line.x_axis.currentText() == 'x'
    assert viewer.image.plot.ax.get_images(), 'detector image not shown'
    assert 'i16-100' in viewer.details.text.toPlainText()
    # select two y-axes from the list beside the plot
    viewer.line.y_list.selectAll()
    assert set(viewer.line.y_names()) == {'x', 'total'}
    labels = [line.get_label() for line in viewer.line.plot.ax.get_lines()]
    assert 'x' in labels and 'total' in labels
    viewer.line.y_axis.setCurrentText('total')
    viewer.line.on_y_axis_change()
    assert viewer.line.y_names() == ['total']
    viewer.line.fit.setChecked(True)
    assert any(line.get_label() == 'fit' for line in viewer.line.plot.ax.get_lines())
    viewer.image.index.setValue(5)
    viewer.close()


def test_nexus_viewer(app, experiment):
    from mmg_qt_dataviewer.nexus_viewer import NexusViewer
    viewer = NexusViewer(os.path.join(experiment, 'i16-1001.nxs'))
    assert viewer.tree.topLevelItemCount() == 1
    assert viewer.namespace.topLevelItemCount() > 0
    viewer.expression.setText('mean(total)')
    viewer.evaluate()
    assert 'mean(total)' in viewer.output.toPlainText()
    viewer.tabs.setCurrentIndex(2)  # NeXus string view
    assert viewer.string_views['NeXus'].toPlainText()
    viewer.close()


def test_other_windows(app, experiment, config):
    from mmg_qt_dataviewer.file_browser import FileBrowser
    from mmg_qt_dataviewer.multi_scan import MultiScanAnalysis
    from mmg_qt_dataviewer.peak_fit import PeakFitting
    from mmg_qt_dataviewer.xmcd import XMCDVisualiser
    from mmg_qt_dataviewer.editors import PythonEditor
    from mmg_qt_dataviewer.config_editor import ConfigEditor
    from mmg_qt_dataviewer.plots import PlotWindow

    for mode in ('any', 'nexus', 'jupyter'):
        FileBrowser(experiment, mode, config).close()
    multi = MultiScanAnalysis(config, [1001, 1002], 'x', 'total', experiment)
    assert multi.range.scan_numbers() == [1001, 1002]
    multi.close()
    fit = PeakFitting(config, [1001, 1002, 1003], 'x', 'total', experiment, metadata='entry_identifier')
    fit.fit_all()
    assert fit.table.topLevelItem(0).text(3), 'centre not fitted'
    fit.close()
    XMCDVisualiser(config, [1001], experiment).close()
    PythonEditor('print(1)').close()
    ConfigEditor(dict(config)).close()
    PlotWindow([os.path.join(experiment, 'i16-1002.nxs')], config).close()
