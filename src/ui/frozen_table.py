"""结果表：冻结左侧若干列（默认 Function / Test item）。

芯片测试明细常有 10+ 列，横向滚动时项名会滚出视野，核对数据只能来回拖。
按 Qt 官方 "Frozen Column" 方案：用一个覆盖在主表视口左侧的子表格显示前 N 列。

**关键约束**：主表仍然持有全部数据与全部列——``item(r, c)``、``rowCount``、
排序、``_current_rows()`` 导出等既有逻辑完全不受影响；覆盖层只是"画"在左边。
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
)


class ResultTable(QTableWidget):
    """带左侧冻结列的 ``QTableWidget``，可直接替换原有用法。"""

    def __init__(self, frozen_cols: int = 2, parent=None):
        super().__init__(0, 0, parent)
        self.frozen_cols = frozen_cols

        self._frozen = QTableWidget(self)
        self._frozen.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._frozen.setSelectionMode(QAbstractItemView.NoSelection)
        self._frozen.setFocusPolicy(Qt.NoFocus)          # 焦点始终留在主表
        self._frozen.verticalHeader().setVisible(False)
        self._frozen.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self._frozen.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._frozen.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._frozen.show()
        self.viewport().stackUnder(self._frozen)         # 覆盖层压在视口之上

        # ---- 同步信号
        self.horizontalHeader().sectionResized.connect(self._sync_geometry)
        self.verticalHeader().sectionResized.connect(self._sync_geometry)
        # 排序会重排行而不触发 dataChanged，用表头排序指示器兜底
        self.horizontalHeader().sortIndicatorChanged.connect(
            lambda *_: self.refresh_frozen())
        # 垂直滚动双向跟随（值相同不会再发信号，无递归风险）
        self.verticalScrollBar().valueChanged.connect(
            self._frozen.verticalScrollBar().setValue)
        self._frozen.verticalScrollBar().valueChanged.connect(
            self.verticalScrollBar().setValue)

        self._sync_geometry()

    # ------------------------------------------------------------------
    def refresh_frozen(self) -> None:
        """把前 N 列复制进覆盖层，并同步行高 / 列宽 / 表头文案。

        在 ``_fill_table`` 填充完成后显式调用一次（避免逐格 dataChanged
        触发 O(n²) 重建）。
        """
        frozen = self._frozen
        cols = min(self.frozen_cols, self.columnCount())
        frozen.setRowCount(self.rowCount())
        frozen.setColumnCount(cols)
        if cols == 0 or self.rowCount() == 0:
            frozen.clear()
            frozen.setRowCount(0)
            frozen.setColumnCount(0)
            self._sync_geometry()
            return

        frozen.setHorizontalHeaderLabels([
            self.horizontalHeaderItem(c).text()
            if self.horizontalHeaderItem(c) else ""
            for c in range(cols)
        ])
        for c in range(cols):
            frozen.setColumnWidth(c, max(1, self.columnWidth(c)))
        for r in range(self.rowCount()):
            frozen.setRowHeight(r, self.rowHeight(r))
            for c in range(cols):
                src = self.item(r, c)
                cell = QTableWidgetItem(src.text() if src else "")
                if src is not None:
                    cell.setForeground(src.foreground())
                    cell.setBackground(src.background())
                    cell.setFont(src.font())
                    # textAlignment() 返回 int，直接传会触发弃用重载（每次刷新
                    # 上万条告警）；包成 Qt.Alignment 走新重载
                    cell.setTextAlignment(Qt.Alignment(src.textAlignment()))
                    cell.setIcon(src.icon())
                frozen.setItem(r, c, cell)
        self._sync_geometry()

    def _sync_geometry(self, *_args) -> None:
        """覆盖层贴合主表左上角：宽度 = 前 N 列列宽之和，高度含表头。"""
        frozen = self._frozen
        cols = min(self.frozen_cols, self.columnCount())
        width = sum(max(1, self.columnWidth(c)) for c in range(cols))
        if width <= 0 or self.columnCount() == 0:
            frozen.hide()
            return
        frozen.show()
        frame = self.frameWidth()
        head_height = self.horizontalHeader().height()
        frozen.setGeometry(
            frame, frame,
            width + frame,
            self.viewport().height() + head_height + frame,
        )
        frozen.horizontalHeader().setFixedHeight(head_height)
