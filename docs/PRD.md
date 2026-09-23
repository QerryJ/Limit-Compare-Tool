# Limit Compare · 功能信息清单与产品规划方案

> 状态：**持续演进中（M2/M3/M4 完成、M5 单文件 exe 已打包）**——本版为 2026-09-23 真数据验证后的校准，
> O1–O7 已于 2026-09-23 经用户拍板（见 D12–D18），其中 **O2/O3/O4/O5 已落地并跑通真数据**
> （覆盖率不误导、GU-vs-FT 固化、真 GU 校验、反解消歧）；**FV-1 / FV-4 的 GUI 模式已于 M3 接入**
> （FT ↔ QA 覆盖率、变更前 ↔ 后 两种桌面模式 + 对应 XLSX/HTML 导出）。
> 作者：@Agent Harness 架构设计师 ｜ 版本：v0.4.3 ｜ 日期：2026-09-24（… + v0.4.3 L 图标/冻结列/忙碌指示/快捷键/最近文件/判定徽章）

---

## 0. 本次设计的诚实标注

- 架构知识库（`SKILL.md` / 案例库）在当前工具集中不可用，本方案不引用外部案例，
  全部依据**既有代码**与**真实素材**（PE 十份 Excel、产品A.pds、产品B.cpts、
  产品A datalog）推导。
- 「已实现」指引擎层已跑通真实数据；「待实现」指新仓库中尚未落地。

---

## 1. 背景与目标

模拟芯片测试的 limit 会在三处流转，任何一处脱节都会造成事故：

```
PE 规格(Excel) ──→ 测试程序(pds/cpts) ──→ 生产实测(datalog) ──→ 出货判定
```

三类事故：**漏放**（limit 过宽）、**过杀**（limit 过紧）、**监控失效**（GU 不比 FT 紧）。

**产品目标**：一个 Windows 桌面、**完全离线**的工具，把上述三处两两可核对，
并把结论落到可直接执行的清单（哪个测试项、从多少改到多少、依据哪份 PE 文件哪一行）。

**非目标**（本期不做）：不做数据库服务器、不做账号体系、不联网、不做自动回写程序文件。

---

## 2. 用户已确认的决策（D）

| 编号 | 决策 | 影响 |
|---|---|---|
| D1 | PE 值**仅映射 Room** 温区 | Hot/Cold 对比本期不做 |
| D2 | 新仓库**借鉴设计重写**，不复制旧代码 | 结构与雏形不同，可自由演进 |
| D3 | **FT 与 QA 两侧都对比更新** | PE 对比产出双侧行 |
| D4 | **场景 2 优先** | 已交付，作为桌面版首个落地模式 |
| D5 | PE 表中 `0/0` = **待测未定**，非有效值 0 | 修正后需更新 1690→1170，1104 项单列 |
| D6 | GUI 框架待定（PyQt6 / PySide6 二选一） | 见 §13 Q1 |
| D7 | 阶段识别以 datalog `Current Limit:` 行为准 | `FTRoom` → FT / Room |
| D8 | GUI 框架 **PySide6** | LGPL，商业分发无授权风险 |
| D9 | 报告 **XLSX + HTML 离线单文件** | HTML 零 CDN，便于邮件分发 |
| D10 | FV-7 版本追溯**纳入 M3** | 稽核刚需，成本低 |
| D11 | 打包 **单文件 exe** | 分发最简单 |
| D12 | **FV-7 版本追溯移出本期**（O6 决定），留待后续版本 | M3 不再含 FV-7 |
| D13 | Hot/Cold 为**独立温区**，现阶段只用 Room，Hot/Cold **保留功能位置、暂不开** | 多温区逻辑本期不做 |
| D14 | 覆盖率区分「整体缺失 / 局部缺失」，覆盖率按可比温区计 | O2 |
| D15 | 场景 4 GU vs FT **固化进 engine + GUI** | O3 |
| D16 | `analyze_datalog` 加 `--ft-program` 做真 GU-vs-FT | O4 |
| D17 | Aligner 用「反解 limit」消歧同名 function | O5 |
| D18 | 更多 ATE 平台**保留为待开发**，本期不扩 | O7 |

> D8–D11 于 2026-09-23 经用户确认，Gate 已通过，进入 M2 编码；D12–D18 为同日 O1–O7 拍板结果。

---

## 3. 默认假设（A，可推翻）

| 编号 | 假设 | 推翻代价 |
|---|---|---|
| A1 | 单用户单机使用，无需工程文件，最近文件 + mapping 持久化即可 | 低 |
| A2 | 报告交付以 **XLSX 为主**，HTML 离线报告为可选增强 | 低 |
| A3 | 打包为**单文件 exe**（PyInstaller），无需安装 Python | 中 |
| A4 | 版本号从 `0.1.0` 起，遵循语义化版本 | 低 |
| A5 | 界面语言简体中文，单位/数值格式不做本地化切换 | 低 |
| A6 | 不做多温区派生规则（Room ⊆ Hot/Cold 校验） | 中，依赖 D1 的扩展 |

---

## 4. 功能信息清单（FV）

### FV-1 · 程序内部 FT ↔ QA 覆盖检查　【引擎已实现 + 真数据验证】

- **输入**：单个 `.pds`（文件内含 FT+QA），或 `.cpts` 的 FT、QA 双文件（自动合并）
- **判定**：QA 区间必须包含 FT 区间，即 `QA.Lo ≤ FT.Lo` 且 `QA.Hi ≥ FT.Hi`
- **输出列**：`GB Lo = FT.Lo − QA.Lo`、`GB Hi = QA.Hi − FT.Hi`（**正 = 有余量**）、
  `Margin% = GB / (FT.Hi − FT.Lo)`、判定
- **判定枚举**：`覆盖` / `未覆盖` / `缺失`（一侧无限值）/ `数据异常`（FT.Lo > FT.Hi）
- **验收**：`Margin%` 的 `N/A`（除零或单边缺失）与 `ERROR`（区间反向）由引擎统一产出，
  UI 与导出**只消费不得自行判空**
- **实测基线**：产品A Room 覆盖率 99.88%（4 项未覆盖，含 `某 CS 类测试项` FT 下限 -47 疑似录入错误）；产品C 7 项未覆盖，全在 `Fuse_Check`（QA 比 FT 紧）。
- **GUI 接入**：桌面模式「FT ↔ QA 覆盖率 (FV-1)」——`.pds` 自带双侧直接比对，`.cpts` 需同时选 FT/QA 两文件经 `merge_sides` 合并；摘要给出**可比温区覆盖率**，**结果表默认展示全部原始 limit 行（不丢数据）**，表头筛选下拉可一键切到「仅异常」（未覆盖 / 局部缺失 / 整体缺失 / 数据异常）；导出 `export_coverage_report`（摘要 / 未覆盖(需处理) / 局部缺失 / 整体缺失 / 全部明细）。

### FV-2 · PE 规格 ↔ 程序，输出待更新清单　【已实现】

- **输入**：PE Excel（可多选，一次导入十份）＋ 程序（`.pds` 或 `.cpts` 双侧）
- **对齐**：精确 → 规范化 → 前缀 → 文件名消歧 → 持久化 mapping
- **输出 Sheet**：待更新 / 程序缺项 / 基线漂移 / 未匹配待确认 / PE待测未定 / 全部明细 / 摘要
- **实测基线**：2699 项对齐 2463（91.3%）、需更新 1170、待测未定 1104、基线漂移 58

### FV-3 · datalog 反推实际 limit（含阶段识别）　【已实现】

- **输入**：ETS88 datalog `.csv`
- **阶段识别**：解析元信息 `Current Limit: FTRoom` → 档位 FT + 温区 Room；
  缺失时默认 FT/Room 并**显式标注**未识别
- **输出**：AsRun limit 文件（Test item / Units / Test Number / LSL / USL / 档位 / 温区
  ＋ 程序名、DataSheet、Lot 元信息），以及与 PE 的对比报告
- **实测基线**：反推 4523 项，与 PE 不符 67 项（收紧 12 / 放宽 54 / 混合 1）

### FV-4 · 变更前 ↔ 后复核　【引擎已实现 + GUI 已接入（变更前 ↔ 后 模式）】

- **输入**：更新前程序、更新后程序（同机台或跨机台）
- **判定**：逐温区逐侧给出方向性结论 `收紧` / `放宽` / `混合` / `相同` / `新增` / `移除`
- **规则**：**放宽 = 红色真风险**。混合变动（Lo 收紧但 Hi 放宽）单独成色为「混合」，
  与雏形「不新增枚举」的旧约定不同——保留独立值便于 UI 区分，
  但在 `summary["放宽风险"]` 口径中与放宽**合并计数**
- **GUI 接入**：桌面模式「变更前 ↔ 后 (FV-4)」——基准程序 + 新程序两个入口（复用「程序文件 / 第二程序」字段，按模式动态改标签）；运行 `compare_programs` 后渲染方向表（放宽/混合/收紧/新增/移除），**结果表默认展示全部原始 limit 行（不丢数据）**，表头筛选下拉可一键切到「仅异常」（放宽/混合/收紧/新增/移除）；摘要**领先展示「放宽风险」**；导出 `export_compare_report`（摘要 / 放宽风险 / 新增与移除 / 变更明细逐格 / 全部明细）。

### FV-5 · GU limit 自动生成 + 收紧校验　【CLI + 引擎 + GUI 已固化（O3/O4）】

- **生成**：`GU = mean ± k·σ`，默认 `k = 3`（对齐 `30Pcs 3sigma` 惯例）
- **校验**：GU 必须**严格落在 FT 之内**，否则判「GU 比 FT 宽(失效)」——
  GU 比 FT 宽则无法验证 setup 正常
- **场景 4（GU 程序 ↔ FT 程序）已固化**：`engine.coverage.evaluate_gu_vs_ft`
  逐温区校验 `FT.lo ≤ GU.lo` 且 `GU.hi ≤ FT.hi`，并接入 GUI「GU ↔ FT 校验 (FV-5)」模式 +
  `export.export_gu_vs_ft`。真数据复核：产品C 抓到 1 项失效
  （`某 IQ 休眠电流项` GU 高边 795 > FT 794，GUI/CLI 均复现）。
- **真 GU-vs-FT（datalog ↔ FT 程序）**：`analyze_datalog.py` 新增 `--ft-program`
  （O4），以反解 limit 消歧同名 function 后取 FT/Room 基准，避免「比的是 QA 假合格」。
- **实测基线（伪 GU，比 QA）**：合格 2984 / 与 FT 相同 76 / 失效 37（Rejects 样本）。
- **⚠ 样本偏差**：现有 datalog 为 Rejects 样本且仅 9 颗，正式结论须用 ≥30 颗正常批次

### FV-6 · Cpk 合理性分析　【CLI 已实现，待接入 GUI】

- **判定**：`过紧`（Cpk < 1.33）/ `过松`（Cpk ≥ 2.0）/ `偏心`（偏移比 > 0.3）/
  `合理` / `无波动` / `无限值` / `数据不足`
- **阈值可配**：`--tight` `--loose` `--skew`

### FV-7 · 版本追溯与稽核留痕　【待定，见 §13 Q4】

- 记录 `Test program Revision`、`Data Sheet Revision` 及修改日期（datalog 元信息已有）
- 导出 limit 变更单（谁、何时、从 X 改到 Y、依据哪版 PE）

---

## 5. 六层架构（E / C / S / L / T / V）

| 层 | 职责 | 落地 |
|---|---|---|
| **E** 环境 | Windows 10/11 桌面、完全离线、单 exe | PyInstaller 打包，零网络调用 |
| **C** 上下文/输入 | 三类数据源适配，统一为内部模型 | `parsers/` 四个解析器 |
| **S** 状态 | 最近文件、mapping 字典、阈值与偏好 | `config/` JSON 持久化 |
| **L** 逻辑 | 对齐、覆盖、对比、Cpk/GU、校验 | `engine/`（纯函数、可单测） |
| **T** 能力 | XLSX / HTML 导出、CLI 批处理 | `export/` ＋ 三个 CLI |
| **V** 视图 | 桌面 GUI：导入、模式、结果表、筛选、导出 | `ui/`（PyQt6 或 PySide6） |

**层间铁律**：`L` 与 `C` 不得 import `V`；`V` 只消费 `L` 的结果，不得自行判空或重算方向。
`N/A` / `ERROR` / 方向枚举的产出权在引擎层（延续雏形的单一真值原则）。

---

## 6. 模块结构与关键接口

```
src/
  model.py                 Bound / LimitItem / ProgramModel / PeItem / PeProgram
  parsers/
    numeric.py             parse_number(raw) -> float|None
    pds.py                 PdsParser.parse_file(path) -> ProgramModel
    cpts.py                CptsParser.parse_file(path) -> ProgramModel
                           merge_sides(ft, qa, name="") -> ProgramModel
    pe_excel.py            parse_files(paths, program_id) -> PeProgram
    datalog.py             parse_datalog(path) -> Datalog
                           parse_limit_tag(tag) -> (SourceType, TempZone)
                           datalog_to_program(data) -> ProgramModel
  engine/
    align.py               Aligner(program, mapping).match_all(pe_items) -> list[Match]
    coverage.py            evaluate_coverage(program, zones) -> CoverageReport
    pe_compare.py          compare_pe_to_program(pe, program, matches, zone, sides)
                             -> PeCompareResult
    compare.py             compare_programs(base, new, zones) -> CompareReport
    analysis.py            compute_stat(...) -> ItemStat
                           propose_gu(..., k=3.0) -> GuProposal
    validator.py           【待实现】validate(slots) -> list[ValidationIssue]
  export/
    report.py              export_pe_report(path, result, matches, ...)
    analysis_report.py     export_analysis(path, stats, gu, meta, ...)
    datalog_limit.py       export_datalog_limit(path, data)
  ui/                      【待实现】main_window / panels / table / legend
  config/                  【待实现】settings.py / recent.py
compare_pe.py              CLI 场景 2
datalog_pe.py              CLI 场景 2b
analyze_datalog.py         CLI Cpk + GU
```

**待实现接口的签名约定**：

```python
# engine/coverage.py
def evaluate_coverage(program: ProgramModel, zones: list[TempZone]) -> CoverageReport
def coverage_status(ft: Bound|None, qa: Bound|None) -> CoverageStatus

# engine/compare.py
def compare_programs(base: ProgramModel, new: ProgramModel,
                     zones: list[TempZone]) -> CompareReport

# engine/validator.py
def validate(slots) -> list[ValidationIssue]   # BLOCK / WARN / INFO 三态
```

---

## 7. 数据模型

完整定义见 [`docs/db/data-model.md`](../db/data-model.md)。
要点：`LimitValue = float | None`（`None` 表示未设，**绝不存 0**）；
对齐键 `function|test_item`；`bounds[TempZone][SourceType] = Bound`。

## 8. UI 与视觉规范

设计令牌见 [`docs/design-system/tokens.css`](../design-system/tokens.css)。
基线：效率型桌面工具、桌面优先、信息密度 Comfortable/Compact 可调、
**PASS 绿 / FAIL 红且不得仅靠颜色传达语义**（须同时有文字或形状标识）。

**结果表与筛选（v0.2.3 增强）**：
- **全量原始数据**：任一模式下结果表默认渲染**全部原始 limit 行**，不预过滤、不丢弃；
  异常只是「判定列」的一个取值，数据完整性优先于「只看异常」的默认视图。
- **表头筛选下拉**：结果表上方提供筛选下拉（默认「全部」），含「仅异常」快捷项
  以及各模式判定列的去重取值（如覆盖率：未覆盖/局部缺失/整体缺失/数据异常；
  变更：放宽/混合/收紧/新增/移除；GU：GU 比 FT 宽(失效)）。筛选**仅收窄视图**，不删除底层行。
- **作者 / 版本标注**：主窗口右上角常驻显示 `作者: Quincy · v{版本号}`，便于现场审计与版本确认。

**文件输入与复用（v0.3.0 增强）**：
- **拖拽上传**：主窗口整体接收拖放，按扩展名自动路由——`.pds/.cpts` → 程序、
  `.xlsx/.xlsm/.xls` → PE 表格（多份追加）、`.csv` → datalog；未识别扩展名明确提示。
  双程序模式（GU↔FT / 覆盖率 / 变更前↔后）下**一次拖入两个程序会自动分居主/副字段**，不互相覆盖。
  浏览按钮保留，拖拽与之等价。
- **清除文件**：工具栏「清除文件」一键清空四个输入字段与当前结果（表格/摘要/图例/筛选），
  **保留模式、温区与 σ 倍数**，便于对比完成后直接开启第二轮。
- **GU σ 倍数可配**：分析模式提供 `GU σ 倍数` 输入框，默认 **3.0**（对齐 30Pcs 3sigma 惯例），
  范围 1.0–6.0、步长 0.5，改动持久化到 `settings.gu_sigma_k`，重新执行分析后生效。
- **导出弹窗默认落在数据上传位置**：按当前模式取主输入文件所在目录打开，
  无输入时回退到上次导出目录，最终位置仍由用户选择。
- **Excel 锁文件容错**：跳过 `~$xxx.xlsx`（Excel 打开时生成的属主锁文件），
  避免工程师开着 PE 表就用工具时崩溃（真实会踩到的坑）。

**报告可信与查找效率（v0.4.0 增强，对应「芯片测试经理视角」GR-1~GR-4）**：
- **稽核信息块（2026-09-24 精简）**：只保留 `导出时间 / 筛选信息（结果筛选·搜索·导出口径·行数）/
  对比源文件全路径 / 对比总结`；**不写工具版本与作者**——报告要交付客户与质量部，不带工具与作者信息。
  XLSX 前置「稽核信息」Sheet，HTML 报告头内嵌稽核表并单列「对比总结」小节。
- **导出报告表头筛选**：XLSX 的**数据表**统一开启 AutoFilter + 冻结首行（键值型摘要表跳过，
  避免筛选箭头干扰阅读）；HTML 报告内联「判定列下拉 + 关键字框」（内联 JS，零 CDN，仍是离线单文件）。
  两者**默认显示全部**，让用户自己筛出未通过项，不预先隐藏任何行。
- **导出口径确认**：筛选或搜索后导出 HTML 时，弹窗明确给出
  「导出全量（M 行）/ 仅导出当前视图（N 行）/ 取消」，杜绝 v0.2.3 那类"数据静默消失"在导出环节重演。
  XLSX 恒为引擎全量结果，并在稽核块中标注"不受界面筛选影响"。
- **搜索 + 排序**：结果表上方搜索框（Function / Test item，与判定筛选叠加生效）；
  表头可点击排序，数值列按**数值大小**排（避免 "10" 排在 "9" 前）。
- **缺文件友好提示**：单侧 `.cpts` / 缺基准或新程序时，明确指出缺哪一侧及补救方式（含拖拽方式）。

**桌面可用性（v0.4.2 增强）**：
- **启动即居中**：主窗口按主屏幕可用区域正中打开（无屏幕环境安全跳过）。
- **字母 L 图标**：由 `src/ui/icon.py` 用 **QPainter 矢量绘制**（圆角方块 + 一竖一横两条
  笔画路径构成 L，斜接拐角；**不依赖系统字体**——Qt 离屏平台字体库可能为空，
  drawText 会画出豆腐块）；运行时作为窗口/任务栏图标，`assets/app.ico`（多尺寸 PNG 条目）
  供 PyInstaller 打包 exe 文件图标。
- **拖拽目标高亮**：拖拽悬停期间按扩展名**预测落点**并高亮对应输入框
  （QSS 属性选择器 `[dropTarget="true"]` + 重新 polish），状态栏同步提示
  「拖放目标：程序 / PE 表格…」；未识别类型也有明确提示。拖离或落下即清除。
  落点规则与真实路由 `_accept_dropped_paths` 保持一致（有单测守护）。
- **当前文件面板**：左侧按「角色：文件名」列出已选文件（角色随模式变化，如 QA 程序/新程序），
  完整路径放 tooltip；选择 / 拖入 / 清除 / 切模式自动刷新。

**效率与可读性（v0.4.3 增强）**：
- **冻结左侧两列**：明细表 10+ 列横向滚动时 Function / Test item 始终可见
  （`src/ui/frozen_table.py`，按 Qt 官方 Frozen Column 方案用覆盖层实现；
  **主表仍持有全部数据**，`item()`/排序/导出不受影响）。
- **执行中忙碌指示**：执行对比时按钮禁用并显示「执行中…」+ 忙碌光标 + 状态栏提示；
  解析是同步阻塞的，先重绘再进重活，避免被误认为卡死而反复点击；失败路径必定恢复按钮。
- **键盘快捷键**：`Ctrl+O` 按当前模式打开主输入、`F5` 执行、`Ctrl+E` 导出 XLSX、
  `Ctrl+Shift+E` 导出 HTML、`/` 聚焦搜索框（按钮 tooltip 已标注）。
- **最近文件下拉**：`recent.json` 一直在记，现在露出来；选中即按扩展名自动落到对应输入框
  （与拖拽共用同一条路由规则），重复核对同一料号省 3 步。
- **判定列徽章**：判定值以 **颜色（前景）+ 形状（圆角方块图标）+ 文字** 三重编码，
  满足「语义不得仅靠颜色传达」；徽章走 `DecorationRole`，**不污染单元格文本**，
  导出与筛选拿到的仍是干净判定值。

**样式（v0.4.0）**：Qt 样式表由 `src/ui/style.py` 从 `tokens.css` **运行时生成**
（背景/圆角/间距/字体/主按钮/表头/斑马纹/选中/滚动条），不硬编码任何颜色；
扩展了交互态令牌（`--lc-accent` / `--lc-selection-bg` / `--lc-row-alt` / `--lc-surface-hover` 等）。
注意：**不得给裸 `QWidget` 设 background**，否则会级联到表格视口盖掉斑马纹。
「执行对比」为主行动按钮（`objectName=primary`），数值列等宽右对齐（令牌 `--lc-numeric-font`）。

## 9. 离线与打包

- PyInstaller 单文件 exe，内嵌 Python 与 openpyxl；**运行时零网络请求**
- 导出 HTML 报告须内联 CSS/JS，**零 CDN**，可离线双击或邮件分发（沿用雏形约束）
- 配置与 mapping 写入用户目录，不写程序安装目录

## 10. 仓库与工程规范

遵循项目组规范 §2：README / LICENSE / .gitignore / CONTRIBUTING / CHANGELOG /
.github 模板 / 语义化版本 / 分支策略（详见 `CONTRIBUTING.md`）。
分支：`main`（发布）· `develop`（集成）· `feature/*` · `release/*` · `hotfix/*`。
提交：Conventional Commits（`feat:` `fix:` `docs:` `refactor:` `test:` `chore:`）。

---

## 11. 里程碑

| 阶段 | 内容 | 产出 |
|---|---|---|
| **M1** | 仓库骨架 + 规范文件 + 设计令牌 | 本文档、tokens.css、README/LICENSE/CI |
| **M2** | GUI 外壳：导入、模式切换、结果表、筛选、导出 | 桌面版可跑通 FV-2 / FV-3 |
| **M3** | O2 局部缺失 + O3 GU-vs-FT 固化(引擎+GUI) + O4 `--ft-program` + O5 对齐消歧 ✅ 已落地；**FV-1 / FV-4 GUI 模式已接入 ✅** | 六场景全通、GU 真校验、覆盖率不误导、变更复核可视化 |
| **M4** | FV-5 / FV-6 接入 GUI（Cpk 面板、GU 面板） | 分析能力可视化 |
| **M5** | 打包 exe + 离线验证 + 发布 v0.1.0 | ✅ 已完成：`dist/LimitCompare.exe`（45MB 单文件，含 PySide6/openpyxl/tokens.css，离线零网络）｜**v0.2.3 增强**：结果表全量原始数据不丢、表头筛选下拉、右上角作者/版本标注 |

---

## 12. 决策确认记录（原阻塞项，已拍板）

| 编号 | 问题 | 结论 |
|---|---|---|
| Q1 | GUI 框架 PyQt6 还是 PySide6？ | **PySide6**（LGPL，商业分发无授权风险） |
| Q2 | 是否需要工程文件保存对比配置？ | **暂不做**，仅持久化最近文件 + mapping（沿用 A1） |
| Q3 | 报告是否需要 HTML 离线版？ | **要**，XLSX + HTML 双导出，HTML 内联零 CDN |
| Q4 | FV-7 版本追溯是否纳入 M3？ | **纳入** |
| Q5 | 打包形态 | **单文件 exe** |

## 12.1 生产级自查

| 项 | 状态 | 说明 |
|---|---|---|
| 离线可用 | 通过 | 运行时零网络请求；HTML 报告内联 CSS，无 CDN |
| 空值语义 | 通过 | `None` 与 `0` 严格区分；`0/0` 按「待测未定」 |
| 浮点容差 | 通过 | `_close()` 相对+绝对 `1e-9` |
| 判定单一来源 | 通过 | 引擎产出，UI/导出只消费 |
| 语义不只靠颜色 | 通过 | 判定列必带文字，颜色仅辅助 |
| 结果表全量原始数据 | 通过 | 任一模式默认渲染全部原始 limit 行，异常不预过滤、不丢数据；筛选仅收窄视图 |
| 表头筛选下拉 | 通过 | 全部/仅异常/各判定取值可切；GUI 测试验证「仅异常」行数 0 < 异常 < 全量 |
| 作者/版本标注 | 通过 | 右上角常驻 `作者: Quincy · v0.2.3`，GUI 测试断言文本含 `Quincy` 与 `v0.2.3` |
| 设计令牌单一来源 | 通过 | UI 运行时读取 `tokens.css`，打包后从 `_MEIPASS` 读取 |
| 单元测试 | 通过 | 110 项（`tests/`），覆盖解析/对齐/对比/覆盖/变更/分析/GUI 冒烟（含 FV-1/FV-4 模式与导出、结果表全量数据 + 表头筛选、作者/版本标注、拖拽路由 / 清除文件 / σ 倍数 / 导出目录、Excel 锁文件容错、稽核信息 / 导出口径 / 搜索 / 数值排序 / 令牌化样式 / 导出报告表头筛选、L 图标像素断言 / 启动居中 / 拖拽目标高亮 / 当前文件面板、**冻结列镜像 / 忙碌状态 / 失败恢复 / 徽章不污染文本 / 最近文件路由**） |
| 报告稽核信息 | 通过 | 仅含 导出时间 / 筛选信息 / 源文件全路径 / 对比总结；**不含工具版本与作者**（交付客户） |
| 导出口径 | 通过 | 筛选后导出 HTML 弹窗确认全量 vs 当前视图，取消即中止；XLSX 恒为全量并标注 |
| 搜索与排序 | 通过 | 名称列搜索与判定筛选叠加；数值列按数值大小排序（`_SortItem`） |
| 导出报告表头筛选 | 通过 | XLSX 数据表 AutoFilter + 冻结首行（摘要类键值表跳过）；HTML 内联判定下拉 + 关键字框，零 CDN |
| 样式令牌单一来源 | 通过 | `src/ui/style.py` 运行时从 `tokens.css` 生成 QSS，零硬编码颜色；紧凑/宽两种密度 |
| 拖拽上传 | 通过 | 主窗口 acceptDrops，按扩展名路由；双程序模式一次拖入两个文件自动分居主/副字段 |
| 清除文件 | 通过 | 一键清空输入与结果，保留模式/温区/σ 倍数，第二轮对比零残留 |
| GU σ 倍数 | 通过 | 默认 3.0（30Pcs 3sigma），1.0–6.0 可调并持久化 |
| Excel 锁文件容错 | 通过 | `parse_files` 跳过 `~$*.xlsx`，避免 Excel 占用时 PermissionError |
| GUI 冒烟 | 通过 | PySide6 6.11.2，headless 端到端已验证（真实 PE 目录 + 真实 .pds） |
| 打包 exe | 通过 | 单文件 `dist/LimitCompare.exe`（45MB），含 PySide6/openpyxl/tokens.css，离线零网络；`build.spec` 已改为基于 `SPECPATH` 的绝对路径（任意 cwd 可打包） |

## 13. 遗留问题与未知区（校准至 2026-09-23 验证后）

1. **Hot/Cold 为独立温区（O1/D13 已拍板）**：PE 表无温区列，D1 仅做 Room；Hot/Cold 判定为
   **独立温区**，现阶段只用 Room，多温区包含关系校验本期不做，但温区枚举与功能位置已保留。
2. **GU 样本偏差（已缓解）**：早期唯一 datalog 为 Rejects（9 颗）；现已新增 Bin1 GU Loop
   （100 颗）与 产品C GU，可下正式结论。
3. **CTA8290 端到端 ✅ 已验证**：产品C 家族 FT/QA/GU 三份成对文件已解析、`merge_sides`、
   FV-1 与场景 4 全跑通；并修复 `IsQAFile` 恒为 0 导致边误判的阻断 bug（`SourceType` 新增 GU）。
4. **跨机台对比未验证**：`.pds` vs `.cpts` 跨机台场景仅有告警设计（V-3），无真实数据验证。
5. **CPTS 单侧文件提示**：若只拿到 FT 或只拿到 QA，如何提示用户（沿用 V-1 BLOCK）尚未实现。
6. **覆盖率局部缺失呈现（O2/D14 已落地）**：`CoverageStatus` 新增 `局部缺失`；
   项级状态按 `ERROR>未覆盖>整体缺失>局部缺失>覆盖` 定级，`覆盖率` 改为**按可比温区**
   （两侧都有值的温区）计。真数据复核：产品C QA 仅 Room 有值，旧逻辑显 0.0，新逻辑
   覆盖率 **97.56%**，275 项标「局部缺失」、88 项「整体缺失」、7 项真实「未覆盖」（`Fuse_Check`）。
7. **同名 function 消歧（O5/D17 已落地）**：`Aligner.align_datalog_items` 用反解 limit
   匹配候选 function 同温区同侧 bound 消歧（唯一命中即解析，否则 AMBIGUOUS）。已单测覆盖
   同名多 function 唯一消歧 / 无候选 / 单候选。

---

## 14. 遗留问题与未知区（校准至 2026-09-23 验证后）

> **O1–O7 已全部拍板（D12–D18）并进入编码**：O2/O3/O4/O5 已落地且真数据验证通过；
> O1 独立温区保留位置暂不开、O6 版本追溯移出本期、O7 更多 ATE 平台保留待开发。
> 下列为**数据层待你领域定性**项（非产品决策，但不定性会影响结论可信度）。

**数据层待你领域定性（非产品决策，但影响结论可信度）**：

- 产品C `Fuse_Check`：QA 比 FT 还紧（QA 128~192 vs FT 0~255）→ 是 **QA 过严** 还是 **FT 过松**？
- 产品C `某 IQ 休眠电流项`：GU 高边 795 > FT 794 → GU 程序**真 bug**（O3 已抓出），建议改程序。
- Bin1 `CS_NOC_DAC*_LSB_20mV`：实测 mean≈20 但 PDS FT=[-21,-19] 符号相反 → **源数据约定不一致**，需核查。
- Bin1 FV-3：本次 QA 实际 limit 比 PE 宽松 2010 项（过杀）→ 是否 **PE 的 QA 列定太松**？

**工程遗留（非阻塞）**：

- CPTS 单侧文件提示（只拿到 FT 或只拿到 QA 时如何提示用户）尚未实现（沿用 V-1 BLOCK 思路）。
- 跨机台 `.pds` vs `.cpts` 对比仅有告警设计，无真实数据验证。

> O1–O7 拍板后已据 D12–D18 更新本文档并进入对应编码；未拍板前不动功能代码（Gate 铁律已执行）。
