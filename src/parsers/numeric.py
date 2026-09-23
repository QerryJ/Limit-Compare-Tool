"""Numeric parsing helpers.

A blank cell, a dash or any non-numeric placeholder must come back as ``None``
-- never as ``0`` -- because ``0`` is a perfectly legal limit value.
"""

from typing import Optional

LimitValue = Optional[float]

_NULL_TOKENS = {"", "-", "--", "n/a", "na", "null", "none", "nan", "/"}


def parse_number(raw) -> LimitValue:
    """Parse a spreadsheet / ATE cell into a float, or ``None`` when unset."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        value = float(raw)
        return None if value != value else value  # filter NaN
    text = str(raw).strip()
    if text.lower() in _NULL_TOKENS:
        return None
    text = text.replace(",", "")
    try:
        value = float(text)
    except ValueError:
        return None
    return None if value != value else value


def fmt(value: LimitValue, digits: int = 6) -> str:
    """Render a limit value for reports; ``None`` renders as an empty string."""
    if value is None:
        return ""
    rounded = round(value, digits)
    if rounded == int(rounded):
        return str(int(rounded))
    return str(rounded)
