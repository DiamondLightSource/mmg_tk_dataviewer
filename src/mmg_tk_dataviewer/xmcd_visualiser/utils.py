import os
import tkinter as tk
from tkinter import messagebox

from mmg_toolbox.utils.file_functions import get_scan_number
from mmg_toolbox.xas.nxxas_loader import is_subtraction, load_xmcd_from_processed_nxs, load_xas_scans

from ..misc.functions import select_hdf_file, select_hdf_files


def load_subtraction_file(root: tk.Misc, initial_directory: str | None = None) -> str | None:
    filename = select_hdf_file(root, initial_directory)
    if filename and not is_subtraction(filename):
        messagebox.showwarning(
            title='File must be a processed XMCD file',
            message=f"File: \n{filename}\n is not an XAS Subtraction file.",
            parent=root
        )
        filename = None
    return filename


def load_spectra_files(root: tk.Misc, initial_dir: str) -> list[str]:
    filenames = select_hdf_files(root, initial_dir)
    good, bad = [], []
    for filename in filenames:
        if is_subtraction(filename):
            scan = load_xmcd_from_processed_nxs(filename)
            if hasattr(scan.metadata, 'raw_files1') and hasattr(scan.metadata, 'raw_files2'):
                raw_files1 = scan.metadata.raw_files1
                raw_files2 = scan.metadata.raw_files2
                good.extend(raw_files1 + raw_files2)
            else:
                bad.append(filename)
        else:
            try:
                scan = load_xas_scans(filename)
                good.append(filename)
            except Exception as e:
                bad.append(filename)
    if bad:
        messagebox.showwarning(
            title='Incorrect File Type',
            message=f"These files can't be read as Spectra: \n  " + '\n  '.join(bad),
            parent=root
        )
    return good


def load_pairs(root: tk.Misc, initial_dir: str) -> tuple[str | None, list[tuple[int, int]]]:
    # filename = load_subtraction_file(root, initial_directory=initial_dir)
    filenames = select_hdf_files(root, initial_dir)
    if len(filenames) == 1 and is_subtraction(filenames[0]):
        scan = load_xmcd_from_processed_nxs(filenames[0])
        if hasattr(scan.metadata, 'raw_files1') and hasattr(scan.metadata, 'raw_files2'):
            raw_files1 = scan.metadata.raw_files1
            raw_files2 = scan.metadata.raw_files2
            folder = next(iter(raw_files1.values()))
            pairs = [
                (int(scan_no1), int(scan_no2))
                for scan_no1, scan_no2 in zip(raw_files1.keys(), raw_files2.keys())
            ]
            print(f"Loaded {len(pairs)} pairs in folder: {folder}")
            return folder, pairs
    elif filenames:
        folder = os.path.basename(filenames[0])
        pairs = [
            (get_scan_number(f1), get_scan_number(f2))
            for f1, f2 in zip(filenames[0::2], filenames[1::2])
        ]
        print(f"Loaded {len(pairs)} pairs in folder: {folder}")
        return folder, pairs
    return None, []
