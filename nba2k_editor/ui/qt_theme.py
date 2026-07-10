from __future__ import annotations

# Qt port of the old editor theme. Keep these color names aligned with the
# deleted legacy theme so the PyQt shell keeps the same visual identity.
PRIMARY_BG = "#020812"
PANEL_BG = "#051426"
INPUT_BG = "#081B31"
ACCENT_BG = "#0D3872"
BUTTON_BG = "#0A2446"
BUTTON_ACTIVE_BG = "#134C91"
BUTTON_SELECTED_BG = "#135BA5"
TEXT_PRIMARY = "#EEF6FF"
TEXT_SECONDARY = "#7F99B8"
TEXT_HEADING = "#F6FBFF"
TEXT_LABEL = "#A3B8D2"
TEXT_ACCENT = "#35C9FF"
TEXT_SUCCESS = "#18E0D1"
TEXT_DANGER = "#F06A7C"
BUTTON_TEXT = "#F7FBFF"
TEXT_BADGE = "#B8D7FF"
INPUT_TEXT_FG = "#E6F1FF"
INPUT_PLACEHOLDER_FG = "#587495"
ENTRY_BG = INPUT_BG
ENTRY_ACTIVE_BG = "#0E2C54"
ENTRY_FG = BUTTON_TEXT
ENTRY_BORDER = "#0E3A71"


def editor_stylesheet() -> str:
    return f"""
    QMainWindow, QWidget {{
        background: {PRIMARY_BG};
        color: {TEXT_PRIMARY};
        font-family: "Tahoma", "Arial";
        font-size: 12px;
    }}

    #EditorRoot {{
        background: {PRIMARY_BG};
    }}

    #Sidebar {{
        background: #040a13;
        border: 0;
        border-radius: 0;
    }}

    QLabel#AppLogo {{
        background: #ff5648;
        color: white;
        border-radius: 5px;
        padding: 6px 7px;
        font-weight: bold;
    }}

    QLabel#SidebarTitle {{
        color: {TEXT_HEADING};
        font-size: 11px;
        font-weight: bold;
    }}

    QLabel#SidebarSubtitle, QLabel#SidebarSection, QLabel#SidebarFooter {{
        color: {TEXT_SECONDARY};
        font-size: 9px;
        letter-spacing: 1px;
    }}

    QLabel#SidebarSection {{
        padding: 8px 7px 2px 7px;
    }}

    QLabel#SidebarFooter {{
        color: {TEXT_SUCCESS};
        padding: 8px 8px;
        background: #071527;
        border: 1px solid #102844;
        border-radius: 8px;
    }}

    QLabel {{
        color: {TEXT_PRIMARY};
        background: transparent;
    }}

    QWidget#DashboardScreen {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {PRIMARY_BG}, stop:0.55 #03101f, stop:1 #160914);
    }}

    QLabel#DashboardEyebrow, QLabel#PanelEyebrow {{
        color: {TEXT_SUCCESS};
        font-size: 9px;
        font-weight: bold;
        letter-spacing: 2px;
    }}

    QLabel#DashboardTitle {{
        color: {TEXT_HEADING};
        font-size: 28px;
        font-weight: bold;
    }}

    QLabel#PanelTitle {{
        color: {TEXT_HEADING};
        font-size: 15px;
        font-weight: bold;
    }}

    QLabel#DashboardStatus {{
        color: {TEXT_SECONDARY};
    }}

    QLabel#LiveStatusChip {{
        color: {TEXT_SUCCESS};
        background: #071527;
        border: 1px solid {ENTRY_BORDER};
        border-radius: 10px;
        padding: 4px 10px;
    }}

    QWidget#MetricCard, QWidget#DashboardPanel {{
        background: rgba(7, 18, 34, 218);
        border: 1px solid #102844;
        border-radius: 10px;
    }}

    QLabel#MetricValue {{
        color: {TEXT_HEADING};
        font-size: 22px;
        font-weight: bold;
    }}

    QLabel#MetricCaption, QLabel#UpdateBody {{
        color: {TEXT_SECONDARY};
        font-size: 10px;
    }}

    QWidget#UpdateItem {{
        background: #07192d;
        border: 1px solid #12385f;
        border-radius: 9px;
    }}

    QLabel#UpdateBadge {{
        color: {TEXT_BADGE};
        background: {ACCENT_BG};
        border: 1px solid {TEXT_ACCENT};
        border-radius: 3px;
        padding: 2px 5px;
        font-size: 8px;
        font-weight: bold;
    }}

    QLabel#UpdateTitle {{
        color: {TEXT_HEADING};
        font-size: 13px;
        font-weight: bold;
    }}

    QPushButton#DashboardLinkButton {{
        text-align: left;
        background: #101827;
        border: 1px solid #1b2b44;
        border-radius: 8px;
        padding: 8px 10px;
    }}

    QPushButton#DashboardLinkButton:hover {{
        background: #13243a;
        border-color: {TEXT_ACCENT};
    }}

    QGroupBox, QTabWidget::pane {{
        background: {PANEL_BG};
        border: 1px solid {ENTRY_BORDER};
        border-radius: 0;
        margin-top: 4px;
    }}

    QGroupBox::title {{
        color: {TEXT_ACCENT};
        subcontrol-origin: margin;
        left: 6px;
        padding: 0 3px;
    }}

    QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QListWidget, QTableWidget, QSpinBox, QDoubleSpinBox {{
        background: {INPUT_BG};
        color: {INPUT_TEXT_FG};
        border: 1px solid {ENTRY_BORDER};
        border-radius: 0;
        padding: 3px 5px;
        selection-background-color: {ACCENT_BG};
        selection-color: {BUTTON_TEXT};
    }}

    QComboBox {{
        combobox-popup: 0;
    }}

    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QListWidget:focus, QTableWidget:focus {{
        background: {ENTRY_ACTIVE_BG};
        border: 1px solid {TEXT_ACCENT};
    }}

    QLineEdit:disabled, QTextEdit:disabled, QComboBox:disabled {{
        color: {TEXT_SECONDARY};
        background: {PANEL_BG};
    }}

    QComboBox::drop-down {{
        border: 0;
        width: 22px;
    }}

    QComboBox QAbstractItemView {{
        background: {PANEL_BG};
        color: {TEXT_PRIMARY};
        border: 1px solid {ENTRY_BORDER};
        selection-background-color: {ACCENT_BG};
    }}

    QTextEdit#DataOutput {{
        font-family: "Consolas", "Courier New", monospace;
        font-size: 10pt;
    }}

    QPushButton {{
        background: {BUTTON_BG};
        color: {BUTTON_TEXT};
        border: 1px solid {ENTRY_BORDER};
        border-radius: 0;
        padding: 3px 7px;
        font-weight: normal;
    }}

    QPushButton:hover {{
        background: {BUTTON_ACTIVE_BG};
        border: 1px solid {TEXT_ACCENT};
    }}

    QPushButton:pressed, QPushButton:checked {{
        background: {BUTTON_SELECTED_BG};
        border: 1px solid {TEXT_ACCENT};
    }}

    QPushButton:disabled {{
        background: {PANEL_BG};
        color: {TEXT_SECONDARY};
        border: 1px solid {ENTRY_BORDER};
    }}

    QPushButton#NavButton {{
        text-align: left;
        padding: 7px 10px;
        min-height: 28px;
        border-radius: 7px;
        border: 1px solid transparent;
        background: transparent;
        font-weight: normal;
    }}

    QPushButton#NavButton:hover {{
        background: #0b1727;
        border: 1px solid #1a2a44;
    }}

    QPushButton#NavButton:checked {{
        background: #111a2a;
        border: 1px solid #243550;
        color: {TEXT_HEADING};
    }}

    QListWidget#RecordList {{
        padding: 2px;
    }}

    QWidget#DetailRow QLabel:first-child {{
        color: {TEXT_LABEL};
    }}

    QWidget#EditableFieldRow {{
        background: transparent;
    }}

    QListWidget::item, QTableWidget::item {{
        padding: 2px 4px;
        color: {TEXT_PRIMARY};
    }}

    QListWidget::item:selected, QTableWidget::item:selected {{
        background: {ACCENT_BG};
        color: {BUTTON_TEXT};
    }}

    QHeaderView::section {{
        background: {BUTTON_BG};
        color: {BUTTON_TEXT};
        padding: 3px 5px;
        border: 1px solid {ENTRY_BORDER};
        font-weight: normal;
    }}

    QTableCornerButton::section {{
        background: {BUTTON_BG};
        border: 1px solid {ENTRY_BORDER};
    }}

    QTabBar::tab {{
        background: {BUTTON_BG};
        color: {BUTTON_TEXT};
        padding: 3px 7px;
        border: 1px solid {ENTRY_BORDER};
        border-top-left-radius: 0;
        border-top-right-radius: 0;
        margin-right: 1px;
    }}

    QTabBar::tab:hover {{
        background: {BUTTON_ACTIVE_BG};
    }}

    QTabBar::tab:selected {{
        background: {ACCENT_BG};
        color: {TEXT_HEADING};
        border-color: {TEXT_ACCENT};
    }}

    QSplitter::handle {{
        background: {PRIMARY_BG};
    }}

    QSplitter::handle:horizontal {{
        width: 6px;
    }}

    QScrollBar:vertical, QScrollBar:horizontal {{
        background: {PRIMARY_BG};
        border: 0;
        margin: 0;
    }}

    QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
        background: {ACCENT_BG};
        border-radius: 0;
        min-height: 24px;
        min-width: 24px;
    }}

    QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
        background: {BUTTON_ACTIVE_BG};
    }}

    QScrollBar::add-line, QScrollBar::sub-line {{
        height: 0;
        width: 0;
    }}

    QProgressBar {{
        background: {INPUT_BG};
        color: {TEXT_PRIMARY};
        border: 1px solid {ENTRY_BORDER};
        border-radius: 0;
        text-align: center;
    }}

    QProgressBar::chunk {{
        background: {TEXT_ACCENT};
        border-radius: 0;
    }}
    """


def apply_qt_theme(app: object) -> None:
    set_style = getattr(app, "setStyle", None)
    if callable(set_style):
        set_style("Fusion")
    set_stylesheet = getattr(app, "setStyleSheet", None)
    if callable(set_stylesheet):
        set_stylesheet(editor_stylesheet())
