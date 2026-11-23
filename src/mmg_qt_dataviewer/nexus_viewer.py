"""
NeXus File Viewer - the structure of a single HDF5/NeXus file
"""
import h5py
import hdfmap
from PySide6 import QtWidgets
from PySide6.QtCore import Qt

from mmg_toolbox.utils.file_functions import hdfobj_string
from .style import fit_to_screen
from .common import add_menus, show_window, select_hdf_files, monospace, button
from .style import card, row


def text_view() -> QtWidgets.QPlainTextEdit:
    text = QtWidgets.QPlainTextEdit(readOnly=True, font=monospace())
    text.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
    return text


class NexusViewer(QtWidgets.QMainWindow):
    """Tree, NeXus, HdfMap and text views of a file, with search and expression evaluation"""

    STRING_TABS = {
        'NeXus': lambda m: m.info_nexus(),
        'Tree String': lambda m: hdfmap.hdf_tree_string(m.filename),
        'NeXus2SRS': lambda m: _nexus2srs(m),
        'NXtransformations': lambda m: _transformations(m.filename),
    }

    def __init__(self, filename: str = '', config: dict | None = None):
        super().__init__()
        self.setWindowTitle('NeXus File Viewer')
        self.filename = ''
        self.map: hdfmap.NexusMap | None = None

        self.path = QtWidgets.QLineEdit(readOnly=True)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(['Name', 'Type', 'Value'])
        self.tree.itemSelectionChanged.connect(self.show_details)
        self.namespace = QtWidgets.QTreeWidget()
        self.namespace.setHeaderLabels(['Name', 'Path', 'Value'])
        self.namespace.itemSelectionChanged.connect(self.show_details)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.addTab(self.tree, 'HDF Tree')
        self.tabs.addTab(self.namespace, 'HdfMap')
        self.string_views = {name: text_view() for name in self.STRING_TABS}
        for name, view in self.string_views.items():
            self.tabs.addTab(view, name)
        self.tabs.currentChanged.connect(self.load_tab)

        self.search = QtWidgets.QLineEdit(placeholderText='Search names and paths…')
        self.search.textChanged.connect(self.filter_tree)
        self.details = text_view()
        self.expression = QtWidgets.QLineEdit(placeholderText='Expression, e.g. axes, mean(signal)')
        self.expression.returnPressed.connect(self.evaluate)
        self.output = text_view()

        self.tree.setAlternatingRowColors(True)
        self.namespace.setAlternatingRowColors(True)
        self.tree.header().resizeSection(0, 220)
        self.namespace.header().resizeSection(0, 180)
        top = row(self.path, button('Open…', self.browse, self), button('Expand all', self.tree.expandAll),
                  self.search, stretch=0)
        self.search.setMaximumWidth(260)
        self.search.setClearButtonEnabled(True)
        right = QtWidgets.QSplitter(Qt.Vertical, childrenCollapsible=False)
        right.addWidget(card(self.details, title='Details'))
        right.addWidget(card(self.expression, self.output, title='Evaluate expression'))
        right.setStretchFactor(0, 2)
        right.setStretchFactor(1, 1)
        splitter = QtWidgets.QSplitter(childrenCollapsible=False)
        splitter.addWidget(self.tabs)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addLayout(top)
        layout.addWidget(splitter)
        self.setCentralWidget(central)
        fit_to_screen(self, 1500, 950)

        add_menus(self, {'File': {'New': lambda: show_window(NexusViewer(config=config)), 'Open': self.browse}})
        if filename:
            self.load_file(filename)

    def browse(self):
        files = select_hdf_files(self)
        if files:
            self.load_file(files[0])

    def load_file(self, filename: str):
        self.filename = filename
        self.path.setText(filename)
        self.map = hdfmap.create_nexus_map(filename)
        self.tree.clear()
        self.namespace.clear()
        with hdfmap.load_hdf(filename) as hdf:
            self._add_group(self.tree.invisibleRootItem(), hdf)
            for name, path in self.map.combined.items():
                item = QtWidgets.QTreeWidgetItem([name, path, self.map.get_string(hdf, name)])
                self.namespace.addTopLevelItem(item)
        self.tree.topLevelItem(0) and self.tree.topLevelItem(0).setExpanded(True)
        for view in self.string_views.values():
            view.clear()
        self.load_tab()

    def _add_group(self, parent: QtWidgets.QTreeWidgetItem, group: h5py.Group):
        for key in group:
            obj = group.get(key)
            if isinstance(obj, h5py.Group):
                nx_class = obj.attrs.get('NX_class', b'')
                nx_class = nx_class.decode() if isinstance(nx_class, bytes) else str(nx_class)
                item = QtWidgets.QTreeWidgetItem(parent, [key, nx_class, ''])
                self._add_group(item, obj)
            elif isinstance(obj, h5py.Dataset):
                value = str(obj[()]) if obj.size < 10 else f"{obj.dtype} {obj.shape}"
                item = QtWidgets.QTreeWidgetItem(parent, [key, 'dataset', value])
            else:
                item = QtWidgets.QTreeWidgetItem(parent, [key, 'missing link', ''])
            item.setData(0, Qt.UserRole, f"{group.name.rstrip('/')}/{key}")

    def load_tab(self):
        name = self.tabs.tabText(self.tabs.currentIndex())
        view = self.string_views.get(name)
        if view is not None and self.map and not view.toPlainText():
            try:
                view.setPlainText(self.STRING_TABS[name](self.map))
            except Exception as e:
                view.setPlainText(f"Error: {e}")

    def show_details(self):
        tree = self.sender()
        item = tree.currentItem()
        if item is None:
            return
        path = item.text(1) if tree is self.namespace else item.data(0, Qt.UserRole)
        self.details.setPlainText(hdfobj_string(self.filename, path))

    def filter_tree(self, text: str):
        text = text.lower()

        def visit(item: QtWidgets.QTreeWidgetItem) -> bool:
            children = [visit(item.child(i)) for i in range(item.childCount())]
            match = not text or text in item.text(0).lower() or any(children)
            item.setHidden(not match)
            if text and match:
                item.setExpanded(True)
            return match
        for n in range(self.tree.topLevelItemCount()):
            visit(self.tree.topLevelItem(n))
        for n in range(self.namespace.topLevelItemCount()):
            item = self.namespace.topLevelItem(n)
            item.setHidden(bool(text) and text not in item.text(0).lower() and text not in item.text(1).lower())

    def evaluate(self):
        if not self.map:
            return
        expression = self.expression.text()
        try:
            with hdfmap.load_hdf(self.filename) as hdf:
                result = self.map.eval(hdf, expression)
        except Exception as e:
            result = e
        self.output.appendPlainText(f">>> {expression}\n{result}\n")


def _nexus2srs(hdf_map: hdfmap.NexusMap) -> str:
    from nexus2srs.nexus2srs import generate_datafile
    with hdf_map.load_hdf() as hdf:
        text, _ = generate_datafile(hdf, hdf_map)
    return text


def _transformations(filename: str) -> str:
    from mmg_toolbox.nexus.nexus_transformations import generate_nxtranformations_string
    return generate_nxtranformations_string(filename)
