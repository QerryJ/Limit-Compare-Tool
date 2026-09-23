"""Application icon: a rounded accent tile carrying the letter ``C``.

Drawn at runtime with ``QPainter`` so the frozen exe needs **no bundled image
file**, and the colours still come from ``tokens.css`` (single source of truth).
``save_ico`` writes a multi-size ``.ico`` (PNG-compressed entries) so Windows
Explorer and the taskbar show the same icon as the running window.
"""

import struct

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)

from src.ui.theme import hex_color

LETTER = "L"
_SIZES = (16, 24, 32, 48, 64, 128, 256)


def build_icon_pixmap(size: int = 64) -> QPixmap:
    """Render one icon size: rounded accent tile + centred letter ``L``.

    ``L`` 与 ``C`` 一样用**矢量几何**绘制而不是文字——Qt 离屏平台字体库可能为空，
    ``drawText`` 会画出豆腐块；矢量画法在任何环境下形状一致、小尺寸更清晰。
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)

    # ---- 底：圆角方块（强调色）
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(hex_color("--lc-accent")))
    radius = size * 0.24
    painter.drawRoundedRect(0, 0, size, size, radius, radius)

    # ---- 字：L = 一竖 + 一横，用单条路径描边以获得正确的斜接拐角
    stroke = size * 0.15
    x0 = size * 0.32          # 竖笔中心
    y_top = size * 0.26
    y_bottom = size * 0.74    # 横笔所在高度
    x_right = size * 0.68     # 横笔末端
    glyph = QPainterPath()
    glyph.moveTo(x0, y_top)
    glyph.lineTo(x0, y_bottom)
    glyph.lineTo(x_right, y_bottom)
    pen = QPen(QColor(hex_color("--lc-accent-text")), stroke,
               Qt.SolidLine, Qt.FlatCap, Qt.MiterJoin)
    painter.strokePath(glyph, pen)
    painter.end()
    return pixmap


def status_badge_pixmap(color: str, size: int = 10) -> QPixmap:
    """判定列徽章：一个圆角小方块，作为**形状载体**。

    项目规范「语义不得仅靠颜色传达」——判定列同时具备
    **颜色（前景）+ 形状（本徽章）+ 文字（判定值）** 三重编码，
    色觉障碍与黑白打印下仍可区分。徽章设为 DecorationRole，
    不污染单元格文本，因此导出与筛选拿到的仍是干净的判定值。
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color))
    painter.drawRoundedRect(0, 0, size, size, size * 0.3, size * 0.3)
    painter.end()
    return pixmap


def build_app_icon() -> QIcon:
    """Multi-resolution icon (needed for a crisp taskbar / Alt-Tab entry)."""
    icon = QIcon()
    for size in _SIZES:
        icon.addPixmap(build_icon_pixmap(size))
    return icon


def save_ico(path: str, sizes=_SIZES) -> str:
    """Write a multi-size ``.ico`` so the exe itself shows the C icon."""
    entries = []
    for size in sizes:
        blob = QByteArray()
        buffer = QBuffer(blob)
        buffer.open(QIODevice.WriteOnly)
        build_icon_pixmap(size).save(buffer, "PNG")
        buffer.close()
        entries.append((size, bytes(blob.data())))

    count = len(entries)
    header = struct.pack("<HHH", 0, 1, count)          # reserved, type=icon, count
    offset = 6 + 16 * count
    directory = b""
    for size, data in entries:
        # ICONDIRENTRY: 0 表示 256px（单字节放不下）
        dim = 0 if size >= 256 else size
        directory += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32,
                                 len(data), offset)
        offset += len(data)

    with open(path, "wb") as handle:
        handle.write(header + directory + b"".join(data for _, data in entries))
    return path


if __name__ == "__main__":
    import os
    import sys

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "assets", "app.ico")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    print("wrote", save_ico(out), os.path.getsize(out), "bytes")
