"""
App-wide look: light and dark palettes, a stylesheet and matching matplotlib colours
"""
import os
import tempfile

import matplotlib

from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QColor, QFont, QGuiApplication

FONTS = ['Inter', 'Segoe UI', 'Cantarell', 'Noto Sans', 'Ubuntu', 'DejaVu Sans', 'Liberation Sans', 'Arial']
ACCENT = '#2563eb'

THEMES = {
    'light': {
        'window': '#f3f4f6', 'base': '#ffffff', 'alt': '#f9fafb', 'text': '#111827', 'muted': '#6b7280',
        'border': '#d1d5db', 'hover': '#e5e7eb', 'accent': ACCENT, 'accent_text': '#ffffff',
        'error': '#dc2626', 'grid': '#e5e7eb',
    },
    'dark': {
        'window': '#1f2329', 'base': '#16191d', 'alt': '#1b1e23', 'text': '#e5e7eb', 'muted': '#9ca3af',
        'border': '#374151', 'hover': '#2b3038', 'accent': '#3b82f6', 'accent_text': '#ffffff',
        'error': '#f87171', 'grid': '#2b3038',
    },
}
CURRENT = dict(THEMES['light'])

STYLESHEET = """
QWidget {{ color: {text}; }}
QMainWindow, QDialog {{ background: {window}; }}
QToolTip {{ background: {base}; color: {text}; border: 1px solid {border}; padding: 4px; }}
QFrame#card, QFrame#plot {{ background: {base}; border: 1px solid {border}; border-radius: 8px; }}
QLabel#title {{ font-weight: 600; }}
QLabel#muted {{ color: {muted}; }}
QLabel#error {{ color: {error}; }}
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {base}; border: 1px solid {border}; border-radius: 6px; padding: 3px 6px;
    selection-background-color: {accent}; selection-color: {accent_text};
}}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {accent};
}}
QComboBox::drop-down {{ border: none; width: 18px; }}
QPushButton, QToolButton {{
    background: {base}; border: 1px solid {border}; border-radius: 6px; padding: 4px 12px;
}}
QPushButton:hover, QToolButton:hover {{ background: {hover}; }}
QPushButton:pressed, QPushButton:checked, QToolButton:checked {{ background: {hover}; border-color: {accent}; }}
QPushButton[primary="true"] {{ background: {accent}; color: {accent_text}; border-color: {accent}; font-weight: 600; }}
QPushButton[primary="true"]:hover {{ background: {accent}; border-color: {text}; }}
QToolButton::menu-indicator {{ image: none; }}
QToolBar {{ background: {base}; border: none; spacing: 0px; }}
QToolBar QToolButton {{ border: none; padding: 3px; background: {base}; }}
QToolBar QToolButton:hover {{ background: {hover}; }}
QToolBar QToolButton:checked {{ background: {hover}; }}
QComboBox::down-arrow, QAbstractSpinBox::down-arrow {{ image: url({arrow_down}); width: 10px; height: 10px; }}
QAbstractSpinBox::up-arrow {{ image: url({arrow_up}); width: 10px; height: 10px; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ border: none; width: 16px; background: transparent; }}
QTreeView, QTreeWidget, QListWidget, QTableView {{
    background: {base}; alternate-background-color: {alt}; border: 1px solid {border}; border-radius: 6px;
    selection-background-color: {accent}; selection-color: {accent_text};
}}
QTreeView::item, QListWidget::item {{ padding: 2px 0px; }}
QHeaderView::section {{
    background: {window}; color: {muted}; border: none; border-bottom: 1px solid {border};
    padding: 4px 6px; font-weight: 600;
}}
QTabWidget::pane {{ border: 1px solid {border}; border-radius: 6px; background: {base}; top: -1px; }}
QTabBar::tab {{ background: transparent; color: {muted}; padding: 6px 14px; border: none;
    border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {text}; border-bottom: 2px solid {accent}; }}
QTabBar::tab:hover {{ color: {text}; }}
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:hover {{ background: {accent}; }}
QMenuBar {{ background: {window}; border-bottom: 1px solid {border}; }}
QMenuBar::item {{ padding: 4px 10px; background: transparent; border-radius: 4px; }}
QMenuBar::item:selected {{ background: {hover}; }}
QMenu {{ background: {base}; border: 1px solid {border}; padding: 4px; }}
QMenu::item {{ padding: 5px 24px 5px 20px; border-radius: 4px; }}
QMenu::item:selected {{ background: {accent}; color: {accent_text}; }}
QMenu::separator {{ height: 1px; background: {border}; margin: 4px 8px; }}
QScrollBar:vertical {{ width: 10px; background: transparent; margin: 0; }}
QScrollBar:horizontal {{ height: 10px; background: transparent; margin: 0; }}
QScrollBar::handle {{ background: {border}; border-radius: 5px; min-height: 24px; min-width: 24px; }}
QScrollBar::handle:hover {{ background: {muted}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
    background: none; border: none; width: 0; height: 0;
}}
QSlider::groove:horizontal {{ height: 4px; background: {border}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {accent}; width: 14px; height: 14px; margin: -6px 0; border-radius: 7px; }}
QCheckBox {{ spacing: 6px; }}
QCheckBox::indicator, QTreeView::indicator, QListView::indicator {{
    width: 14px; height: 14px; border: 1px solid {muted}; border-radius: 4px; background: {base};
}}
QCheckBox::indicator:checked, QTreeView::indicator:checked, QListView::indicator:checked {{
    background: {accent}; border-color: {accent}; image: url({check});
}}
QStatusBar {{ color: {muted}; }}
"""


ARROW_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
             '<path d="{path}" fill="none" stroke="{colour}" stroke-width="1.6" stroke-linecap="round"/></svg>')


def icon_files(colours: dict) -> dict[str, str]:
    """Write small SVG icons in the theme colours: combo/spin box arrows and a check mark"""
    folder = os.path.join(tempfile.gettempdir(), 'mmg_qt_dataviewer_icons')
    os.makedirs(folder, exist_ok=True)
    files = {}
    for name, path, colour in [('arrow_down', 'M2 3.5 L5 6.5 L8 3.5', colours['muted']),
                               ('arrow_up', 'M2 6.5 L5 3.5 L8 6.5', colours['muted']),
                               ('check', 'M2.2 5.2 L4.2 7.2 L7.8 3', colours['accent_text'])]:
        filename = os.path.join(folder, f"{name}_{colour.strip('#')}.svg")
        with open(filename, 'w') as f:
            f.write(ARROW_SVG.format(path=path, colour=colour))
        files[name] = filename.replace(os.sep, '/')
    return files


def system_theme() -> str:
    scheme = QGuiApplication.styleHints().colorScheme()
    return 'dark' if scheme == Qt.ColorScheme.Dark else 'light'


def apply_theme(app: QtWidgets.QApplication, theme: str = 'system'):
    """Apply 'light', 'dark' or 'system' colours to the whole application"""
    colours = THEMES[system_theme() if theme == 'system' else theme]
    CURRENT.clear()
    CURRENT.update(colours)
    app.setStyle('Fusion')
    palette = QPalette()
    for role, name in [(QPalette.Window, 'window'), (QPalette.Base, 'base'), (QPalette.AlternateBase, 'alt'),
                       (QPalette.WindowText, 'text'), (QPalette.Text, 'text'), (QPalette.ButtonText, 'text'),
                       (QPalette.Button, 'base'), (QPalette.Highlight, 'accent'),
                       (QPalette.HighlightedText, 'accent_text'), (QPalette.PlaceholderText, 'muted'),
                       (QPalette.ToolTipBase, 'base'), (QPalette.ToolTipText, 'text'), (QPalette.Link, 'accent')]:
        palette.setColor(role, QColor(colours[name]))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(colours['muted']))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(colours['muted']))
    app.setPalette(palette)
    app.setStyleSheet(STYLESHEET.format(**colours, **icon_files(colours)))
    matplotlib.rcParams.update({  # also applies to pop-out pyplot figures and legends
        'figure.facecolor': colours['base'], 'axes.facecolor': colours['base'],
        'axes.edgecolor': colours['border'], 'axes.labelcolor': colours['text'], 'text.color': colours['text'],
        'xtick.color': colours['muted'], 'ytick.color': colours['muted'], 'grid.color': colours['grid'],
        'xtick.labelcolor': colours['text'], 'ytick.labelcolor': colours['text'],
        'savefig.facecolor': 'white', 'savefig.edgecolor': 'white',
    })
    for window in app.topLevelWidgets():  # restyle open plots
        for canvas in window.findChildren(QtWidgets.QWidget, 'plot'):
            canvas.style_axes()
            canvas.draw()


def setup_fonts(app: QtWidgets.QApplication):
    """Use a clean sans-serif font, keeping the system's font size"""
    font = QFont(app.font())
    font.setFamilies(FONTS)
    app.setFont(font)


def style_axes(figure, axes):
    """Colour a matplotlib figure to match the current theme"""
    c = CURRENT
    figure.set_facecolor(c['base'])
    for ax in axes:
        ax.set_facecolor(c['base'])
        ax.tick_params(colors=c['muted'], labelcolor=c['text'], labelsize=9)
        for side, spine in ax.spines.items():
            spine.set_color(c['border'])
            spine.set_visible(side in ('left', 'bottom'))
        ax.xaxis.label.set_color(c['text'])
        ax.yaxis.label.set_color(c['text'])
        ax.title.set_color(c['text'])
        ax.grid(True, color=c['grid'], linewidth=0.8)
        ax.set_axisbelow(True)


def card(*widgets: QtWidgets.QWidget, layout: QtWidgets.QLayout | None = None, title: str = '') -> QtWidgets.QFrame:
    """A rounded panel containing widgets or a layout, with an optional title"""
    frame = QtWidgets.QFrame(objectName='card')
    box = QtWidgets.QVBoxLayout(frame)
    box.setContentsMargins(10, 8, 10, 10)
    box.setSpacing(6)
    if title:
        box.addWidget(QtWidgets.QLabel(title, objectName='title'))
    for widget in widgets:
        box.addWidget(widget)
    if layout is not None:
        box.addLayout(layout)
    return frame


def form(*rows) -> QtWidgets.QFormLayout:
    """Form of (label, widget or layout) rows, wrapping labels above fields on narrow windows"""
    layout = QtWidgets.QFormLayout()
    layout.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)
    layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
    layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
    for label, field in rows:
        layout.addRow(QtWidgets.QLabel(label, objectName='muted', minimumWidth=70), field)
    return layout


def row(*widgets, stretch: int | None = None) -> QtWidgets.QHBoxLayout:
    """Horizontal row of widgets, optionally stretching one of them"""
    layout = QtWidgets.QHBoxLayout()
    for n, widget in enumerate(widgets):
        if widget is None:
            layout.addStretch()
        elif isinstance(widget, QtWidgets.QLayout):
            layout.addLayout(widget)
        else:
            layout.addWidget(widget, stretch=1 if n == stretch else 0)
    return layout


def grid(widgets: list[QtWidgets.QWidget], columns: int) -> QtWidgets.QGridLayout:
    """Grid of widgets, filling rows of the given number of columns"""
    layout = QtWidgets.QGridLayout()
    for n, widget in enumerate(widgets):
        layout.addWidget(widget, n // columns, n % columns)
    return layout


def scrollable(widget: QtWidgets.QWidget) -> QtWidgets.QScrollArea:
    """Wrap a widget so it scrolls on screens too small to show it all"""
    area = QtWidgets.QScrollArea(widgetResizable=True, frameShape=QtWidgets.QFrame.NoFrame)
    area.setWidget(widget)
    return area


def heading(text: str = '', scale: float = 1.6) -> QtWidgets.QLabel:
    label = QtWidgets.QLabel(text)
    font = label.font()
    font.setPointSizeF(font.pointSizeF() * scale)
    font.setWeight(QFont.DemiBold)
    label.setFont(font)
    return label


def fit_to_screen(window: QtWidgets.QWidget, width: int, height: int):
    """Size a window to (width, height), or 92% of the available screen if smaller, and centre it"""
    screen = (window.screen() or QGuiApplication.primaryScreen()).availableGeometry()
    w = min(width, int(screen.width() * 0.92))
    h = min(height, int(screen.height() * 0.92))
    window.resize(w, h)
    window.move(screen.x() + (screen.width() - w) // 2, screen.y() + (screen.height() - h) // 2)
