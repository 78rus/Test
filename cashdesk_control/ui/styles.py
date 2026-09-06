"""Dark Cashdesk Control QSS theme."""

APP_QSS = r"""
* { font-family: "Inter", "Segoe UI", sans-serif; }
QMainWindow, QWidget#root { background: #0b0e13; color: #f3f5f9; }
QWidget { color: #e8edf5; font-size: 12px; }
QFrame#sidebar { background: #11151d; border-right: 1px solid #252d3a; }
QFrame#content { background: #0b0e13; }
QLabel#brand { color: #f3f5f9; font-size: 16px; font-weight: 800; letter-spacing: 2px; }
QLabel#brandSub { color: #657084; font-size: 8px; font-weight: 700; letter-spacing: 3px; }
QLabel#eyebrow { color: #657084; font-size: 9px; font-weight: 700; letter-spacing: 1.3px; }
QLabel#eyebrowAccent { color: #8da5ff; font-size: 9px; font-weight: 700; letter-spacing: 1.3px; }
QLabel#pageTitle { color: #f3f5f9; font-size: 22px; font-weight: 750; }
QLabel#muted { color: #919caf; font-size: 11px; }
QLabel#dim { color: #657084; font-size: 10px; }
QLabel#metricValue { color: #f3f5f9; font-size: 24px; font-weight: 750; }
QLabel#metricLabel { color: #919caf; font-size: 10px; font-weight: 600; }
QLabel#panelTitle { color: #f3f5f9; font-size: 14px; font-weight: 700; }
QLabel#panelEyebrow { color: #657084; font-size: 9px; font-weight: 700; letter-spacing: 1.2px; }
QFrame#panel, QFrame#metric { background: #151a23; border: 1px solid #252d3a; border-radius: 10px; }
QFrame#metric:hover, QFrame#panel:hover { border-color: #344157; }
QFrame#metricGreen { background: #151e20; border: 1px solid #25433a; border-radius: 10px; }
QFrame#metricBlue { background: #151a27; border: 1px solid #2b385c; border-radius: 10px; }
QFrame#metricViolet { background: #1a1726; border: 1px solid #3a2f5e; border-radius: 10px; }
QFrame#metricAmber { background: #211b16; border: 1px solid #4c3a24; border-radius: 10px; }
QPushButton { min-height: 32px; padding: 0 11px; border: 1px solid transparent; border-radius: 7px; color: #919caf; background: transparent; font-size: 11px; }
QPushButton:hover { color: #f3f5f9; background: #202735; border-color: #344157; }
QPushButton:pressed { background: #293246; }
QPushButton:disabled { color: #4f5b6d; }
QPushButton#primary { color: #0b1020; background: #6c8cff; font-weight: 700; }
QPushButton#primary:hover { background: #8da5ff; }
QPushButton#secondary { color: #c2cada; background: #151a23; border-color: #303a4b; }
QPushButton#secondary:hover { background: #202735; }
QPushButton#nav { text-align: left; padding-left: 11px; color: #919caf; }
QPushButton#nav:checked { color: #dbe1ff; background: #202b4a; border-left: 2px solid #6c8cff; }
QPushButton#tab { min-height: 44px; border-radius: 0; color: #657084; padding: 0 12px; border-bottom: 2px solid transparent; }
QPushButton#tab:hover { color: #c3ccdc; background: #151a23; }
QPushButton#tab:checked { color: #8da5ff; border-bottom-color: #6c8cff; }
QPushButton#session { min-height: 54px; padding: 6px 9px; text-align: left; border: 1px solid transparent; border-radius: 8px; }
QPushButton#session:hover { background: #1b222d; }
QPushButton#session:checked { background: #202b4a; border-color: #35477a; }
QLabel#sessionName { color: #e7eaf1; font-size: 11px; font-weight: 650; }
QLabel#sessionMeta { color: #657084; font-size: 9px; }
QLabel#statusOnline { color: #55d6a2; font-size: 10px; font-weight: 700; }
QLabel#statusWarning { color: #f2b767; font-size: 10px; font-weight: 700; }
QLabel#statusOffline { color: #657084; font-size: 10px; font-weight: 700; }
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox { color: #dce4ef; background: #11161e; border: 1px solid #2a3444; border-radius: 7px; padding: 6px 9px; selection-background-color: #394d9a; }
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus { border-color: #6c8cff; }
QTextEdit#terminalOutput, QPlainTextEdit#sqlEditor { background: #0b1016; border-color: #283342; color: #aeb9c7; font-family: "Cascadia Mono", "SFMono-Regular", Consolas, monospace; font-size: 11px; }
QTableWidget, QTreeWidget { background: #11161d; alternate-background-color: #151b24; border: 1px solid #252d3a; border-radius: 8px; gridline-color: #252d3a; color: #cbd3df; }
QHeaderView::section { background: #171d26; color: #657084; border: 0; border-bottom: 1px solid #252d3a; padding: 7px; font-size: 10px; font-weight: 650; }
QListWidget#sessionList { background: transparent; border: 0; outline: 0; }
QScrollArea { border: 0; background: transparent; }
QScrollBar:vertical { width: 7px; background: transparent; margin: 2px; }
QScrollBar::handle:vertical { background: #303b4c; border-radius: 3px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #4a5970; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QDialog { background: #161d28; }
QDialog QLabel { color: #919caf; }
QDialog QDialogButtonBox QPushButton { min-width: 80px; }
"""
