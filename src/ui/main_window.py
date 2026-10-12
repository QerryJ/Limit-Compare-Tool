"""Main window for the Limit Compare desktop tool.

M2 scope: a working shell that drives the already-implemented engines --
FV-2 (PE spec vs program), FV-3 (datalog as-run limits vs PE) and
FV-5 / FV-6 (Cpk analysis + GU proposal).

Layer rule: this module only *consumes* engine results. It never re-derives
``N/A`` / ``ERROR`` / direction values -- those come from the engine.
"""

import os
from datetime import datetime

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QIcon,
    QKeySequence,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from src.config.settings import add_recent, load_recent, load_settings, save_settings
from src.engine.align import Aligner
from src.engine.analysis import compute_stat, propose_gu
from src.engine.coverage import evaluate_coverage, evaluate_gu_vs_ft
from src.engine.compare import compare_programs
from src.engine.pe_compare import compare_pe_to_program
from src.export.analysis_report import export_analysis
from src.export.report import (
    export_compare_report,
    export_coverage_report,
    export_gu_vs_ft,
    export_pe_report,
)
from src.model import ChangeDirection, CoverageStatus, SourceType, TempZone, ZONES
from src.parsers.cpts import CptsParser, merge_sides
from src.parsers.datalog import datalog_to_program, parse_datalog
from src.parsers.pds import PdsParser
from src.parsers.pe_excel import parse_files
from src.parsers.numeric import fmt
from src.ui.theme import hex_color, row_height, verdict_color
from src.ui.style import build_stylesheet, is_numeric, mono_family
from src.ui.icon import build_app_icon, status_badge_pixmap
from src.ui.frozen_table import ResultTable
from src.export.audit import enable_header_filters, write_audit_sheet

MODE_PE = "PE ↔ 程序 (FV-2)"
MODE_DATALOG = "datalog ↔ PE (FV-3)"
MODE_ANALYSIS = "Cpk / GU 分析 (FV-5/6)"
MODE_GUFT = "GU ↔ FT 校验 (FV-5)"
MODE_COVERAGE = "FT ↔ QA 覆盖率 (FV-1)"
MODE_CHANGE = "变更前 ↔ 后 (FV-4)"

APP_AUTHOR = "Quincy"
APP_VERSION = "0.4.5"

# 拖拽上传：按扩展名路由到对应输入字段
_PROGRAM_EXT = (".pds", ".cpts")
_PE_EXT = (".xlsx", ".xlsm", ".xls")
_DATALOG_EXT = (".csv",)

# 各模式「仅异常」筛选对应的判定值集合
_ANOMALY = {
    "guft": {"GU 比 FT 宽(失效)"},
    "coverage": {"未覆盖", "局部缺失", "整体缺失", "数据异常"},
    "change": {"放宽", "混合", "收紧", "新增", "移除"},
    "update": {"需更新", "程序缺项", "基线漂移"},
}

_UPDATE_HEADERS = [
    "Function", "Test item", "Unit", "侧别",
    "当前 LSL", "当前 HSL", "PE LSL", "PE HSL",
    "Δ LSL", "Δ HSL", "方向", "状态", "PE 文件",
]
_CPK_HEADERS = ["Test item", "Unit", "n", "Mean", "Sigma", "LSL", "USL", "Cpk", "判定"]
_GU_HEADERS = [
    "Test item", "Unit", "n", "Mean", "Sigma",
    "GU LSL", "GU USL", "FT LSL", "FT USL", "判定",
]
_GUFT_HEADERS = [
    "Function", "Test item", "Unit", "温区",
    "FT LSL", "FT HSL", "GU LSL", "GU HSL", "判定", "说明",
]
_COVERAGE_HEADERS = [
    "Function", "Test item", "Unit", "温区",
    "FT LSL", "FT HSL", "QA LSL", "QA HSL", "低边裕度", "高边裕度", "判定",
]
_CHANGE_HEADERS = [
    "Function", "Test item", "Unit", "温区", "侧别",
    "旧 LSL", "旧 HSL", "新 LSL", "新 HSL", "Δ LSL", "Δ HSL",
    "方向", "变更说明",
]


class _SortItem(QTableWidgetItem):
    """表格项：数值列按**数值大小**排序，文本列按字符串排序。

    默认字符串排序会把 "10" 排在 "9" 前面，对裕度 / Δ / Cpk 这类列是错的。
    """

    def __lt__(self, other) -> bool:  # noqa: D105 - Qt sort hook
        a, b = self.text().strip(), other.text().strip()
        try:
            return float(a) < float(b)
        except ValueError:
            return a < b


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.recent = load_recent()
        self.result = None
        self.result_kind = ""
        self.setWindowTitle("Limit Compare")
        self.setWindowIcon(build_app_icon())   # 字母 C（任务栏 / Alt-Tab 同源）
        self.resize(1280, 800)

        self._build_toolbar()
        self._build_body()
        self._apply_style()
        self._setup_shortcuts()
        self.statusBar().showMessage("就绪")

    # ------------------------------------------------------------- window
    def center_on_screen(self) -> None:
        """启动时把窗口放到主屏幕可用区域正中，方便直接查看。

        headless / 无屏幕环境下安全跳过（tests 与打包运行都依赖这一点）。
        """
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        frame = self.frameGeometry()
        frame.moveCenter(available.center())
        self.move(frame.topLeft())

    # ------------------------------------------------------------------ UI
    def _build_toolbar(self) -> None:
        bar = QToolBar("主工具栏")
        bar.setMovable(False)
        self.addToolBar(bar)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(
            [MODE_PE, MODE_DATALOG, MODE_ANALYSIS, MODE_GUFT, MODE_COVERAGE, MODE_CHANGE]
        )
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        bar.addWidget(QLabel(" 模式 "))
        bar.addWidget(self.mode_combo)

        self.run_btn = QPushButton("执行对比")
        self.run_btn.setObjectName("primary")   # 主行动按钮，样式见 style.py
        self.run_btn.setToolTip("执行当前模式的对比（快捷键 F5）")
        self.run_btn.clicked.connect(self._run)
        bar.addWidget(self.run_btn)

        self.clear_btn = QPushButton("清除文件")
        self.clear_btn.setToolTip(
            "清空已选文件与当前结果（保留模式 / 温区 / σ 倍数），便于开始第二轮对比"
        )
        self.clear_btn.clicked.connect(self._clear_files)
        bar.addWidget(self.clear_btn)

        bar.addSeparator()
        self.xlsx_btn = QPushButton("导出 XLSX")
        self.xlsx_btn.setToolTip("导出 XLSX 报告（快捷键 Ctrl+E）")
        self.xlsx_btn.clicked.connect(self._export_xlsx)
        bar.addWidget(self.xlsx_btn)

        self.html_btn = QPushButton("导出 HTML")
        self.html_btn.setToolTip("导出 HTML 报告（快捷键 Ctrl+Shift+E）")
        self.html_btn.clicked.connect(self._export_html)
        bar.addWidget(self.html_btn)

        bar.addSeparator()
        self.density_btn = QPushButton(
            "密度: 宽" if self.settings.get("density") == "comfortable" else "密度: 紧凑"
        )
        self.density_btn.clicked.connect(self._toggle_density)
        bar.addWidget(self.density_btn)

        bar.addSeparator()
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        bar.addWidget(spacer)
        self.author_label = QLabel(f"作者: {APP_AUTHOR}  ·  v{APP_VERSION}")
        self.author_label.setObjectName("author")
        bar.addWidget(self.author_label)

    def _build_body(self) -> None:
        body = QWidget()
        body.setObjectName("body")
        layout = QHBoxLayout(body)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        # ---- left: data sources ------------------------------------------
        left = QFrame()
        left.setObjectName("panel")
        left.setFrameShape(QFrame.StyledPanel)
        left.setMaximumWidth(420)
        form = QFormLayout(left)
        form.setContentsMargins(14, 14, 14, 14)
        form.setSpacing(9)

        self.program_label = QLabel("程序文件:")
        self.program_edit = QLineEdit()
        self.program_edit.setPlaceholderText("选择 .pds 或 .cpts")
        form.addRow(self.program_label, self._with_browse(self.program_edit, self._browse_program))

        self.pe_edit = QLineEdit()
        self.pe_edit.setPlaceholderText("选择 PE 规格 Excel（可多选）")
        form.addRow("PE 表格:", self._with_browse(self.pe_edit, self._browse_pe, multi=True))

        self.datalog_edit = QLineEdit()
        self.datalog_edit.setPlaceholderText("选择 ETS88 datalog .csv")
        form.addRow("datalog:", self._with_browse(self.datalog_edit, self._browse_datalog))

        self.gu_label = QLabel("GU 程序:")
        self.gu_program_edit = QLineEdit()
        self.gu_program_edit.setPlaceholderText("选择 GU 程序 (.pds/.cpts)")
        form.addRow(self.gu_label, self._with_browse(self.gu_program_edit, self._browse_program))

        # 最近文件：recent.json 一直在记，这里把它露出来，重复核对同一料号省 3 步
        self.recent_combo = QComboBox()
        self.recent_combo.setToolTip("最近用过的文件，按扩展名自动落到对应输入框")
        self.recent_combo.activated.connect(self._on_recent_selected)
        form.addRow("最近文件:", self.recent_combo)

        self.gu_k_label = QLabel("GU σ 倍数:")
        self.gu_k_spin = QDoubleSpinBox()
        self.gu_k_spin.setRange(1.0, 6.0)
        self.gu_k_spin.setSingleStep(0.5)
        self.gu_k_spin.setDecimals(1)
        self.gu_k_spin.setValue(float(self.settings.get("gu_sigma_k", 3.0)))
        self.gu_k_spin.setToolTip(
            "GU 建议 limit = mean ± k·σ，默认 3.0（对齐 30Pcs 3sigma 惯例）"
        )
        self.gu_k_spin.valueChanged.connect(self._on_gu_k_changed)
        form.addRow(self.gu_k_label, self.gu_k_spin)

        self.zone_combo = QComboBox()
        self.zone_combo.addItems([z.value for z in TempZone])
        self.zone_combo.setCurrentText(self.settings.get("zone", "Room"))
        form.addRow("温区:", self.zone_combo)

        self.stage_label = QLabel("—")
        form.addRow("识别阶段:", self.stage_label)

        self.summary_label = QLabel("尚未执行")
        self.summary_label.setObjectName("summary")
        self.summary_label.setWordWrap(True)
        form.addRow(self.summary_label)

        self.drop_hint = QLabel(
            "提示：可直接把文件拖进窗口 —— "
            ".pds/.cpts → 程序，.xlsx → PE 表格，.csv → datalog"
        )
        self.drop_hint.setObjectName("hint")
        self.drop_hint.setWordWrap(True)
        form.addRow(self.drop_hint)

        # 当前文件面板：输入框窄、路径长，肉眼常看不全；这里按「角色：文件名」
        # 列出已选文件，完整路径放 tooltip，选择/拖入/清除/切模式都会自动刷新
        self.files_caption = QLabel("当前文件")
        self.files_caption.setObjectName("caption")
        form.addRow(self.files_caption)

        self.file_list = QListWidget()
        self.file_list.setObjectName("fileList")
        self.file_list.setToolTip("已选文件；悬停可查看完整路径")
        self.file_list.setMaximumHeight(110)
        form.addRow(self.file_list)

        layout.addWidget(left)

        # ---- right: result table -----------------------------------------
        right = QWidget()
        right_layout = QVBoxLayout(right)

        self.view_combo = QComboBox()
        self.view_combo.addItems(["Cpk 分析", "GU 建议"])
        self.view_combo.currentTextChanged.connect(self._refresh_table)
        self.view_combo.setVisible(False)
        right_layout.addWidget(self.view_combo)

        # 搜索框（Function / Test item）+ 判定筛选下拉，两者叠加生效
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索测试项 / Function…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMaximumWidth(240)
        self.search_edit.textChanged.connect(self._apply_filter)

        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["全部", "仅异常"])
        self.filter_combo.setCurrentText("全部")
        self.filter_combo.currentTextChanged.connect(self._apply_filter)
        filter_row = QHBoxLayout()
        filter_row.addWidget(self.search_edit)
        filter_row.addStretch(1)
        filter_row.addWidget(QLabel("筛选:"))
        filter_row.addWidget(self.filter_combo)
        right_layout.addLayout(filter_row)

        # 冻结左侧两列（Function / Test item）：横向滚动时项名始终可见
        self.table = ResultTable(frozen_cols=2)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setIconSize(QSize(10, 10))    # 判定徽章
        right_layout.addWidget(self.table)

        self.legend = QLabel()
        self.legend.setObjectName("caption")
        self.legend.setWordWrap(True)
        right_layout.addWidget(self.legend)

        layout.addWidget(right, 1)
        self.setCentralWidget(body)
        self._apply_density()

        # 文件输入框不自行接收拖放，让拖放事件冒泡到主窗口统一按扩展名路由；
        # 同时把它们挂到「当前文件」面板，选择 / 拖入 / 清除都会自动刷新
        for edit in (self.program_edit, self.pe_edit, self.datalog_edit,
                     self.gu_program_edit):
            edit.setAcceptDrops(False)
            edit.textChanged.connect(self._refresh_file_list)
        self.setAcceptDrops(True)

        self._on_mode_changed(self.mode_combo.currentText())

    def _with_browse(self, edit: QLineEdit, slot, multi: bool = False) -> QWidget:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(edit, 1)
        btn = QPushButton("浏览")
        btn.clicked.connect(lambda: slot(edit, multi))
        row.addWidget(btn)
        return box

    # ------------------------------------------------------------- browsing
    def _browse_program(self, edit: QLineEdit, multi: bool = False) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择测试程序", "", "程序文件 (*.pds *.cpts);;所有文件 (*.*)"
        )
        if path:
            add_recent("program", path)   # 先落盘，textChanged 刷新最近文件时即可见
            edit.setText(path)

    def _browse_pe(self, edit: QLineEdit, multi: bool = False) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择 PE 规格表", "", "Excel (*.xlsx);;所有文件 (*.*)"
        )
        if paths:
            for p in paths:
                add_recent("pe", p)
            edit.setText(";".join(paths))

    def _browse_datalog(self, edit: QLineEdit, multi: bool = False) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 datalog", "", "CSV (*.csv);;所有文件 (*.*)"
        )
        if path:
            add_recent("datalog", path)   # 先落盘，textChanged 刷新最近文件时即可见
            edit.setText(path)

    # ----------------------------------------------------------------- mode
    def _on_mode_changed(self, mode: str) -> None:
        is_analysis = mode == MODE_ANALYSIS
        is_guft = mode == MODE_GUFT
        is_coverage = mode == MODE_COVERAGE
        is_change = mode == MODE_CHANGE
        self.view_combo.setVisible(is_analysis)
        # σ 倍数只影响 GU 建议（仅分析模式），其余模式隐藏避免误导
        self.gu_k_spin.setVisible(is_analysis)
        self.gu_k_label.setVisible(is_analysis)
        self.program_edit.setEnabled(
            mode in (MODE_PE, MODE_GUFT, MODE_COVERAGE, MODE_CHANGE)
        )
        self.gu_program_edit.setEnabled(mode in (MODE_GUFT, MODE_COVERAGE, MODE_CHANGE))
        self.pe_edit.setEnabled(mode in (MODE_PE, MODE_DATALOG))
        self.datalog_edit.setEnabled(mode in (MODE_DATALOG, MODE_ANALYSIS))
        # Relabel the shared primary/secondary program fields per mode.
        if is_coverage:
            self.program_label.setText("FT 程序:")
            self.gu_label.setText("QA 程序:")
        elif is_guft:
            self.program_label.setText("FT 程序:")
            self.gu_label.setText("GU 程序:")
        elif is_change:
            self.program_label.setText("基准程序:")
            self.gu_label.setText("新程序:")
        else:
            self.program_label.setText("程序文件:")
            self.gu_label.setText("GU 程序:")
        self.summary_label.setText("尚未执行")
        self.stage_label.setText("—")
        self.filter_combo.blockSignals(True)
        self.filter_combo.clear()
        self.filter_combo.addItems(["全部", "仅异常"])
        self.filter_combo.setCurrentText("全部")
        self.filter_combo.blockSignals(False)
        self.search_edit.blockSignals(True)
        self.search_edit.clear()
        self.search_edit.blockSignals(False)
        self._rows = []
        self.table.setRowCount(0)
        self._refresh_file_list()

    def _toggle_density(self) -> None:
        current = self.settings.get("density", "comfortable")
        new = "compact" if current == "comfortable" else "comfortable"
        self.settings["density"] = new
        save_settings(self.settings)
        self.density_btn.setText("密度: 宽" if new == "comfortable" else "密度: 紧凑")
        self._apply_density()
        self._apply_style()

    def _apply_style(self) -> None:
        """整体样式由设计令牌生成，见 src/ui/style.py。"""
        self.setStyleSheet(
            build_stylesheet(self.settings.get("density", "comfortable"))
        )

    def _apply_density(self) -> None:
        dense = self.settings.get("density", "comfortable")
        self.table.verticalHeader().setDefaultSectionSize(row_height(dense))
        font = QFont()
        font.setPointSize(9 if dense == "compact" else 10)
        self.table.setFont(font)
        # 数值列等宽（令牌 --lc-numeric-font），便于工程师逐列比对位数
        mono = QFont(mono_family(), font.pointSize())
        self._num_font = mono

    # ------------------------------------------------------------------ run
    def _run(self) -> None:
        mode = self.mode_combo.currentText()
        self._set_busy(True, "解析与对比中，请稍候…")
        try:
            if mode == MODE_PE:
                self._run_pe()
            elif mode == MODE_DATALOG:
                self._run_datalog()
            elif mode == MODE_GUFT:
                self._run_gu_vs_ft()
            elif mode == MODE_COVERAGE:
                self._run_coverage()
            elif mode == MODE_CHANGE:
                self._run_change()
            else:
                self._run_analysis()
        except Exception as exc:  # noqa: BLE001 - surfaced to the user
            self._set_busy(False, "执行失败")
            QMessageBox.critical(self, "执行失败", f"{type(exc).__name__}: {exc}")
            self.statusBar().showMessage("执行失败")
            return
        self._set_busy(False)
        self._refresh_table()

    def _zone(self) -> TempZone:
        return TempZone(self.zone_combo.currentText())

    def _load_program(self, path: str):
        if path.lower().endswith(".pds"):
            return PdsParser.parse_file(path)
        return CptsParser.parse_file(path)

    def _run_pe(self) -> None:
        program_path = self.program_edit.text().strip()
        pe_paths = [p for p in self.pe_edit.text().split(";") if p.strip()]
        if not program_path or not pe_paths:
            raise ValueError("请同时选择程序文件与 PE 表格")
        program = self._load_program(program_path)
        pe = parse_files(pe_paths, program_id=program.id)
        mapping_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "..", "config", f"mapping_{program.id}.json")
        aligner = Aligner(program, Aligner.load_mapping(mapping_path))
        matches = aligner.match_all(pe.items)
        self.result = compare_pe_to_program(pe, program, matches, self._zone())
        Aligner.save_mapping(mapping_path, aligner.mapping)
        self.result_kind = "update"
        self.pe_program = pe
        self.program_name = program_path
        self.stage_label.setText("—")
        self.summary_label.setText(
            "\n".join(f"{k}: {v}" for k, v in self.result.summary.items())
        )
        self.statusBar().showMessage(
            f"完成：需更新 {self.result.summary.get('需更新', 0)} 项"
        )

    def _run_datalog(self) -> None:
        datalog_path = self.datalog_edit.text().strip()
        pe_paths = [p for p in self.pe_edit.text().split(";") if p.strip()]
        if not datalog_path or not pe_paths:
            raise ValueError("请同时选择 datalog 与 PE 表格")
        data = parse_datalog(datalog_path)
        program = datalog_to_program(data)
        pe = parse_files(pe_paths, program_id=program.id)
        aligner = Aligner(program)
        matches = aligner.match_all(pe.items)
        self.result = compare_pe_to_program(
            pe, program, matches, zone=data.zone, sides=[data.side]
        )
        self.result_kind = "update"
        self.pe_program = pe
        self.program_name = datalog_path
        self.datalog = data
        self.stage_label.setText(
            f"{data.stage_label()}（{'自动识别' if data.tag_detected else '未识别'}）"
        )
        self.summary_label.setText(
            f"阶段: {data.stage_label()}\n"
            + "\n".join(f"{k}: {v}" for k, v in self.result.summary.items())
        )
        self.statusBar().showMessage(
            f"完成：{data.stage_label()}，不符 {self.result.summary.get('需更新', 0)} 项"
        )

    def _run_analysis(self) -> None:
        datalog_path = self.datalog_edit.text().strip()
        if not datalog_path:
            raise ValueError("请选择 datalog")
        data = parse_datalog(datalog_path)
        limits = {item.name: item for item in data.items}
        k = float(self.gu_k_spin.value())
        stats, gu = [], []
        for name, values in data.measurements.items():
            if len(values) < 2:
                continue
            limit = limits.get(name)
            lo = limit.lo if limit else None
            hi = limit.hi if limit else None
            unit = limit.unit if limit else ""
            if lo == 0 and hi == 0:  # 0/0 means undecided, not a real limit
                lo = hi = None
            stats.append(compute_stat(
                name, unit, values, lo, hi,
                loose=float(self.settings.get("cpk_loose", 2.0)),
                tight=float(self.settings.get("cpk_tight", 1.33)),
                skew=float(self.settings.get("cpk_skew", 0.30)),
            ))
            gu.append(propose_gu(name, unit, values, lo, hi, k=k))
        self.stats, self.gu, self.datalog = stats, gu, data
        self.result_kind = "analysis"
        self.stage_label.setText(data.stage_label())
        self.summary_label.setText(
            f"阶段: {data.stage_label()}　样本: {len(data.bins)} 颗\n"
            f"Cpk: 过紧 {sum(1 for s in stats if s.verdict.value == '过紧')} · "
            f"过松 {sum(1 for s in stats if s.verdict.value == '过松')} · "
            f"偏心 {sum(1 for s in stats if s.verdict.value == '偏心')}\n"
            f"GU: 失效 {sum(1 for g in gu if g.verdict.value.startswith('GU 比'))}"
        )
        self.statusBar().showMessage("完成：Cpk 与 GU 分析")

    def _run_gu_vs_ft(self) -> None:
        ft_path = self.program_edit.text().strip()
        gu_path = self.gu_program_edit.text().strip()
        if not ft_path or not gu_path:
            raise ValueError(
                self._missing_files_hint(ft_path and "" or "FT 程序",
                                         gu_path and "" or "GU 程序")
            )
        ft = self._load_program(ft_path)
        gu = self._load_program(gu_path)
        merged = merge_sides(ft, gu, f"{ft.id or 'FT'} + {gu.id or 'GU'}")
        zone = self._zone()
        self.guft_report = evaluate_gu_vs_ft(merged, [zone])
        self.result = self.guft_report
        self.result_kind = "guft"
        self.ft_name = ft_path
        self.gu_name = gu_path
        self.stage_label.setText(f"{zone.value}")
        outside = self.guft_report.summary.get("GU 比 FT 宽(失效)", 0)
        missing = self.guft_report.summary.get("无法判定", 0)
        self.summary_label.setText(
            f"温区: {zone.value}\n"
            f"GU 失效(比 FT 宽): {outside} 项\n"
            f"无法判定(缺侧): {missing} 项"
        )
        self.statusBar().showMessage(f"完成：GU 比 FT 宽(失效) {outside} 项")

    def _run_coverage(self) -> None:
        ft_path = self.program_edit.text().strip()
        if not ft_path:
            raise ValueError("请选择 FT 程序（.pds 或 .cpts）")
        ft = self._load_program(ft_path)
        # A .pds carries both FT and QA sides in one file; a .cpts is single-side
        # (determined by the _FT_ / _QA_ filename token), so QA must be supplied
        # separately and the two sides merged.
        has_qa = any(
            it.get_bound(z, SourceType.QA) is not None
            for it in ft.items for z in ZONES
        )
        if has_qa:
            program = ft
            qa_name = ""
        else:
            qa_path = self.gu_program_edit.text().strip()
            if not qa_path:
                raise ValueError(
                    "检测到单侧程序文件（只有 FT，没有 QA）。\n"
                    "请在右侧「QA 程序」处选择同一料号的 QA 文件，"
                    "或把 FT / QA 两个文件一起拖进窗口后重试。"
                )
            qa = self._load_program(qa_path)
            program = merge_sides(ft, qa, f"{ft.id or 'FT'} + {qa.id or 'QA'}")
            qa_name = qa_path
        zone = self._zone()
        self.coverage_report = evaluate_coverage(program, [zone])
        self.result = self.coverage_report
        self.result_kind = "coverage"
        self.ft_name = ft_path
        self.qa_name = qa_name
        self.stage_label.setText(f"{zone.value}")
        s = self.coverage_report.summary
        rate = s.get("覆盖率")
        self.summary_label.setText(
            f"温区: {zone.value}\n"
            f"覆盖率(可比温区): {rate if rate is not None else 'N/A'}%\n"
            f"未覆盖: {s.get('未覆盖', 0)} · 整体缺失: {s.get('整体缺失', 0)} · "
            f"局部缺失: {s.get('局部缺失', 0)} · 数据异常: {s.get('数据异常', 0)}"
        )
        self.statusBar().showMessage(
            f"完成：覆盖率 {rate if rate is not None else 'N/A'}%，"
            f"未覆盖 {s.get('未覆盖', 0)} 项"
        )

    def _run_change(self) -> None:
        base_path = self.program_edit.text().strip()
        new_path = self.gu_program_edit.text().strip()
        if not base_path or not new_path:
            raise ValueError(
                self._missing_files_hint(base_path and "" or "基准程序",
                                         new_path and "" or "新程序")
            )
        base = self._load_program(base_path)
        new = self._load_program(new_path)
        zone = self._zone()
        self.compare_report = compare_programs(base, new, [zone])
        self.result = self.compare_report
        self.result_kind = "change"
        self.base_name = base_path
        self.new_name = new_path
        self.stage_label.setText(f"{zone.value}")
        s = self.compare_report.summary
        self.summary_label.setText(
            f"温区: {zone.value}\n"
            f"放宽风险: {s.get('放宽风险', 0)} 项（放宽 {s.get('放宽', 0)} · "
            f"混合 {s.get('混合', 0)}）\n"
            f"收紧: {s.get('收紧', 0)} · 新增: {s.get('新增', 0)} · "
            f"移除: {s.get('移除', 0)} · 相同: {s.get('相同', 0)}"
        )
        self.statusBar().showMessage(f"完成：放宽风险 {s.get('放宽风险', 0)} 项")

    # ---------------------------------------------------------------- table
    def _refresh_table(self) -> None:
        kind = self.result_kind
        rows: list = []
        verdict_col = -1
        headers: list = []
        legend_text = ""
        if kind == "guft" and self.result is not None:
            rows = [
                [r.item.function, r.item.test_item, r.item.unit, z.zone.value,
                 fmt(z.ft.lo) if z.ft else "", fmt(z.ft.hi) if z.ft else "",
                 fmt(z.gu.lo) if z.gu else "", fmt(z.gu.hi) if z.gu else "",
                 z.status.value, z.detail]
                for r in self.result.items for z in r.zones
            ]
            headers = _GUFT_HEADERS
            verdict_col = 8
            legend_text = "GU 必须严格落在 FT 之内；● GU 比 FT 宽(失效) 表示 GU 无法验证 setup 正常"
        elif kind == "coverage" and self.result is not None:
            rows = []
            for entry in self.result.items:
                for z in entry.zones:
                    rows.append([
                        entry.item.function, entry.item.test_item, entry.item.unit,
                        z.zone.value,
                        fmt(z.ft.lo) if z.ft else "", fmt(z.ft.hi) if z.ft else "",
                        fmt(z.qa.lo) if z.qa else "", fmt(z.qa.hi) if z.qa else "",
                        fmt(z.gb_lo) if z.gb_lo is not None else "",
                        fmt(z.gb_hi) if z.gb_hi is not None else "",
                        z.status.value,
                    ])
            headers = _COVERAGE_HEADERS
            verdict_col = 10
            legend_text = ("QA 须完整包含 FT（正裕度=有余量）。● 未覆盖=QA 未包住 FT，需收紧 QA/放宽 FT　"
                           "● 整体缺失=该测试项双侧皆无　● 局部缺失=仅部分温区有数据")
        elif kind == "change" and self.result is not None:
            # 逐 CellDiff 展开，保留旧/新 LSL/HSL 及 Δ，让用户直观看到原始数据差异
            rows = []
            for d in self.result.items:
                cells = d.zones if d.zones else [None]
                for c in cells:
                    rows.append([
                        d.function, d.test_item, d.unit,
                        c.zone.value if c else "",
                        c.side.value if c else "",
                        fmt(c.a_lo) if c and c.a_lo is not None else "",
                        fmt(c.a_hi) if c and c.a_hi is not None else "",
                        fmt(c.b_lo) if c and c.b_lo is not None else "",
                        fmt(c.b_hi) if c and c.b_hi is not None else "",
                        fmt(c.delta_lo) if c and c.delta_lo is not None else "",
                        fmt(c.delta_hi) if c and c.delta_hi is not None else "",
                        d.direction.value, d.change_detail,
                    ])
            headers = _CHANGE_HEADERS
            verdict_col = 11
            legend_text = ("变更方向（颜色之外必有文字）：旧/新 LSL·HSL 为逐温区逐侧原始 limit，"
                           "Δ 为新−旧差值　● 放宽=限制变宽（漏放风险，优先复核）　"
                           "● 混合=一边收一边放（含放宽风险）　● 收紧=更严　● 新增/移除=项变动")
        elif kind == "update" and self.result is not None:
            rows = [
                [r.function, r.test_item, r.unit, r.side,
                 fmt(r.cur_lo), fmt(r.cur_hi), fmt(r.tgt_lo), fmt(r.tgt_hi),
                 fmt(r.d_lo), fmt(r.d_hi), r.direction.value, r.status.value,
                 r.pe_file]
                for r in self.result.updates
            ]
            headers = _UPDATE_HEADERS
            verdict_col = 11
            legend_text = ("语义（颜色之外必有文字）：● 收紧 = 程序现比 PE 松（漏放，必须改）　"
                           "● 放宽 = 程序现比 PE 紧（过杀）　● 程序缺项　● PE待测未定")
        elif kind == "analysis" and self.result is not None:
            if self.view_combo.currentText() == "GU 建议":
                rows = [
                    [g.name, g.unit, str(g.n), fmt(g.mean), fmt(g.sigma),
                     fmt(g.gu_lo), fmt(g.gu_hi), fmt(g.ft_lo), fmt(g.ft_hi),
                     g.verdict.value]
                    for g in self.gu
                ]
                headers = _GU_HEADERS
                verdict_col = 9
                legend_text = "GU 必须严格落在 FT 之内；● GU 比 FT 宽(失效) 表示无法验证 setup 正常"
            else:
                rows = [
                    [s.name, s.unit, str(s.n), fmt(s.mean), fmt(s.sigma),
                     fmt(s.lo), fmt(s.hi), fmt(s.cpk, 3), s.verdict.value]
                    for s in self.stats
                ]
                rows.sort(key=lambda r: (r[8] not in ("过紧", "过松", "偏心"), r[8]))
                headers = _CPK_HEADERS
                verdict_col = 8
                legend_text = "● 过紧 Cpk<1.33（yield 风险）　● 过松 Cpk≥2.0（白放宽度）　● 偏心"
        else:
            self.table.setRowCount(0)
            return

        # 全量原始数据保留在 self._rows；表头筛选仅做视图收窄，不丢弃数据
        self._rows = rows
        self._headers = headers
        self._verdict_col = verdict_col
        if kind == "analysis" and self.view_combo.currentText() == "GU 建议":
            self._anomaly_set = {"GU 比 FT 宽(失效)"}
        elif kind == "analysis":
            self._anomaly_set = {"过紧", "过松", "偏心"}
        else:
            self._anomaly_set = _ANOMALY.get(kind, set())
        self.legend.setText(legend_text)
        self._populate_filter()
        self._apply_filter()

    def _populate_filter(self) -> None:
        distinct = sorted({
            r[self._verdict_col] for r in self._rows if 0 <= self._verdict_col < len(r)
        })
        self.filter_combo.blockSignals(True)
        self.filter_combo.clear()
        self.filter_combo.addItems(["全部", "仅异常"] + distinct)
        self.filter_combo.setCurrentText("全部")
        self.filter_combo.blockSignals(False)

    def _apply_filter(self) -> None:
        if not getattr(self, "_rows", None):
            self.table.setRowCount(0)
            return
        sel = self.filter_combo.currentText()
        if sel == "全部":
            rows = self._rows
        elif sel == "仅异常":
            rows = [
                r for r in self._rows
                if 0 <= self._verdict_col < len(r)
                and r[self._verdict_col] in self._anomaly_set
            ]
        else:
            rows = [
                r for r in self._rows
                if 0 <= self._verdict_col < len(r)
                and r[self._verdict_col] == sel
            ]
        query = self.search_edit.text().strip().lower() if hasattr(
            self, "search_edit") else ""
        if query:
            # 只在名称列（Function / Test item）里搜，避免误命中数值列
            rows = [
                r for r in rows
                if query in " ".join(str(r[i]) for i in (0, 1) if i < len(r)).lower()
            ]
        self._fill_table(self._headers, rows, self._verdict_col)
        parts = [f"筛选：{sel}"]
        if query:
            parts.append(f"搜索：{query}")
        self.statusBar().showMessage(f"{len(rows)} 行（" + " · ".join(parts) + "）")

    def _fill_table(self, headers, rows, verdict_col: int) -> None:
        # 填充期间必须关闭排序，否则 setItem 会边填边重排
        self.table.setSortingEnabled(False)
        self.table.clear()
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(rows))
        num_font = getattr(self, "_num_font", None)
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                text = str(value)
                item = _SortItem(text)
                if c == verdict_col:
                    item.setForeground(QColor(verdict_color(text)))
                elif num_font is not None and is_numeric(text):
                    item.setFont(num_font)
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(r, c, item)
        self.table.setSortingEnabled(True)
        # 判定列：颜色 + 形状徽章 + 文字 三重编码（图标走 DecorationRole，不污染文本）
        if verdict_col >= 0:
            for r in range(len(rows)):
                cell = self.table.item(r, verdict_col)
                if cell is not None:
                    cell.setIcon(QIcon(status_badge_pixmap(verdict_color(cell.text()))))
        self.table.refresh_frozen()
        self.statusBar().showMessage(f"{len(rows)} 行")

    @staticmethod
    def _missing_files_hint(*missing: str) -> str:
        names = [m for m in missing if m]
        return (
            f"缺少 {' 与 '.join(names)}。\n"
            "请把两个程序文件都选上，或直接把它们一起拖进窗口后重试。"
        )

    # --------------------------------------------------------------- export
    def _default_export_dir(self) -> str:
        """导出弹窗默认落在「数据上传位置」：按当前模式的主输入文件目录打开，
        无输入时回退到上次导出目录，再由用户自行选择。"""
        mode = self.mode_combo.currentText()
        if mode in (MODE_DATALOG, MODE_ANALYSIS):
            order = (self.datalog_edit, self.program_edit, self.pe_edit)
        elif mode == MODE_PE:
            order = (self.program_edit, self.pe_edit, self.datalog_edit)
        else:
            order = (self.program_edit, self.gu_program_edit, self.datalog_edit)
        for edit in order:
            first = (edit.text() or "").split(";")[0].strip()
            if first:
                return os.path.dirname(os.path.abspath(first))
        return self.settings.get("export_dir", "")

    def _audit_info(self, exported_rows: int, scope: str) -> list:
        """导出稽核信息：**导出时间 / 筛选信息 / 源文件全路径**。

        对比总结由调用方单独传入（`write_audit_sheet` 的 summary、
        HTML 的“对比总结”小节）。

        2026-09-24 按用户要求精简：**不再写入工具版本与作者**——
        报告是要交付给客户/质量部的，不带工具与作者信息。
        """
        info = [("导出时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))]
        # ---- 筛选信息（决定“这份报告看到的是不是全量”）
        info.append(("结果筛选", self.filter_combo.currentText() or "全部"))
        query = self.search_edit.text().strip()
        if query:
            info.append(("搜索条件", query))
        info.append(("导出口径", scope))
        info.append(("导出行数", str(exported_rows)))
        info.append(("结果总行数", str(len(getattr(self, "_rows", None) or []))))
        # ---- 对比源文件全路径（能据以复现这次对比）
        for label, edit in (("程序 / 基准", self.program_edit),
                            ("第二程序", self.gu_program_edit),
                            ("PE 表格", self.pe_edit),
                            ("datalog", self.datalog_edit)):
            for part in (edit.text() or "").split(";"):
                if part.strip():
                    info.append((label, part.strip()))
        return info

    def _resolve_export_scope(self):
        """确定导出行范围，避免筛选后静默导出子集。返回 (rows, scope)。

        用户取消时返回 ``(None, "")``。
        """
        total = len(getattr(self, "_rows", None) or [])
        view = self._current_rows()
        sel = self.filter_combo.currentText() or "全部"
        query = self.search_edit.text().strip()
        narrowed = (sel != "全部") or bool(query)
        if not narrowed or len(view) >= total:
            return view, ("全部（未筛选）" if not narrowed else f"当前视图（{sel}）")

        box = QMessageBox(self)
        box.setWindowTitle("导出口径")
        cond = f"筛选「{sel}」" + (f" + 搜索「{query}」" if query else "")
        box.setText(
            f"当前视图经过 {cond}，只有 {len(view)} 行；全量共 {total} 行。\n\n"
            "请选择导出范围："
        )
        full_btn = box.addButton(f"导出全量（{total} 行）", QMessageBox.YesRole)
        view_btn = box.addButton(f"仅导出当前视图（{len(view)} 行）", QMessageBox.NoRole)
        box.addButton("取消", QMessageBox.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is full_btn:
            return list(self._rows), "全量"
        if clicked is view_btn:
            return view, f"当前视图（{cond}）"
        return None, ""

    def _remember_export_dir(self, path: str) -> None:
        self.settings["export_dir"] = os.path.dirname(os.path.abspath(path))
        save_settings(self.settings)

    def _export_xlsx(self) -> None:
        if self.result is None and self.result_kind != "analysis":
            QMessageBox.information(self, "提示", "请先执行对比")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 XLSX", os.path.join(self._default_export_dir(), "report.xlsx"),
            "Excel (*.xlsx)"
        )
        if not path:
            return
        if self.result_kind == "guft":
            export_gu_vs_ft(
                path, self.guft_report,
                ft_name=os.path.basename(self.ft_name),
                gu_name=os.path.basename(self.gu_name),
            )
        elif self.result_kind == "coverage":
            export_coverage_report(
                path, self.coverage_report,
                ft_name=os.path.basename(self.ft_name),
                qa_name=os.path.basename(self.qa_name) if self.qa_name else "",
            )
        elif self.result_kind == "change":
            export_compare_report(
                path, self.compare_report,
                base_name=os.path.basename(self.base_name),
                new_name=os.path.basename(self.new_name),
            )
        elif self.result_kind == "analysis":
            from src.engine.analysis import summarise, summarise_gu
            meta = [("来源 datalog", getattr(self, "datalog", None).source_file
                     if getattr(self, "datalog", None) else "")]
            export_analysis(path, self.stats, self.gu, meta,
                            summarise(self.stats), summarise_gu(self.gu))
        else:
            export_pe_report(
                path, self.result, [],
                program_name=os.path.basename(self.program_name),
                pe_files=getattr(self.pe_program, "source_files", []),
            )
        self._remember_export_dir(path)
        full = len(getattr(self, "_rows", None) or [])
        write_audit_sheet(
            path,
            self._audit_info(full, "全量（引擎完整结果，不受界面筛选影响）"),
            summary=self.summary_label.text(),
        )
        enable_header_filters(path)   # 数据表开启表头筛选 + 冻结首行
        self.statusBar().showMessage(
            f"已导出 {path}（含稽核信息，全量 {full} 行，数据表已开启表头筛选）"
        )

    def _export_html(self) -> None:
        if self.result is None and self.result_kind != "analysis":
            QMessageBox.information(self, "提示", "请先执行对比")
            return
        # 先确定导出口径：筛选后必须让用户确认，不能静默导出子集
        rows, scope = self._resolve_export_scope()
        if rows is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 HTML", os.path.join(self._default_export_dir(), "report.html"),
            "HTML (*.html)"
        )
        if not path:
            return
        from src.export.html_report import export_html_report
        audit = self._audit_info(len(rows), scope)
        if self.result_kind == "guft":
            export_html_report(
                path, "GU ↔ FT 校验", _GUFT_HEADERS, rows,
                summary=self.summary_label.text(), audit=audit,
            )
        elif self.result_kind == "coverage":
            export_html_report(
                path, "FT ↔ QA 覆盖率 (FV-1)", _COVERAGE_HEADERS,
                rows, summary=self.summary_label.text(), audit=audit,
            )
        elif self.result_kind == "change":
            export_html_report(
                path, "变更前 ↔ 后 (FV-4)", _CHANGE_HEADERS,
                rows, summary=self.summary_label.text(), audit=audit,
            )
        elif self.result_kind == "analysis":
            export_html_report(
                path, "Cpk 与 GU 分析",
                _GU_HEADERS if self.view_combo.currentText() == "GU 建议" else _CPK_HEADERS,
                rows, summary=self.summary_label.text(), audit=audit,
            )
        else:
            export_html_report(
                path, "Limit 对比结果", _UPDATE_HEADERS, rows,
                summary=self.summary_label.text(), audit=audit,
            )
        self._remember_export_dir(path)
        self.statusBar().showMessage(
            f"已导出 {path}（{scope}，{len(rows)} 行，含稽核信息）"
        )

    def _current_rows(self):
        rows = []
        for r in range(self.table.rowCount()):
            rows.append([
                self.table.item(r, c).text() if self.table.item(r, c) else ""
                for c in range(self.table.columnCount())
            ])
        return rows

    # --------------------------------------------------------- drag & drop
    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.mimeData().hasUrls():
            self._show_drop_hint([u.toLocalFile() for u in event.mimeData().urls()])
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._clear_drop_hint()
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt override
        if not event.mimeData().hasUrls():
            event.ignore()
            return
        paths = [u.toLocalFile() for u in event.mimeData().urls()]
        self._clear_drop_hint()
        placed, rejected = self._accept_dropped_paths(paths)
        event.acceptProposedAction()
        if placed:
            self.statusBar().showMessage("已拖入：" + "、".join(placed))
        if rejected:
            QMessageBox.information(
                self, "未识别的文件",
                "以下文件未识别（仅支持 .pds/.cpts 程序、.xlsx/.xlsm/.xls 表格、"
                ".csv datalog）：\n" + "\n".join(rejected),
            )

    def _role_label(self, edit) -> str:
        """输入框在当前模式下的角色名（随模式变化，如 QA 程序 / 新程序）。"""
        if edit is self.program_edit:
            return self.program_label.text().rstrip("：:").strip()
        if edit is self.gu_program_edit:
            return self.gu_label.text().rstrip("：:").strip()
        if edit is self.pe_edit:
            return "PE 表格"
        return "datalog"

    def _drop_targets(self, paths) -> set:
        """预览每个拖入文件会落到哪个输入框（**只读**，不改内容）。

        落点规则必须与 ``_accept_dropped_paths`` 完全一致，否则高亮会骗人。
        """
        targets = set()
        two = self.mode_combo.currentText() in (MODE_GUFT, MODE_COVERAGE, MODE_CHANGE)
        filled_main = bool(self.program_edit.text().strip())
        filled_second = bool(self.gu_program_edit.text().strip())
        for raw in paths:
            path = (raw or "").strip()
            if not path:
                continue
            ext = os.path.splitext(path)[1].lower()
            if ext in _PROGRAM_EXT:
                if not filled_main:
                    targets.add(self.program_edit)
                    filled_main = True
                elif two and not filled_second:
                    targets.add(self.gu_program_edit)
                    filled_second = True
                else:
                    targets.add(self.program_edit)
            elif ext in _PE_EXT:
                targets.add(self.pe_edit)
            elif ext in _DATALOG_EXT:
                targets.add(self.datalog_edit)
        return targets

    def _set_drop_hint(self, targets) -> None:
        """给目标输入框加高亮（QSS 属性选择器），改属性后必须重新 polish。"""
        for edit in (self.program_edit, self.pe_edit, self.datalog_edit,
                     self.gu_program_edit):
            edit.setProperty("dropTarget", edit in targets)
            edit.style().unpolish(edit)
            edit.style().polish(edit)

    def _show_drop_hint(self, paths) -> None:
        targets = self._drop_targets(paths)
        self._set_drop_hint(targets)
        labels = [self._role_label(edit) for edit in targets]
        if labels:
            self.statusBar().showMessage("拖放目标：" + "、".join(labels))
        else:
            self.statusBar().showMessage(
                "未识别的文件类型（支持 .pds/.cpts 程序、.xlsx/.xlsm/.xls 表格、"
                ".csv datalog）"
            )

    def _clear_drop_hint(self) -> None:
        self._set_drop_hint(set())

    def _program_target_edit(self) -> QLineEdit:
        """决定程序文件落到哪个字段：主字段空→主字段；双程序模式且副字段空→副字段；
        否则覆盖主字段。这样「一次拖入 FT+QA 两个文件」能自动分居两侧。"""
        mode = self.mode_combo.currentText()
        two = mode in (MODE_GUFT, MODE_COVERAGE, MODE_CHANGE)
        if not self.program_edit.text().strip():
            return self.program_edit
        if two and not self.gu_program_edit.text().strip():
            return self.gu_program_edit
        return self.program_edit

    def _accept_dropped_paths(self, paths) -> tuple:
        """按扩展名把拖入文件路由到对应输入字段。返回 (已放置描述, 未识别路径)。"""
        placed, rejected, pe_paths = [], [], []
        for raw in paths:
            path = (raw or "").strip()
            if not path:
                continue
            ext = os.path.splitext(path)[1].lower()
            if ext in _PROGRAM_EXT:
                self._program_target_edit().setText(path)
                add_recent("program", path)
                placed.append(f"程序 {os.path.basename(path)}")
            elif ext in _PE_EXT:
                pe_paths.append(path)
            elif ext in _DATALOG_EXT:
                self.datalog_edit.setText(path)
                add_recent("datalog", path)
                placed.append(f"datalog {os.path.basename(path)}")
            else:
                rejected.append(path)
        if pe_paths:
            existing = [p for p in self.pe_edit.text().split(";") if p.strip()]
            for p in pe_paths:
                if p not in existing:
                    existing.append(p)
                add_recent("pe", p)
            self.pe_edit.setText(";".join(existing))
            placed.append(f"PE 表格 {len(pe_paths)} 份")
        return placed, rejected

    # ------------------------------------------------------------- misc
    def _on_gu_k_changed(self, value: float) -> None:
        self.settings["gu_sigma_k"] = float(value)
        save_settings(self.settings)
        self.statusBar().showMessage(
            f"GU σ 倍数已设为 {float(value):.1f}（重新执行分析后生效）"
        )

    def _clear_files(self) -> None:
        """清空输入文件与当前结果，保留模式 / 温区 / σ 倍数，便于开启第二轮对比。"""
        for edit in (self.program_edit, self.pe_edit, self.datalog_edit,
                     self.gu_program_edit):
            edit.clear()
        self.result = None
        self.result_kind = ""
        for attr in ("stats", "gu", "datalog", "pe_program", "program_name",
                     "guft_report", "coverage_report", "compare_report",
                     "ft_name", "gu_name", "qa_name", "base_name", "new_name"):
            setattr(self, attr, None)
        self._rows = []
        self._headers = []
        self._verdict_col = -1
        self.filter_combo.blockSignals(True)
        self.filter_combo.clear()
        self.filter_combo.addItems(["全部", "仅异常"])
        self.filter_combo.setCurrentText("全部")
        self.filter_combo.blockSignals(False)
        self.search_edit.blockSignals(True)
        self.search_edit.clear()
        self.search_edit.blockSignals(False)
        self.table.clear()
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self.legend.setText("")
        self.summary_label.setText("尚未执行")
        self.stage_label.setText("—")
        self.statusBar().showMessage("已清除文件与结果，可开始新一轮对比")

    def _refresh_file_list(self) -> None:
        """「当前文件」面板：按角色列出已选文件，完整路径放 tooltip。

        输入框宽度有限、路径又长，肉眼常看不全——这是把「选了什么」
        从输入框里解放出来的可读性兜底。顺带刷新最近文件下拉。
        """
        if not hasattr(self, "file_list"):
            return
        self._refresh_recent()
        self.file_list.clear()
        roles = [
            (self._role_label(self.program_edit), self.program_edit),
            (self._role_label(self.gu_program_edit), self.gu_program_edit),
            (self._role_label(self.pe_edit), self.pe_edit),
            (self._role_label(self.datalog_edit), self.datalog_edit),
        ]
        for role, edit in roles:
            for part in (edit.text() or "").split(";"):
                path = part.strip()
                if not path:
                    continue
                item = QListWidgetItem(f"{role}：{os.path.basename(path)}")
                item.setToolTip(path)
                self.file_list.addItem(item)
        if self.file_list.count() == 0:
            empty = QListWidgetItem("（尚未选择文件）")
            empty.setForeground(QColor(hex_color("--lc-text-hint")))
            self.file_list.addItem(empty)

    def _refresh_recent(self) -> None:
        """最近文件下拉：每次从 recent.json 现读，add_recent 落盘后立即可见。"""
        if not hasattr(self, "recent_combo"):
            return
        self.recent = load_recent()
        self.recent_combo.blockSignals(True)
        self.recent_combo.clear()
        self.recent_combo.addItem("— 选择最近文件 —")
        seen = set()
        for items in self.recent.values():
            for path in items:
                if not path or path in seen:
                    continue
                seen.add(path)
                self.recent_combo.addItem(os.path.basename(path))
                row = self.recent_combo.count() - 1
                self.recent_combo.setItemData(row, path, Qt.ToolTipRole)
                self.recent_combo.setItemData(row, path, Qt.UserRole)
        self.recent_combo.blockSignals(False)

    def _on_recent_selected(self, index: int) -> None:
        path = self.recent_combo.itemData(index)
        if not path:
            return
        self._accept_dropped_paths([path])    # 复用拖拽同一条路由规则
        self.recent_combo.setCurrentIndex(0)  # 回到占位项，便于再次选择同一路径

    # ------------------------------------------------------------ busy state
    def _set_busy(self, busy: bool, message: str = "") -> None:
        """执行期反馈：按钮禁用 + 文案变化 + 忙碌光标 + 状态栏提示。

        解析大 datalog 是同步阻塞的；必须先把「执行中…」画出来再进重活，
        否则用户会以为卡死而反复点击。
        """
        was_busy = getattr(self, "_busy", False)
        self.run_btn.setEnabled(not busy)
        self.run_btn.setText("执行中…" if busy else "执行对比")
        if busy and not was_busy:
            QApplication.setOverrideCursor(Qt.WaitCursor)
        elif not busy and was_busy:
            QApplication.restoreOverrideCursor()
        self._busy = busy
        if busy and message:
            self.statusBar().showMessage(message)
            self.repaint()                    # 先画出来
            QApplication.processEvents()

    # -------------------------------------------------------------- shortcuts
    def _setup_shortcuts(self) -> None:
        """键盘流：工程师核对数据时手不离键盘。"""
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self._open_for_mode)
        QShortcut(QKeySequence("F5"), self, activated=self.run_btn.click)
        QShortcut(QKeySequence("Ctrl+E"), self, activated=self._export_xlsx)
        QShortcut(QKeySequence("Ctrl+Shift+E"), self, activated=self._export_html)
        QShortcut(QKeySequence("/"), self, activated=self._focus_search)

    def _focus_search(self) -> None:
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    def _open_for_mode(self) -> None:
        """Ctrl+O 按当前模式打开最相关的选择对话框。"""
        if self.mode_combo.currentText() in (MODE_DATALOG, MODE_ANALYSIS):
            self._browse_datalog(self.datalog_edit)
        else:
            self._browse_program(self.program_edit)


def main() -> int:
    app = QApplication([])
    app.setWindowIcon(build_app_icon())   # 任务栏 / Alt-Tab 图标
    window = MainWindow()
    window.center_on_screen()             # 启动即居中，免去找窗口
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
