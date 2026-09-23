"""Bridge from the design tokens to Qt.

Single source of truth: ``docs/design-system/tokens.css``. Colours and density
are read from that file at runtime, so the UI can never drift away from the
documented design system.
"""

import os
import re
from typing import Dict

_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
TOKENS_CSS = os.path.join(_ROOT, "docs", "design-system", "tokens.css")


def _tokens_path() -> str:
    """Locate the token file, whether running from source or a frozen exe.

    PyInstaller unpacks bundled data into ``sys._MEIPASS``; the design tokens
    must stay the single source of truth in both cases.
    """
    import sys

    base = getattr(sys, "_MEIPASS", None)
    if base:
        frozen = os.path.join(base, "docs", "design-system", "tokens.css")
        if os.path.exists(frozen):
            return frozen
    return TOKENS_CSS

_FALLBACK = {
    "--lc-pass": "#639922",
    "--lc-pass-bg": "#eaf3de",
    "--lc-fail": "#a32d2d",
    "--lc-fail-bg": "#fcebeb",
    "--lc-warn": "#ba7517",
    "--lc-warn-bg": "#faeeda",
    "--lc-info": "#378add",
    "--lc-info-bg": "#e6f1fb",
    "--lc-neutral": "#888780",
    "--lc-neutral-bg": "#f1efe8",
    "--lc-verdict-offcentre": "#d85a30",
    "--lc-verdict-mixed": "#e24b4a",
    "--lc-bg": "#ffffff",
    "--lc-surface": "#f7f7f5",
    "--lc-border": "#e3e3df",
    "--lc-text": "#2c2c2a",
    "--lc-text-muted": "#5f5e5a",
    # 交互态（与 tokens.css 保持一致；冻结 exe 缺少 tokens.css 时兜底）
    "--lc-surface-hover": "#ececea",
    "--lc-surface-pressed": "#e2e2df",
    "--lc-accent": "#378add",
    "--lc-accent-hover": "#2f7ac4",
    "--lc-accent-text": "#ffffff",
    "--lc-selection-bg": "#dbe9f7",
    "--lc-row-alt": "#fbfbf9",
    "--lc-input-bg": "#ffffff",
    "--lc-density-row-height": "28px",
    "--lc-density-cell-padding": "6px 8px",
    "--lc-fs-body": "13px",
}

_TOKEN_RE = re.compile(r"(--[\w-]+)\s*:\s*([^;]+);")
_VAR_REF_RE = re.compile(r"var\((--[\w-]+)\)")


def load_tokens() -> Dict[str, str]:
    """Parse the token file into ``{name: value}``."""
    tokens = dict(_FALLBACK)
    try:
        with open(_tokens_path(), "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return tokens
    for name, value in _TOKEN_RE.findall(text):
        tokens[name] = value.strip()
    # Resolve var() references (one pass is enough for this token set).
    for name, value in list(tokens.items()):
        match = _VAR_REF_RE.search(value)
        if match:
            tokens[name] = tokens.get(match.group(1), _FALLBACK.get(name, value))
    return tokens


_TOKENS = load_tokens()


def token(name: str) -> str:
    return _TOKENS.get(name, _FALLBACK.get(name, ""))


def hex_color(name: str) -> str:
    """Return the token as a ``#rrggbb`` string usable by ``QColor``."""
    value = token(name)
    match = re.search(r"#([0-9a-fA-F]{6})", value)
    return "#" + match.group(1) if match else "#000000"


def row_height(density: str) -> int:
    """Row height in px for the given density."""
    if density == "compact":
        return int(token("--lc-density-row-height").replace("px", "") or 22) - 6
    return int(token("--lc-density-row-height").replace("px", "") or 28)


# Semantic colours per verdict text -- never rely on colour alone: the caller
# must always render the text label as well.
def verdict_color(kind: str) -> str:
    mapping = {
        "覆盖": "--lc-pass",
        "未覆盖": "--lc-fail",
        "缺失": "--lc-neutral",
        "数据异常": "--lc-fail",
        "收紧": "--lc-warn",
        "放宽": "--lc-fail",
        "混合": "--lc-verdict-mixed",
        "一致": "--lc-pass",
        "补值": "--lc-info",
        "过松": "--lc-warn",
        "过紧": "--lc-fail",
        "偏心": "--lc-verdict-offcentre",
        "合理": "--lc-pass",
        "无波动": "--lc-neutral",
        "无限值": "--lc-neutral",
        "数据不足": "--lc-neutral",
        "GU 更紧(合格)": "--lc-pass",
        "GU 与 FT 相同": "--lc-warn",
        "GU 比 FT 宽(失效)": "--lc-fail",
        "无法判定": "--lc-neutral",
        "需更新": "--lc-warn",
        "无需更新": "--lc-pass",
        "程序缺项": "--lc-fail",
        "PE待测未定": "--lc-neutral",
    }
    return hex_color(mapping.get(kind, "--lc-neutral"))
