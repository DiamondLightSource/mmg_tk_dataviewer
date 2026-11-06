"""
Replicate ScanSelector from scan_selector.py for Spectra objects

CURRENTLY NOT USED!
"""

import os
import time
import tkinter as tk
from tkinter import ttk
from threading import Thread, current_thread

import hdfmap

from mmg_toolbox.utils.file_functions import list_files, display_timestamp, get_scan_number
from ..misc.functions import post_right_click_menu, select_folder
from ..misc.logging import create_logger
from ..misc.config import get_config, C
from ..misc.styles import create_hover
from .find_scans import FindScans
from .treeview import CanvasTreeview

# TODO: Finsih this, split up scan_selectror._ScanSelector and use part of that here

class SpectraTable(CanvasTreeview):
    """Frame with TreeView for selection of scan files"""

    def __init__(self, root: tk.Misc, config: dict | None = None):
        self.config = config or get_config()
        self.search_str = ""
        self.search_time = time.time()
        self.search_reset = 3.0  # seconds
        self._update_time = 10  # seconds - poll folders for new files

        # Variables
        self.extension = tk.StringVar(root, '.nxs')
        self.read_datasets = tk.BooleanVar(root, True)
        self.search_box = tk.StringVar(root, '')
        self.search_matchcase = tk.BooleanVar(root, False)
        self.search_wholeword = tk.BooleanVar(root, True)
        self.select_box = tk.StringVar(root, '')
        self.map = None

        # Columns
        columns = [
            # (name, text, width, reverse, sort_col)
            ("#0", 'Number', 100, False, None),
            ("modified", 'Date', 150, True, "modified_time"),
            ('modified_time', 'Modified', 0, False, None),
            ("filepath", 'File Path', 0, False, None),
        ]
        # add values from metadata_list
        self.metadata_names = self.config.get(C.metadata_list, {})
        columns += [
            (name, name, 400, True, None) for name in self.metadata_names
        ]
        super().__init__(root, *columns, pack=False)

    "======================================================"
    "=============== populate functions ==================="
    "======================================================"

    def _add_row(self, parent="", name="", timestamp=0.0, time_str="", filepath="", *args, **kwargs):
        values = (time_str, timestamp, filepath) + args
        iid = self.tree.insert(parent, 0, text=name, values=values)
        for name, value in kwargs.items():
            self.tree.set(iid, column=name, value=value)
        return iid

    def _add_file(self, parent, filepath):
        scan_number = str(get_scan_number(filepath))
        timestamp = os.stat(filepath).st_mtime
        mtime = display_timestamp(timestamp)
        iid = self._add_row(parent, name=scan_number, timestamp=timestamp, time_str=mtime, filepath=filepath)
        return iid

    def _add_data(self, item):
        filepath = self.tree.set(item, 'filepath')
        if os.path.isdir(filepath):
            return
        try:
            if self.map is None:
                self.map = hdfmap.create_nexus_map(filepath)
            with hdfmap.load_hdf(filepath) as nxs:
                for name, fmt in self.metadata_names.items():
                    if not self.tree.winfo_exists():
                        return
                    data = self.map.format_hdf(nxs, fmt)
                    self.tree.set(item, name, data)
        except Exception as exception:
            name = next(iter(self.metadata_names), 'data')
            self.tree.set(item, name, str(exception))

    def populate_files(self, item, *file_list: str):
        """Add list of files below folder on folder expand"""
        # remove old entries
        self.tree.delete(*self.tree.get_children(item))
        self.map = None  # reset hdfmap
        start_time = time.time()
        for file in file_list:
            self._add_file(item, file)
        if self.read_datasets.get():
            self.update_metadata()
        logger.info(f"Expanding took {time.time() - start_time:.3g} s")

    def update_metadata(self, event=None):
        """Update dataset values column for hdf files under open folders"""

        def fn():
            for branch in self.tree.get_children():  # folders
                for leaf in self.tree.get_children(branch):  # files
                    if not self.tree.winfo_exists():
                        return
                    self._add_data(leaf)

        th = Thread(target=fn)
        th.daemon = True  # runs thread in the background, outside mainloop, allowing python to close
        th.start()

    def update_files(self):
        """Check folders in the tree for new files"""
        pass

    def poll_files(self, _event=None):
        """Create background thread that checks the folders for new files"""
        def fn():
            while True:
                if not self.tree.winfo_exists():
                    logger.info('poll_files exiting')
                    return
                self.update_files()
                time.sleep(self._update_time)

        th = Thread(target=fn)
        th.daemon = True  # runs thread in the background, outside mainloop, allowing python to close
        th.start()

    "======================================================"
    "================ general functions ==================="
    "======================================================"

    def get_filepath(self) -> tuple[str, str]:
        """
        Return filepath and folderpath of current selection
        :returns filename: str full filepath or None if selection isn't a file
        :returns foldername: str folder path
        """
        filename = None
        foldername = None
        for iid in self.tree.selection():
            filepath = self.tree.set(iid, 'filepath')
            if os.path.isfile(filepath):
                filename = filepath
                foldername = os.path.dirname(filename)
            else:  # item is a folder
                foldername = filepath
        logger.debug(f"Selected item: filename='{filename}', foldername='{foldername}'")
        return filename, foldername

    def get_multi_filepath(self) -> list[str]:
        """
        Return list of filepaths for all files in current selection
        :returns filename: list[str] of full filepaths
        """
        filenames = []
        for iid in self.tree.selection():
            filepath = self.tree.set(iid, 'filepath')
            if os.path.isfile(filepath):
                filenames.append(filepath)
        filenames.sort()
        return filenames

    def get_metadata(self) -> list[dict[str, str]]:
        return [
            {
                name: self.tree.set(iid, name)
                for name in self.metadata_names
            }
            for iid in self.tree.selection()
        ]

    def copy_path(self):
        filepath, folderpath = self.get_filepath()
        self.root.clipboard_clear()
        if filepath:
            self.root.clipboard_append(filepath)
        else:
            self.root.clipboard_append(folderpath)

    def copy_scan_number(self):
        scn = next((self.tree.item(iid)['text'] for iid in self.tree.selection()), None)
        self.root.clipboard_clear()
        if scn:
            self.root.clipboard_append(scn)

    def copy_data(self):
        metadata = next(iter(self.get_metadata()), {})
        data = next(iter(metadata.values()), '')
        self.root.clipboard_clear()
        self.root.clipboard_append(data)

    def _create_menu(self, iid: str | int):

        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Copy path", command=self.copy_path)

        filepath = self.tree.set(iid, 'filepath')
        if os.path.isfile(filepath):
            metadata = next(iter(self.metadata_names))
            menu.add_command(label="Copy Scan Number", command=self.copy_scan_number)
            menu.add_command(label=f"Copy {metadata}", command=self.copy_data)
            menu.add_command(label="open Treeview", command=self.open_nexus_treeview)
            menu.add_command(label="open Plot", command=self.open_nexus_plot)
            menu.add_command(label="open Image", command=self.open_nexus_image)
        return menu

    def right_click_menu(self):
        logger.info('Creating right click menu')

        def menu_popup(event):
            # select item
            iid = self.tree.identify_row(event.y)
            if iid:
                menu = self._create_menu(iid)
                post_right_click_menu(menu, event.x_root, event.y_root)
        return menu_popup

    def _delete_tree(self):
        self.tree.delete(*self.tree.get_children())

    def _on_close(self):
        # self.root.unbind_all('<KeyPress>')
        self.root.destroy()

    def _get_select_box(self):
        # TODO: replace with asteval
        return str(eval(self.select_box.get()))

    def select_from_box(self, event=None):
        item = self._get_select_box()
        self.tree.selection_remove(self.tree.selection())
        for iid in self.tree.get_children():  # folders
            for scan_iid in self.tree.get_children(iid):
                scan_number = self.tree.item(scan_iid)['text']
                if item in scan_number:
                    self.tree.selection_add(scan_iid)
                    self.tree.see(scan_iid)
                    break

    def select_box_increase(self):
        if self.tree.selection():
            self.tree.selection_set(self.tree.prev(self.tree.selection()[0]))

    def select_box_decrease(self):
        if self.tree.selection():
            self.tree.selection_set(self.tree.next(self.tree.selection()[0]))

    def on_key_press(self, event):
        """any key press performs search of folders, selects first matching folder"""
        # return if clicked on entry box
        # event.widget == self.tree
        if str(event.widget).endswith('entry'):
            return
        # reset search str after reset time
        ctime = time.time()
        if ctime > self.search_time + self.search_reset:
            self.search_str = ""
        # update search time, add key to query
        self.search_time = ctime
        self.search_str += event.char

        self.tree.selection_remove(self.tree.selection())
        # search folder list
        for branch in self.tree.get_children():  # folders
            folder = self.tree.item(branch)['text']
            if self.search_str in folder[:len(self.search_str)].lower():
            # if folder.lower().startswith(self.search_str):
                self.tree.selection_add(branch)
                self.tree.see(branch)
                break

    "======================================================"
    "=============== widget functions ====================="
    "======================================================"

    def open_nexus_treeview(self):
        filename, folderpath = self.get_filepath()
        logger.info(f"Opening nexus viewer for filename: {filename}")
        if filename:
            from .. import create_nexus_viewer
            create_nexus_viewer(filename, parent=self.root, config=self.config)

    def open_nexus_plot(self):
        filename, folderpath = self.get_filepath()
        logger.info(f"Opening nexus plot viewer for filename: {filename}")
        if filename:
            from ..apps.nexus import create_nexus_plotter
            create_nexus_plotter(filename, parent=self.root, config=self.config)

    def open_nexus_image(self):
        filename, folderpath = self.get_filepath()
        logger.info(f"Opening nexus image viewer for filename: {filename}")
        if filename:
            from ..apps.nexus import create_nexus_image_plotter
            create_nexus_image_plotter(filename, parent=self.root, config=self.config)

    "======================================================"
    "================= misc functions ====================="
    "======================================================"

    def fun_search(self, event=None):
        self.tree.selection_remove(self.tree.selection())
        query = self.search_box.get()
        match_case = self.search_matchcase.get()
        whole_word = self.search_wholeword.get()
        query = query if match_case else query.lower()

        for branch in self.tree.get_children():  # folders
            # folder = self.tree.item(branch)['text']
            for leaf in self.tree.get_children(branch):  # files
                item = self.tree.item(leaf)
                if len(item['values']) < 3:
                    continue
                file = item['text']
                value = item['values'][2]
                test = f"{file} {value}"
                test = test if match_case else test.lower()
                test = test.split() if whole_word else test
                if query in test:
                    self.tree.selection_add(leaf)
                    self.tree.see(leaf)

