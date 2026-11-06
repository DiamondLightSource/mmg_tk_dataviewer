
import os
import tkinter as tk
from tkinter import ttk

from mmg_toolbox.xas import SpectraContainerSubtraction
from mmg_toolbox.scripts import R, Rxas
from ..misc.config import generate_output_filename
from ..misc.processing_options import create_script_from_template, create_notebook_from_template
from ..widgets.simple_plot import SimplePlot
from .spectra_plot import SpectraPlot
from .average_tab import Average


class AveragePlot:
    def __init__(self, root: tk.Misc, base: Average, config: dict | None = None):
        self._base = base
        self.config = config
        self.root = root
        self.spectra: SpectraContainerSubtraction | None = None
        self.mode: str = ''
        self.output_name = tk.StringVar(self.root, '')

        # Pol 1
        frm = ttk.Frame(self.root)
        frm.pack(side='top', fill='x')
        self.pol1_figure = SimplePlot(
            root=frm,
            xdata=[],
            ydata=[],
            xlabel='Energy [eV]',
            ylabel='',
            title='Pol 1',
            config=self.config
        )
        self.pol1_figure.ax1.set_xlabel('Energy [eV]')
        self.pol1_figure.fig.tight_layout()

        # Pol 2
        frm = ttk.Frame(self.root)
        frm.pack(side='top', fill='x')
        self.pol2_figure = SimplePlot(
            root=frm,
            xdata=[],
            ydata=[],
            xlabel='Energy [eV]',
            ylabel='',
            title='Pol 2',
            config=self.config
        )
        self.pol2_figure.ax1.set_xlabel('Energy [eV]')
        self.pol2_figure.fig.tight_layout()

        # Average
        frm = ttk.Frame(self.root)
        frm.pack(side='top', fill='x')
        self.figure = SpectraPlot(frm, config=self.config)

        # Buttons
        frm = ttk.Frame(self.root)
        frm.pack(side='top', fill='x')
        ttk.Button(frm, text='Add Spectra to Comparison', command=self.btn_add_spectra).pack(side='top', fill='x')
        line = ttk.Frame(frm)
        line.pack(side='top', fill='x')
        ttk.Label(line, text='Filename:').pack(side='left', padx=5)
        ttk.Entry(line, textvariable=self.output_name).pack(side='left', fill='x', expand=True)
        ttk.Button(frm, text='Save NeXus', command=self.btn_nexus).pack(side='top', fill='x')
        ttk.Button(frm, text='Save CSV', command=self.btn_csv).pack(side='top', fill='x')
        ttk.Button(frm, text='Generate Script', command=self.btn_script).pack(side='top', fill='x')

    def update_plot(self, spectra: SpectraContainerSubtraction, mode: str = 'tey'):
        self.spectra = spectra
        self.mode = mode

        self.pol1_figure.remove_lines()
        self.pol1_figure.reset_plot()
        spectra.add_edge_lines(self.pol1_figure.ax1)
        self.pol2_figure.remove_lines()
        for spec in spectra.spectra1.parents:
            spectrum = spec.spectra[self.mode]
            self.pol1_figure.plot(spectrum.energy, spectrum.signal, label=spec.name)
        self.pol1_figure.ax1.legend(frameon=False)
        self.pol1_figure.ax1.set_title(spectra.spectra1.name)
        self.pol1_figure.update_axes()

        self.pol2_figure.remove_lines()
        self.pol2_figure.reset_plot()
        spectra.add_edge_lines(self.pol2_figure.ax1)
        for spec in spectra.spectra2.parents:
            spectrum = spec.spectra[self.mode]
            self.pol2_figure.plot(spectrum.energy, spectrum.signal, label=spec.name)
        self.pol2_figure.ax1.legend(frameon=False)
        self.pol2_figure.ax1.set_title(spectra.spectra2.name)
        self.pol2_figure.update_axes()

        self.figure.update_spectra(spectra, self.mode)
        self.output_name.set(spectra.label())

    def btn_add_spectra(self):
        """Add spectra to different panel"""
        if self.spectra:
            self._base.add_comparison_spectra(self.spectra)
            # self._base._base.comparison.treeview.add_spectra(self.spectra)

    def btn_nexus(self):
        output_name = self.output_name.get()
        filename = generate_output_filename(output_name, '.nxs', self.config)
        if self.spectra and output_name:
            self.spectra.write_nexus(filename)

    def btn_csv(self):
        output_name = self.output_name.get()
        filename = generate_output_filename(output_name, '.csv', self.config)
        if self.spectra and output_name and self.mode:
            self.spectra.write_csv(filename, self.mode)

    def btn_script(self):
        self._script_create()

    def btn_jupyter(self):
        pass

    def _script_create(self):

        if self.spectra:
            spectra1 = self.spectra.spectra1
            spectra2 = self.spectra.spectra2
            files1 = list(spectra1.get_raw_metadata('filename').values())
            files2 = list(spectra2.get_raw_metadata('filename').values())
            output_name = self.output_name.get()
            filename = generate_output_filename(output_name, '.py', self.config)

            replacements = {
                Rxas.files1: '\n    '.join(f"'{f}'," for f in files1),
                Rxas.files2: '\n    '.join(f"'{f}'," for f in files2),
                Rxas.mode: self.mode,
                Rxas.proc: os.path.dirname(filename),
                Rxas.description: 'script from xmcd visualiser.',
                Rxas.title: 'xmcd_visualiser',
                Rxas.background: self._base.pair_selector.bkg_option.get()
            }
            create_script_from_template(self.root, 'xmcd', config=self.config, **replacements)

        # replacements = {
        #     R.exp: self._base.exp.folder_paths[0],
        #     # R.filepaths: '\n'.join(self._base.pair_numbers),
        #     R.beamline: 'i10-1',
        #     R.scannos: str(12345),
        #     # R.title: exp.generate_scans_title(*scan_numbers, metadata_str=value, hdf_map=first_scan.map),
        #     R.description: 'Created by  MultiScanAnalysis',
        #     # R.xaxis: self.x_axis.get(),
        #     # R.yaxis: self.y_axis.get(),
        #     # R.value: self.metadata_name.get(),
        # }
        # create_script_from_template(self.root, 'spectra', config=self.config, **replacements)
        # elif script in NOTEBOOKS:
        #     create_notebook_from_template(self.root, script, proc, self.config, **replacements)
