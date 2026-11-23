"""
Python script editor and GDA terminal log viewer
"""
import os

from PySide6 import QtWidgets
from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QTextDocument

from mmg_toolbox.utils.env_functions import run_python_script
from mmg_toolbox.utils.file_reader import read_gda_terminal_log
from .common import add_menus, show_window, monospace, show_error


class Highlighter(QSyntaxHighlighter):
    """Colour text matching regular expressions"""

    def __init__(self, document, rules: list[tuple[str, str]]):
        super().__init__(document)
        self.rules = []
        for pattern, colour in rules:
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(colour))
            self.rules.append((QRegularExpression(pattern), fmt))

    def highlightBlock(self, text: str):
        for regex, fmt in self.rules:
            matches = regex.globalMatch(text)
            while matches.hasNext():
                match = matches.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)


PYTHON_RULES = [
    (r'\b(def|class|import|from|as|return|for|in|if|elif|else|while|with|try|except|lambda|None|True|False)\b', '#0000c0'),
    (r'\b(print|range|len|list|dict|str|int|float)\b', '#008080'),
    (r'".*?"|\'.*?\'', '#a05000'),
    (r'#[^\n]*', '#808080'),
]
LOG_RULES = [
    (r'\b(Scan|WARNING|ERROR)\b', '#c00000'),
    (r'^.*\| >>>.*$', '#0000c0'),
    (r'".*?"|\'.*?\'', '#a05000'),
]


class PythonEditor(QtWidgets.QMainWindow):
    """Simple python editor with RUN button"""

    def __init__(self, text: str = '', filename: str = ''):
        super().__init__()
        self.filename = filename
        self.text = QtWidgets.QPlainTextEdit(text, font=monospace())
        self.text.setTabStopDistance(4 * self.text.fontMetrics().horizontalAdvance(' '))
        self.highlighter = Highlighter(self.text.document(), PYTHON_RULES)
        run = QtWidgets.QPushButton('RUN')
        run.clicked.connect(self.run)
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.addWidget(self.text)
        layout.addWidget(run)
        self.setCentralWidget(central)
        self.resize(800, 700)
        add_menus(self, {'File': {
            'New script': lambda: show_window(PythonEditor()),
            'Open': self.open,
            'Save As...': self.save_as,
            'Save': self.save,
            'Quit': self.close,
        }})
        if filename and not text and os.path.isfile(filename):
            self.load(filename)
        self.setWindowTitle(filename or 'Python Editor')

    def load(self, filename: str):
        with open(filename) as f:
            self.text.setPlainText(f.read())
        self.filename = filename
        self.setWindowTitle(filename)

    def open(self):
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Open script', '', 'Python (*.py)')
        if filename:
            self.load(filename)

    def save_as(self):
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(self, 'Save script', self.filename, 'Python (*.py)')
        if filename:
            self.filename = filename
            self.save()

    def save(self):
        if not self.filename:
            return self.save_as()
        with open(self.filename, 'w') as f:
            f.write(self.text.toPlainText())
        self.setWindowTitle(self.filename)

    def run(self):
        self.save()
        if self.filename:
            run_python_script(self.filename)


class LogViewer(QtWidgets.QMainWindow):
    """GDA terminal log, one tab per day, with search"""

    def __init__(self, filename: str):
        super().__init__()
        self.setWindowTitle(f"Log Viewer: {filename}")
        self.tabs = QtWidgets.QTabWidget()
        self.highlighters = []
        for title, lines in read_gda_terminal_log(filename).items():
            text = QtWidgets.QPlainTextEdit('\n'.join(lines), readOnly=True, font=monospace())
            text.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
            self.highlighters.append(Highlighter(text.document(), LOG_RULES))
            self.tabs.addTab(text, title)
        self.tabs.setCurrentIndex(self.tabs.count() - 1)

        self.search = QtWidgets.QLineEdit(placeholderText='Search...')
        self.search.returnPressed.connect(self.find)
        self.case = QtWidgets.QCheckBox('Case')
        self.all_dates = QtWidgets.QCheckBox('All Dates')
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.search, stretch=1)
        row.addWidget(self.case)
        row.addWidget(self.all_dates)
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.addLayout(row)
        layout.addWidget(self.tabs)
        self.setCentralWidget(central)
        self.resize(1000, 700)
        add_menus(self, {})

    def find(self):
        """Find the next match in this tab, or in the following tabs if 'All Dates' is ticked"""
        flags = QTextDocument.FindCaseSensitively if self.case.isChecked() else QTextDocument.FindFlag(0)
        start = self.tabs.currentIndex()
        tabs = range(start, self.tabs.count()) if self.all_dates.isChecked() else [start]
        for index in tabs:
            text = self.tabs.widget(index)
            if text.find(self.search.text(), flags):
                self.tabs.setCurrentIndex(index)
                return
            text.moveCursor(text.textCursor().MoveOperation.Start)  # wrap to start for next search


def open_log_viewer(data_directory: str):
    filename = os.path.join(data_directory, 'gdaterminal.log')
    if not os.path.isfile(filename):
        show_error(None, f"{filename} does not exist!")
        return
    show_window(LogViewer(filename))
