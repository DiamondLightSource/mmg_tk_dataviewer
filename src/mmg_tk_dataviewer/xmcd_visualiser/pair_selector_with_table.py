"""
pair_selector.py
The PairSelector widget controls the scan pair panel, loading scan files as spectra and determining pair type.
Pair data is loaded and stored by Average.load_pair
"""

import os
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable
from threading import Thread

from mmg_toolbox.utils.misc_functions import string2numbers
from mmg_toolbox.xas import SpectraContainer, polarised_pairs
from mmg_toolbox.xas.spectra import BACKGROUND_FUNCTIONS
from ..misc.functions import create_scrollable_window, entry_with_placeholder
from ..misc.config import C
from ..widgets.scan_selector import _ScanSelector
from .average_tab import Average
from .utils import load_spectra_files

BACKGROUNDS = ['None'] + list(BACKGROUND_FUNCTIONS)


class ScanTable(_ScanSelector):
    """Frame with TreeView for selection of scans"""

    def __init__(self, root: tk.Misc, *scan_files: str, config: dict | None = None):
        super().__init__(root, config)
        self.pack_treeview()
        self.file_list = scan_files
        self.output_files = []

        self.tree.bind("<Button-3>", self.right_click_menu())
        self.populate_files("", *scan_files)

    def update_metadata(self, event=None):
        """Update dataset values column for hdf files under open folders"""

        def fn():
            for file in self.tree.get_children():  # files
                if not self.tree.winfo_exists():
                    return
                self._add_data(file)

        th = Thread(target=fn)
        th.daemon = True  # runs thread in the background, outside mainloop, allowing python to close
        th.start()



class PairSelector:
    def __init__(self, root: tk.Misc, base: Average, scan_range_str: str | None = None, files: list[str] | None = None):
        self._base = base
        self.root = root

        # variables
        modes = ['TEY', 'TFY']
        backgrounds = BACKGROUNDS
        self.scan_range = tk.StringVar(self.root, scan_range_str)
        self.dls_loader = tk.BooleanVar(self.root, True)
        self.mode_option = tk.StringVar(self.root, modes[0])
        self.bkg_option = tk.StringVar(self.root, backgrounds[0])
        self.pair_numbers: list[tuple[tk.IntVar, tk.IntVar, Callable]] = []

        grid_options = dict(padx=5, pady=5, sticky='nsew')
        self.root.rowconfigure(0, weight=0)  # scan numbers
        self.root.rowconfigure(1, weight=1)  # scan list
        self.root.rowconfigure(2, weight=1)  # pairs
        self.root.rowconfigure(3, weight=0)  # options

        # Files
        frm = ttk.LabelFrame(self.root, text='Scan Numbers')
        frm.grid(row=0, column=0, **grid_options)
        ttk.Button(frm, text='Load', command=self.btn_load_file).pack(side='top', fill='x', padx=10, pady=3)
        var = entry_with_placeholder(frm, self.scan_range, '123456:123460')
        var.bind('<Return>', self.btn_find_pairs)
        var.pack(side='left')
        ttk.Checkbutton(frm, text='DLS Loader', variable=self.dls_loader).pack(side='left')
        ttk.Button(frm, text='List', command=self.btn_list_scans).pack(side='left')
        ttk.Button(frm, text='Find Pairs', command=self.btn_find_pairs).pack(side='left')

        # Scan List
        frm = ttk.LabelFrame(self.root, text='Scans', relief='groove')
        frm.grid(row=1, column=0, **grid_options)
        # TODO: improve this or replace ScanTable with SpectraTable
        table_config = {
            C.metadata_list: {'pol': '{polarisation}', 'cmd': '{scan_command}'}
        }
        self.table = ScanTable(frm, config=table_config)
        self.table.tree.column('pol', width=30)
        ttk.Button(frm, text='Select', command=self.btn_select_scans).pack(side='top', fill='x')

        # Pairs
        frm = ttk.LabelFrame(self.root, text='Pairs', relief='groove')
        frm.grid(row=2, column=0, **grid_options)
        self.pair_frm = create_scrollable_window(frm, height=100, width=100)
        # self.pair_frm.pack(side='top', fill='x')
        ttk.Button(frm, text='+', command=self.add_pair).pack(side='top', fill='x')
        self.add_pair()

        # Options
        frm = ttk.LabelFrame(self.root, text='Options')
        # frm.pack(side='top', fill='x')
        frm.grid(row=3, column=0, **grid_options)
        self.ch_modes = ttk.OptionMenu(frm, self.mode_option, modes[0], *modes,
                                       command=self._base.update_plots)
        self.ch_modes.pack(side='top', fill='x', padx=4)
        ttk.OptionMenu(frm, self.bkg_option, backgrounds[0], *backgrounds,
                       command=self._base.update_plots).pack(side='top', fill='x', padx=4)
        ttk.Button(frm, text='Plot', command=self._base.plot_pairs).pack(side='top', fill='x', padx=10, pady=3)

        # populate scans box
        if files:
            self.add_files(files)

    def add_files(self, filename, *filenames):
        folder = os.path.dirname(filename)
        self._base.exp.add_data_paths(folder)
        self.table.populate_files("", filename, *filenames)

    def add_pair(self, number1: int | None = None, number2: int | None = None):
        var1 = tk.IntVar(self.root, number1)
        var2 = tk.IntVar(self.root, number2)
        label = tk.StringVar(self.root, '')

        frm = ttk.Frame(self.pair_frm)
        frm.pack(side='top', fill='x')

        def update_label(event=None):
            n1, n2 = var1.get(), var2.get()
            if n1 and n2:
                try:
                    s1, s2 = self._base.load_pair(n1, n2, dls_loader=self.dls_loader.get())
                    subtract = s1 - s2
                    label.set(subtract.label())
                    self.update_modes(s1)
                except ValueError:
                    label.set("Scans don't match")

        def remove():
            self.pair_numbers.remove((var1, var2, update_label))
            frm.destroy()

        en = ttk.Entry(frm, textvariable=var1, width=10)
        en.pack(side='left')
        en.bind('<Return>', update_label)
        en = ttk.Entry(frm, textvariable=var2, width=10)
        en.pack(side='left')
        en.bind('<Return>', update_label)
        ttk.Button(frm, text='X', command=remove, width=1).pack(side='left', padx=1)
        ttk.Label(frm, textvariable=label).pack(side='left')
        self.pair_numbers.append((var1, var2, update_label))
        update_label()

    def add_pairs(self, pairs: list[tuple[SpectraContainer, SpectraContainer]],
                  spectra_list: list[SpectraContainer] | None = None):
        """
            self.add_pairs([(s1, s2), (s3, s4)])
        or
            self.add_pairs(spectra_list=[s1, s2, s3, s4])

        :param pairs: list of paired SpectraContainers
        :param spectra_list: list of SpectraContainers
        """
        if spectra_list:
            spectra_list.append(spectra_list[-1]) # copy final value when odd number
            pairs = [
                (s1, s2) for s1, s2 in zip(spectra_list[::2], spectra_list[1::2])
            ]
        if pairs:
            self.update_modes(pairs[0][0])
        for s1, s2 in pairs:
            # Find next free box
            n = next((
                n for n, (v1, v2, update) in enumerate(self.pair_numbers)
                if v1.get() < 1 and v2.get() < 1), None
            )
            if n is not None:
                v1, v2, update = self.pair_numbers[n]
                v1.set(s1.metadata.scan_no)
                v2.set(s2.metadata.scan_no)
                update()
            else:
                # add new box
                self.add_pair(s1.metadata.scan_no, s2.metadata.scan_no)
        self._base.plot_pairs()

    def get_pair_numbers(self) -> list[tuple[int, int]]:
        return [
            vals for v1, v2, update in self.pair_numbers
            if all(vals := (v1.get(), v2.get()))
        ]

    def set_pair_numbers(self, pair_numbers: list[tuple[int, int]]) -> None:
        for n, (scan_no1, scan_no2) in enumerate(pair_numbers):
            if n < len(self.pair_numbers):
                v1, v2, update = self.pair_numbers[n]
                v1.set(scan_no1)
                v2.set(scan_no2)
                update()
            else:
                self.add_pair(scan_no1, scan_no2)
            if n == 0:
                scan, = self._base.load_scans(scan_no1, dls_loader=self.dls_loader.get())
                self.update_modes(scan)

    def update_modes(self, scan: SpectraContainer):
        modes = list(scan.spectra)
        self.ch_modes.set_menu(modes[0], *modes)

    def btn_list_scans(self):
        scan_numbers = string2numbers(self.scan_range.get())
        filenames = [self._base.exp.get_scan_filename(n) for n in scan_numbers]
        self.table.populate_files("", *filenames)

    def btn_find_pairs(self, event=None):
        scan_numbers = string2numbers(self.scan_range.get())
        scans = self._base.load_scans(*scan_numbers, dls_loader=self.dls_loader.get())
        if scans:
            self.update_modes(scans[0])
            pol_pairs = polarised_pairs(*scans)
            self.add_pairs(pol_pairs)

    def btn_load_file(self):
        default_folder = self._base.config.get(C.current_proc) or self._base.config.get(C.current_dir, '')
        filenames = load_spectra_files(self.root, default_folder)
        if filenames:
            self.add_files(*filenames)

    def btn_select_scans(self):
        filenames = self.table.get_multi_filepath()
        scans = self._base.load_scans(*filenames, dls_loader=self.dls_loader.get())
        if scans:
            self.add_pairs([], spectra_list=scans)

