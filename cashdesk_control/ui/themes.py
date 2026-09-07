"""Colour themes for the desktop shell.

Three themes ship with the application — dark, light and gray. They are defined
as token sets rather than three copies of the stylesheet, so a control only has
to be styled once and all three themes stay consistent.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any


@dataclass(frozen=True, slots=True)
class Theme:
    """One colour scheme."""

    key: str
    label: str
    is_dark: bool
    window: str
    surface: str
    surface_alt: str
    surface_hover: str
    surface_sunken: str
    border: str
    border_strong: str
    text: str
    text_muted: str
    text_dim: str
    accent: str
    accent_hover: str
    accent_soft: str
    accent_text: str
    ok: str
    ok_hover: str
    ok_text: str
    warn: str
    err: str
    info: str
    input_bg: str
    selection: str
    scrollbar: str
    scrollbar_hover: str
    font: str = '"Segoe UI", "Inter", "Ubuntu", "DejaVu Sans", sans-serif'
    mono: str = '"Cascadia Mono", "JetBrains Mono", "DejaVu Sans Mono", Consolas, monospace'

    def token(self, name: str) -> str:
        for field in fields(self):
            if field.name == name:
                return str(getattr(self, name))
        raise KeyError(name)

    def to_dict(self) -> dict[str, Any]:
        return {field.name: getattr(self, field.name) for field in fields(self)}


DARK = Theme(
    key="dark",
    label="Тёмная",
    is_dark=True,
    window="#0d1015",
    surface="#161b23",
    surface_alt="#1b222c",
    surface_hover="#232c39",
    surface_sunken="#0a0d12",
    border="#252e3c",
    border_strong="#3a4658",
    text="#e9eef6",
    text_muted="#94a0b3",
    text_dim="#68748a",
    accent="#5b8cff",
    accent_hover="#7ba2ff",
    accent_soft="#1d2942",
    accent_text="#ffffff",
    ok="#3fc99a",
    ok_hover="#55dcae",
    ok_text="#06231a",
    warn="#e8b15c",
    err="#f2647c",
    info="#58b6e8",
    input_bg="#11161e",
    selection="#2f4d9c",
    scrollbar="#313c4d",
    scrollbar_hover="#4a5a72",
)

LIGHT = Theme(
    key="light",
    label="Светлая",
    is_dark=False,
    window="#eef1f6",
    surface="#ffffff",
    surface_alt="#f6f8fc",
    surface_hover="#e8edf6",
    surface_sunken="#e6eaf2",
    border="#d7dee9",
    border_strong="#b8c2d2",
    text="#18202e",
    text_muted="#5b6678",
    text_dim="#8b95a6",
    accent="#2f6bff",
    accent_hover="#1c58ea",
    accent_soft="#e4ecff",
    accent_text="#ffffff",
    ok="#12a06c",
    ok_hover="#0e8a5c",
    ok_text="#ffffff",
    warn="#b57614",
    err="#cf3352",
    info="#1f7fb8",
    input_bg="#ffffff",
    selection="#c3d6ff",
    scrollbar="#c9d2e0",
    scrollbar_hover="#a9b5c8",
)

GRAY = Theme(
    key="gray",
    label="Серая",
    is_dark=True,
    window="#2b2f36",
    surface="#333841",
    surface_alt="#3a404a",
    surface_hover="#454c58",
    surface_sunken="#25282e",
    border="#464d59",
    border_strong="#5c6472",
    text="#e7eaef",
    text_muted="#b3bac6",
    text_dim="#8d95a2",
    accent="#7f9cf5",
    accent_hover="#9bb1f8",
    accent_soft="#3d4763",
    accent_text="#ffffff",
    ok="#6fd0a8",
    ok_hover="#8adcb9",
    ok_text="#0d2a20",
    warn="#e0bb72",
    err="#e8879a",
    info="#84bcd8",
    input_bg="#292d34",
    selection="#4c5a80",
    scrollbar="#525a67",
    scrollbar_hover="#6d7787",
)

THEMES: dict[str, Theme] = {theme.key: theme for theme in (DARK, LIGHT, GRAY)}
DEFAULT_THEME = DARK.key


def get_theme(key: str | None) -> Theme:
    """Return the theme for *key*, falling back to dark."""

    return THEMES.get((key or DEFAULT_THEME).lower(), DARK)


def theme_keys() -> tuple[str, ...]:
    return tuple(THEMES)


_QSS_TEMPLATE = r"""
/* Касса Control — тема «{label}» */
* {{ font-family: {font}; font-size: 12px; color: {text}; }}

QMainWindow, QDialog, QWidget#root {{ background: {window}; }}
QFrame#sidebar {{ background: {surface}; border-right: 1px solid {border}; }}
QFrame#content {{ background: {window}; }}
QFrame#topbar {{ background: {surface}; border-bottom: 1px solid {border}; }}
QFrame#sessionHeader {{ background: {surface}; border-bottom: 1px solid {border}; }}
QFrame#tabBar {{ background: {surface}; border-bottom: 1px solid {border}; }}

QLabel {{ background: transparent; }}
QLabel#brand {{ font-size: 15px; font-weight: 800; letter-spacing: 2px; color: {text}; }}
QLabel#brandSub {{ font-size: 8px; font-weight: 700; letter-spacing: 3px; color: {text_dim}; }}
QLabel#eyebrow {{ font-size: 9px; font-weight: 700; letter-spacing: 1.3px; color: {text_dim}; }}
QLabel#eyebrowAccent {{ font-size: 9px; font-weight: 700; letter-spacing: 1.3px; color: {accent}; }}
QLabel#pageTitle {{ font-size: 21px; font-weight: 750; color: {text}; }}
QLabel#sectionTitle {{ font-size: 14px; font-weight: 700; color: {text}; }}
QLabel#muted {{ font-size: 11px; color: {text_muted}; }}
QLabel#dim {{ font-size: 10px; color: {text_dim}; }}
QLabel#metricValue {{ font-size: 23px; font-weight: 750; color: {text}; }}
QLabel#metricLabel {{ font-size: 10px; font-weight: 600; color: {text_muted}; }}
QLabel#mono {{ font-family: {mono}; font-size: 11px; }}
QLabel#statusOnline {{ color: {ok}; font-size: 10px; font-weight: 700; }}
QLabel#statusWarning {{ color: {warn}; font-size: 10px; font-weight: 700; }}
QLabel#statusOffline {{ color: {text_dim}; font-size: 10px; font-weight: 700; }}
QLabel#statusError {{ color: {err}; font-size: 10px; font-weight: 700; }}
QLabel#sessionName {{ font-size: 11px; font-weight: 650; color: {text}; }}
QLabel#sessionMeta {{ font-size: 9px; color: {text_dim}; }}

QFrame#panel, QFrame#metric {{ background: {surface}; border: 1px solid {border}; border-radius: 10px; }}
QFrame#panel:hover, QFrame#metric:hover {{ border-color: {border_strong}; }}
QFrame#metricOk {{ background: {surface}; border: 1px solid {ok}; border-radius: 10px; }}
QFrame#metricWarn {{ background: {surface}; border: 1px solid {warn}; border-radius: 10px; }}
QFrame#metricErr {{ background: {surface}; border: 1px solid {err}; border-radius: 10px; }}
QFrame#metricInfo {{ background: {surface}; border: 1px solid {accent}; border-radius: 10px; }}
QFrame#statusStrip {{ background: {surface}; border-top: 1px solid {border}; }}
QFrame#divider {{ background: {border}; max-height: 1px; border: 0; }}

QPushButton {{
    min-height: 30px; padding: 0 12px; border: 1px solid transparent;
    border-radius: 7px; color: {text_muted}; background: transparent;
}}
QPushButton:hover {{ color: {text}; background: {surface_hover}; border-color: {border_strong}; }}
QPushButton:pressed {{ background: {selection}; color: {text}; }}
QPushButton:disabled {{ color: {text_dim}; background: transparent; border-color: {border}; }}
QPushButton#primary {{ color: {accent_text}; background: {accent}; font-weight: 700; border: 0; }}
QPushButton#primary:hover {{ background: {accent_hover}; color: {accent_text}; }}
QPushButton#primary:disabled {{ background: {border}; color: {text_dim}; }}
QPushButton#success {{ color: {ok_text}; background: {ok}; font-weight: 700; border: 0; }}
QPushButton#success:hover {{ background: {ok_hover}; color: {ok_text}; }}
QPushButton#success:pressed {{ background: {ok}; }}
QPushButton#success:disabled {{ background: {border}; color: {text_dim}; }}
QPushButton#secondary {{ color: {text}; background: {surface_alt}; border: 1px solid {border_strong}; }}
QPushButton#secondary:hover {{ background: {surface_hover}; }}
QPushButton#danger {{ color: {accent_text}; background: {err}; font-weight: 700; border: 0; }}
QPushButton#danger:hover {{ background: {err}; color: {accent_text}; }}
QPushButton#warnButton {{ color: {accent_text}; background: {warn}; font-weight: 700; border: 0; }}
QPushButton#nav {{ text-align: left; padding-left: 12px; }}
QPushButton#nav:checked {{ color: {text}; background: {accent_soft}; border-left: 2px solid {accent}; }}
QPushButton#tab {{ min-height: 40px; border-radius: 0; color: {text_dim}; padding: 0 14px; border-bottom: 2px solid transparent; }}
QPushButton#tab:hover {{ color: {text}; background: {surface_alt}; }}
QPushButton#tab:checked {{ color: {accent}; border-bottom: 2px solid {accent}; font-weight: 650; }}
QPushButton#session {{ min-height: 52px; padding: 6px 9px; text-align: left; border: 1px solid transparent; border-radius: 9px; }}
QPushButton#session:hover {{ background: {surface_alt}; }}
QPushButton#session:checked {{ background: {accent_soft}; border: 1px solid {accent}; }}
QPushButton#commandButton {{ text-align: left; padding: 6px 10px; min-height: 34px; border: 1px solid {border}; background: {surface_alt}; color: {text}; }}
QPushButton#commandButton:hover {{ border-color: {accent}; background: {surface_hover}; }}
QPushButton#commandDanger {{ text-align: left; padding: 6px 10px; min-height: 34px; border: 1px solid {err}; background: {surface_alt}; color: {text}; }}
QPushButton#commandDanger:hover {{ background: {err}; color: {accent_text}; }}
QPushButton#commandCritical {{ text-align: left; padding: 6px 10px; min-height: 34px; border: 1px solid {err}; background: {surface_alt}; color: {text}; font-weight: 700; }}
QPushButton#commandCritical:hover {{ background: {err}; color: {accent_text}; }}
QPushButton#link {{ color: {accent}; border: 0; padding: 0; min-height: 18px; }}
QPushButton#link:hover {{ color: {accent_hover}; background: transparent; }}

QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    color: {text}; background: {input_bg}; border: 1px solid {border};
    border-radius: 7px; padding: 6px 9px; selection-background-color: {selection};
    selection-color: {text};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {accent}; }}
QLineEdit:read-only {{ color: {text_muted}; }}
QComboBox::drop-down {{ border: 0; width: 22px; }}
QComboBox QAbstractItemView {{ background: {surface}; border: 1px solid {border_strong}; color: {text}; selection-background-color: {selection}; }}
QCheckBox {{ color: {text_muted}; spacing: 7px; }}
QCheckBox::indicator {{ width: 15px; height: 15px; border: 1px solid {border_strong}; border-radius: 4px; background: {input_bg}; }}
QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; }}
QRadioButton::indicator {{ width: 14px; height: 14px; border: 1px solid {border_strong}; border-radius: 7px; background: {input_bg}; }}
QRadioButton::indicator:checked {{ background: {accent}; border-color: {accent}; }}

QPlainTextEdit#terminalView, QTextEdit#terminalOutput, QPlainTextEdit#sqlEditor, QTextEdit#reportView {{
    background: {surface_sunken}; border: 1px solid {border}; color: {text};
    font-family: {mono}; font-size: 11px;
}}
QPlainTextEdit#terminalView {{ border-radius: 8px; }}

QTableView, QTreeView, QTreeWidget, QTableWidget, QListView {{
    background: {surface}; alternate-background-color: {surface_alt};
    border: 1px solid {border}; border-radius: 8px; gridline-color: {border}; color: {text};
}}
QTableView::item:selected, QTreeView::item:selected, QTreeWidget::item:selected, QListView::item:selected {{
    background: {selection}; color: {text};
}}
QHeaderView::section {{
    background: {surface_alt}; color: {text_muted}; border: 0;
    border-bottom: 1px solid {border}; padding: 7px; font-size: 10px; font-weight: 650;
}}
QListWidget#sessionList {{ background: transparent; border: 0; outline: 0; }}

QTabWidget::pane {{ border: 0; background: {window}; }}
QScrollArea {{ border: 0; background: transparent; }}
QSplitter::handle {{ background: {border}; }}
QSplitter::handle:horizontal {{ width: 3px; }}
QSplitter::handle:vertical {{ height: 3px; }}

QProgressBar {{ background: {surface_alt}; border: 0; border-radius: 4px; height: 8px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {accent}; border-radius: 4px; }}

QScrollBar:vertical {{ width: 9px; background: transparent; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {scrollbar}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {scrollbar_hover}; }}
QScrollBar:horizontal {{ height: 9px; background: transparent; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {scrollbar}; border-radius: 4px; min-width: 30px; }}
QScrollBar::handle:horizontal:hover {{ background: {scrollbar_hover}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QDockWidget {{ color: {text}; titlebar-close-icon: none; }}
QDockWidget::title {{ background: {surface_alt}; padding: 8px 12px; border-bottom: 1px solid {border}; font-weight: 700; }}
QStatusBar {{ background: {surface}; color: {text_muted}; border-top: 1px solid {border}; }}
QStatusBar::item {{ border: 0; }}
QMenuBar {{ background: {surface}; color: {text_muted}; border-bottom: 1px solid {border}; }}
QMenuBar::item:selected {{ background: {surface_hover}; color: {text}; }}
QMenu {{ background: {surface}; color: {text}; border: 1px solid {border_strong}; padding: 4px; }}
QMenu::item {{ padding: 6px 22px 6px 14px; border-radius: 5px; }}
QMenu::item:selected {{ background: {accent_soft}; color: {text}; }}
QMenu::separator {{ height: 1px; background: {border}; margin: 4px 8px; }}
QToolTip {{ background: {surface_alt}; color: {text}; border: 1px solid {border_strong}; padding: 5px; }}
QGroupBox {{ border: 1px solid {border}; border-radius: 8px; margin-top: 12px; padding-top: 6px; color: {text_muted}; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}
"""


def build_qss(theme: Theme) -> str:
    """Render the stylesheet for *theme*."""

    return _QSS_TEMPLATE.format(**theme.to_dict())


def qss_for(key: str | None) -> str:
    return build_qss(get_theme(key))


#: Kept for modules written against the earlier single-theme API.
APP_QSS = build_qss(DARK)
