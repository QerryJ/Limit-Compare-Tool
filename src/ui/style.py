"""Qt stylesheet generated from the design tokens.

``docs/design-system/tokens.css`` stays the single source of truth: colours,
radii and spacing used by the Qt chrome are read from it at runtime, so the
desktop UI cannot drift away from the documented design system (the same rule
the HTML report already follows).
"""

import re

from src.ui.theme import token

_NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?$")


def is_numeric(text: str) -> bool:
    """True when a cell holds a plain number (should be mono + right aligned)."""
    return bool(_NUM_RE.match(str(text).strip()))


def _family(css_name: str, fallback: str) -> str:
    """Turn a CSS font stack into a Qt stylesheet font family list."""
    raw = token(css_name)
    names = []
    for part in raw.split(","):
        name = part.strip().strip('"').strip("'")
        if not name or name in ("system-ui", "sans-serif", "monospace"):
            continue
        names.append(f'"{name}"')
    return ", ".join(names) if names else f'"{fallback}"'


def mono_family() -> str:
    """Monospace family for numeric columns (token ``--lc-numeric-font``)."""
    return _family("--lc-font-mono", "Consolas")


def _first_px(css_name: str, default: int) -> int:
    """Read the first px value out of a token (e.g. ``6px 8px`` -> ``6``)."""
    raw = token(css_name)
    match = re.search(r"(\d+(?:\.\d+)?)\s*px", raw)
    return int(float(match.group(1))) if match else default


def _css_color(css_name: str) -> str:
    """Return a Qt-stylesheet-safe colour (converts CSS ``rgba()`` alpha)."""
    raw = token(css_name)
    match = re.match(
        r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)",
        raw,
    )
    if not match:
        return raw or "#000000"
    r, g, b = (int(float(match.group(i))) for i in (1, 2, 3))
    if match.group(4) is None:
        return f"rgb({r}, {g}, {b})"
    alpha = float(match.group(4))
    if alpha <= 1.0:
        alpha = round(alpha * 255)
    return f"rgba({r}, {g}, {b}, {int(alpha)})"


def build_stylesheet(density: str = "comfortable") -> str:
    """Build the full application stylesheet for the given density."""
    bg = _css_color("--lc-bg")
    surface = _css_color("--lc-surface")
    hover = _css_color("--lc-surface-hover")
    pressed = _css_color("--lc-surface-pressed")
    border = _css_color("--lc-border")
    strong = _css_color("--lc-border-strong")
    text = _css_color("--lc-text")
    muted = _css_color("--lc-text-muted")
    hint = _css_color("--lc-text-hint")
    accent = _css_color("--lc-accent")
    accent_hover = _css_color("--lc-accent-hover")
    accent_text = _css_color("--lc-accent-text")
    selection = _css_color("--lc-selection-bg")
    row_alt = _css_color("--lc-row-alt")
    input_bg = _css_color("--lc-input-bg")

    radius = _first_px("--lc-radius-md", 8)
    radius_lg = _first_px("--lc-radius-lg", 12)
    pad_v = _first_px("--lc-density-cell-padding", 6)
    compact = density == "compact"
    fs = "12px" if compact else "13px"
    pad_v = max(3, pad_v - 2) if compact else pad_v
    sans = _family("--lc-font-sans", "Microsoft YaHei UI")

    return f"""
/* ---- base -------------------------------------------------------------
   注意：不能给裸 QWidget 设 background——它会级联到表格视口等子部件，
   把斑马纹和选中色盖掉。这里只对明确的容器设置背景。 */
QWidget {{
    color: {text};
    font-family: {sans};
    font-size: {fs};
}}
QMainWindow, QWidget#body {{ background: {surface}; }}

/* ---- toolbar ---------------------------------------------------------- */
QToolBar {{
    background: {bg};
    border: none;
    border-bottom: 1px solid {border};
    padding: {6 if not compact else 4}px 10px;
    spacing: 6px;
}}
QToolBar QLabel {{ color: {muted}; padding: 0 2px; }}
QToolBar QToolButton, QToolBar QPushButton {{ margin: 0 2px; }}

/* ---- buttons ---------------------------------------------------------- */
QPushButton {{
    background: {surface};
    border: 1px solid {border};
    border-radius: {radius}px;
    padding: {pad_v - 1 if pad_v > 3 else 3}px 12px;
    color: {text};
}}
QPushButton:hover {{ background: {hover}; border-color: {strong}; }}
QPushButton:pressed {{ background: {pressed}; }}
QPushButton:disabled {{ color: {hint}; background: {surface}; border-color: {border}; }}
QPushButton#primary {{
    background: {accent};
    border: 1px solid {accent};
    color: {accent_text};
    font-weight: 500;
}}
QPushButton#primary:hover {{ background: {accent_hover}; border-color: {accent_hover}; }}
QPushButton#primary:pressed {{ background: {accent_hover}; }}

/* ---- inputs ----------------------------------------------------------- */
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {{
    background: {input_bg};
    border: 1px solid {border};
    border-radius: {radius}px;
    padding: {max(3, pad_v - 2)}px 8px;
    selection-background-color: {selection};
}}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {{
    border-color: {accent};
}}
QLineEdit:disabled, QComboBox:disabled {{ color: {hint}; background: {surface}; }}
/* 拖拽悬停目标高亮：属性选择器 + 重新 polish，让用户看清文件会落到哪一栏 */
QLineEdit[dropTarget="true"] {{
    border: 2px solid {accent};
    background: {selection};
}}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{
    border: 1px solid {border};
    border-radius: {radius}px;
    background: {input_bg};
    selection-background-color: {selection};
    padding: 4px;
}}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ width: 16px; }}

/* ---- panels ----------------------------------------------------------- */
QFrame#panel {{
    background: {bg};
    border: 1px solid {border};
    border-radius: {radius_lg}px;
}}
QFrame#panel QLabel {{ background: transparent; }}

/* ---- table ------------------------------------------------------------ */
QTableWidget {{
    background: {bg};
    alternate-background-color: {row_alt};
    gridline-color: {border};
    border: 1px solid {border};
    border-radius: {radius}px;
    selection-background-color: {selection};
    selection-color: {text};
}}
QTableWidget::item {{ padding: 2px 6px; }}
QTableWidget::item:selected {{ background: {selection}; color: {text}; }}
QHeaderView::section {{
    background: {surface};
    color: {muted};
    border: none;
    border-bottom: 1px solid {border};
    border-right: 1px solid {border};
    padding: {pad_v}px 8px;
    font-weight: 500;
}}
QHeaderView::section:hover {{ background: {hover}; color: {text}; }}

/* ---- file list -------------------------------------------------------- */
QListWidget {{
    background: {input_bg};
    border: 1px solid {border};
    border-radius: {radius}px;
    padding: 4px;
    alternate-background-color: {row_alt};
}}
QListWidget::item {{ padding: 3px 6px; border-radius: 4px; }}
QListWidget::item:selected {{ background: {selection}; color: {text}; }}

/* ---- labels ----------------------------------------------------------- */
QLabel#caption {{ color: {muted}; font-size: 12px; }}
QLabel#hint {{ color: {hint}; font-size: 12px; }}
QLabel#author {{ color: {muted}; font-size: 12px; padding-right: 6px; }}
QLabel#summary {{
    background: {surface};
    border-radius: {radius}px;
    padding: 8px 10px;
    font-size: 12px;
}}

/* ---- status bar & scrollbars ------------------------------------------ */
QStatusBar {{
    background: {surface};
    border-top: 1px solid {border};
    color: {muted};
    font-size: 12px;
}}
QScrollBar:vertical {{ background: {bg}; width: 10px; margin: 0; border: none; }}
QScrollBar:horizontal {{ background: {bg}; height: 10px; margin: 0; border: none; }}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: {strong}; border-radius: 5px; min-height: 24px; min-width: 24px;
}}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
    background: {muted};
}}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QToolTip {{
    background: {surface}; color: {text};
    border: 1px solid {border}; border-radius: {radius}px; padding: 4px 6px;
}}
"""
