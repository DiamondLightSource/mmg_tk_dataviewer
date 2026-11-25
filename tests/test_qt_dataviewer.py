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


def make_xas_scan(filename: str, scan_number: int, pol: str = 'pc', field: float = 5., temp: float = 10.):
    """Write a minimal NXxas scan of an Fe L2,3 edge with circular dichroism"""
    energy = np.linspace(695, 735, 400)
    sign = np.sign(field) * (1 if pol == 'pc' else -1)
    step = 0.3 / (1 + np.exp(-(energy - 708) / 0.5)) + 0.15 / (1 + np.exp(-(energy - 721) / 0.5))
    l3 = (1 + 0.15 * sign) / (1 + ((energy - 708) / 1.0) ** 2)
    l2 = (0.5 - 0.1 * sign) / (1 + ((energy - 721) / 1.2) ** 2)
    signal = 1 + 0.002 * (energy - 695) + step + l3 + l2
    noise = np.random.default_rng(scan_number).normal(0, 0.005, energy.size)
    with h5py.File(filename, 'w') as nx:
        entry = nx.create_group('entry')
        entry.attrs.update({'NX_class': 'NXentry', 'default': 'tey'})
        entry['definition'] = 'NXxas'
        entry['entry_identifier'] = scan_number
        entry['scan_command'] = f'scan energy 695 735 0.1 pol {pol}'
        entry['start_time'] = '2026-11-25T10:00:00'
        entry.create_group('instrument').attrs['NX_class'] = 'NXinstrument'
        entry['instrument/name'] = 'i06-1'
        monitor = entry.create_group('monitor')
        monitor.attrs['NX_class'] = 'NXmonitor'
        monitor['data'] = np.full_like(energy, 1000.)
        sample = entry.create_group('sample')
        sample.attrs['NX_class'] = 'NXsample'
        sample['temperature'] = float(temp)
        sample['magnetic_field'] = float(field)
        beam = sample.create_group('beam')
        beam.attrs['NX_class'] = 'NXbeam'
        beam['incident_polarization'] = pol
        for mode, scale in (('tey', 1000), ('tfy', 400)):
            data = entry.create_group(mode)
            data.attrs.update({'NX_class': 'NXdata', 'signal': 'absorbed_beam', 'axes': ['energy']})
            data['mode'] = mode
            data['energy'] = energy
            data['absorbed_beam'] = scale * (signal + noise)


def make_xas_experiment(folder: str) -> list[str]:
    """pc, nc, nc, pc scans at +5 T and -5 T, at 10 K and 100 K"""
    files = []
    number = 1000
    for temp in (10, 100):
        for field in (5, -5):
            for pol in ('pc', 'nc', 'nc', 'pc'):
                number += 1
                files.append(os.path.join(folder, f'i06-1-{number}.nxs'))
                make_xas_scan(files[-1], number, pol, field, temp)
    return files


@pytest.fixture(scope='module')
def xas_experiment(tmp_path_factory):
    folder = str(tmp_path_factory.mktemp('xas'))
    make_xas_experiment(folder)
    return folder


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
    cfg[C.metadata_string] = '{filename}\ncmd = {scan_command}'
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


def test_xmcd_analysis(xas_experiment, tmp_path):
    """Pairs, processing chain, averages, sum rules and the generated script give the same answer"""
    import json
    import matplotlib
    from mmg_toolbox.xas import load_xas_scans
    from mmg_qt_dataviewer.xmcd import analysis as a

    files = sorted(os.path.join(xas_experiment, f) for f in os.listdir(xas_experiment))
    scans = [a.load_scan(f) for f in files]
    pol_pairs = [a.Pair(*p) for p in a.find_pairs(scans, 'polarisation')]
    assert len(pol_pairs) == 8
    assert all(p.scan1.metadata.pol == 'pc' and p.scan2.metadata.pol == 'nc' for p in pol_pairs)
    assert not any(p.warnings() for p in pol_pairs)
    field_pairs = [a.Pair(*p) for p in a.find_pairs(scans, 'field')]
    assert all(p.scan1.metadata.mag_field > 0 > p.scan2.metadata.mag_field for p in field_pairs)

    steps = a.default_steps() + [a.Step('trim', {'ev_from_start': 2})]
    assert a.chain_code(steps).endswith('.trim(ev_from_start=2)')
    processed = {id(s): a.apply_chain(s, steps) for s in scans}
    condition = pol_pairs[0].condition()
    for pair in pol_pairs:
        pair.include = pair.condition() == condition
    result = a.Result.calculate(pol_pairs, processed, steps, 'tey')
    assert len(result.pairs) == 2
    holes = a.n_holes('Fe', 2)
    assert holes == 4
    assert a.n_holes('Gd') is None
    orbital, spin = result.sum_rules(holes, result.default_split_energy())
    assert np.isfinite(orbital) and np.isfinite(spin)

    result.write_nexus(str(tmp_path / result.file_name()))
    reloaded, = load_xas_scans(str(tmp_path / result.file_name()))
    assert 'Subtraction' in type(reloaded).__name__

    matplotlib.use('Agg')
    namespace = {}
    exec(a.to_script([result], str(tmp_path / 'script')), namespace)
    (diff, script_orbital, script_spin), = namespace['results']
    assert np.isclose(script_orbital, orbital) and np.isclose(script_spin, spin)
    notebook = json.loads(a.to_notebook([result, result]))
    assert notebook['nbformat'] == 4 and len(notebook['cells']) > 4


def test_xmcd_visualiser(app, xas_experiment, config):
    from mmg_qt_dataviewer.xmcd import XMCDVisualiser
    from mmg_qt_dataviewer.xmcd.analysis import Step

    window = XMCDVisualiser(config, list(range(1001, 1009)), xas_experiment)
    while window.browser.is_loading():
        app.processEvents()
    app.processEvents()
    assert len(window.browser.loaded_scans()) == 8
    assert len(window.pairs) == 4, 'scans should be paired automatically'
    assert len(window.grid.cells) == 4
    assert window.result is not None and len(window.result.pairs) == 2  # first condition only

    window.grid.cells[0].include.setChecked(False)
    assert len(window.result.pairs) == 1
    window.grid.include_all(True)
    assert len(window.result.pairs) == 2

    window.chain.add(Step('divide_by_postedge'))
    window.reprocess()
    assert 'divide_by_postedge' in [s.method for s in window.result.steps]
    window.chain.add(Step('divide_by_signal_at_energy', {'energy1': 'not a number'}))
    window.reprocess()
    assert window.result is None and window.errors
    window.chain.reset()
    window.reprocess()
    assert window.result is not None and not window.errors

    window.sum_rules.oxidation.setValue(3)
    assert window.sum_rules.holes.value() == 5
    window.sum_rules.set_split(714.)
    assert window.result.split_energy == 714.
    window.add_to_series()
    window.grid.condition.setCurrentIndex(window.grid.condition.count() - 1)
    window.add_to_series()
    assert len(window.results) == 2 and window.series.table.rowCount() == 2

    window.pair_list.by.setCurrentText('Field')
    window.pair_list.auto_pair()
    assert all(p.is_field_pair() for p in window.pairs)
    window.close()
