# Limit Compare

模拟芯片测试 **limit 对比工具** —— Windows 桌面应用，**完全离线**（无网络、无云端、无遥测）。

把 limit 流转的三处「PE 规格 → 测试程序 → 生产实测」两两核对，
输出可直接执行的修订清单，用于**防漏放、防过杀、防 GU 监控失效**。

当前版本 **v0.4.4** · MIT 许可 · 单文件 exe 可分发

---

## 它能解决什么

| 痛点 | 本工具的做法 |
|---|---|
| PE 规格改了，程序没跟着改 | FV-2：逐项比对，输出「待更新清单」（含 sheet / 行号 / 当前值→目标值） |
| 程序里 FT 与 QA 互不覆盖 | FV-1：覆盖率检查，标出未覆盖 / 局部缺失 / 整体缺失 |
| 实测用的到底是不是 PE 的 limit | FV-3：从 datalog 反推实际施加的 limit，再与 PE 核对 |
| 改完 limit 不知道有没有改坏 | FV-4：变更前 ↔ 后复核，标出收紧 / 放宽 / 混合 |
| GU 监控形同虚设 | FV-5：按 `mean ± kσ` 生成 GU limit，并校验必须严格落在 FT 之内 |
| limit 定得太松或太紧没人知道 | FV-6：Cpk 合理性分析（过松 / 过紧 / 偏心） |

## 支持的文件

| 类型 | 扩展名 | 说明 |
|---|---|---|
| ETS88 测试程序 | `.pds` | 单文件内含 FT + QA |
| CTA8290 测试程序 | `.cpts` | 单侧文件，FT / QA 双文件自动合并 |
| PE 规格 | `.xlsx` / `.xlsm` | 表头按**文字**定位，兼容各文件表头不一致 |
| ETS88 datalog | `.csv` | 转置宽表，`Current Limit:` 行标识阶段 |

---

## 桌面 GUI（推荐）

```bash
python main.py
```

### 六种对比模式

| 模式 | 用途 |
|---|---|
| `PE ↔ 程序 (FV-2)` | PE 规格 vs 测试程序，输出待更新清单 |
| `datalog ↔ PE (FV-3)` | 实测 limit vs PE 规格 |
| `Cpk / GU 分析 (FV-5/6)` | Cpk 合理性 + GU limit 生成 |
| `GU ↔ FT 校验 (FV-5)` | GU 是否严格落在 FT 内 |
| `FT ↔ QA 覆盖率 (FV-1)` | 程序内部 FT / QA 覆盖检查 |
| `变更前 ↔ 后 (FV-4)` | 变更复核，标出收紧 / 放宽 |

### 常用操作

| 快捷键 | 动作 |
|---|---|
| `Ctrl+O` | 按当前模式打开文件 |
| `F5` | 执行对比 |
| `Ctrl+E` | 导出 Excel |
| `Ctrl+Shift+E` | 导出 HTML |
| `/` | 聚焦搜索框 |

- **拖拽上传**：把文件或文件夹直接拖到窗口，按扩展名自动分流到对应栏位，
  拖拽过程中目标栏位会高亮指示。
- **清除文件**：一键清空当前所有栏位，直接开始第二轮对比。
- **表头筛选**：结果表头下拉可只看异常；搜索框支持关键字过滤。
- **导出**：Excel 与 HTML 报告均自带表头筛选，可直接在报告里筛出「未通过」项；
  报告首个工作表是「稽核信息」（导出时间、源文件全路径、筛选口径、对比总结）。
- **GU sigma 倍数**：默认 `mean ± 3σ`，可在界面上手动调整倍数。

---

## 命令行

CLI 入口都收敛在 `scripts/`：

```bash
# FV-2：PE 规格 vs 程序，输出待更新清单
python scripts/compare_pe.py --pe-dir <PE目录> --program <file.pds> --out <report.xlsx>

# CTA8290（FT / QA 双文件）
python scripts/compare_pe.py --pe-dir <dir> --program-ft <ft.cpts> \
    --program-qa <qa.cpts> --out <report.xlsx>

# FV-3：datalog 反推实际 limit，并与 PE 核对
python scripts/datalog_pe.py --datalog <run.csv> --pe-dir <PE目录> \
    --out-limit <asrun.xlsx> --out <compare.xlsx>

# FV-5 + FV-6：Cpk 分析与 GU limit 生成校验
python scripts/analyze_datalog.py --datalog <run.csv> --sigma-k 3 --out <analysis.xlsx>
```

---

## 快速开始

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt

python main.py              # 启动 GUI
python -m pytest -q         # 跑测试
```

### 打包成单文件 exe

```bash
.venv\Scripts\pip install pyinstaller
pyinstaller build.spec --noconfirm
# 产物：dist\LimitCompare.exe（离线可用，双击即开）
```

---

## 目录结构

```
main.py                 GUI 入口
build.spec              PyInstaller 打包配置（cwd 无关）
src/
  model.py              数据模型
  parsers/              pds / cpts / pe_excel / datalog / numeric
  engine/               align / compare / pe_compare / coverage / analysis
  export/               report / html_report / audit / analysis_report / datalog_limit
  ui/                   main_window / frozen_table / style / theme / icon
  config/settings.py    本地设置与最近文件持久化
scripts/                CLI 入口与一次性验证脚本
tests/                  pytest 用例（真实素材用例默认 skip）
docs/
  PRD.md                功能信息清单与产品规划方案
  design-system/tokens.css   设计令牌（颜色 / 密度 / 语义）—— 唯一事实来源
  db/data-model.md      数据模型与持久化 schema
config/
  mapping.example.json  名称对齐 mapping 示例（结构说明）
assets/                 应用图标
```

**分层约定**：引擎（E / C / S / L）负责算，UI 层（V）只负责呈现，**绝不重新推导判定**。
颜色与尺寸一律来自 `docs/design-system/tokens.css`，代码里不出现硬编码色值。

---

## 数据隐私

- 本工具 **完全离线**：不联网、不上传、不采集任何使用数据。
- 仓库 **不包含任何真实料号或实测数据**。`Material/` 已在 `.gitignore` 中排除，
  文档中出现的产品编号均已做中性化处理。
- 生成的报告、本机设置、最近文件列表 (`output/`、`results/`、`config/settings.json`、
  `config/recent.json`) 都不入库 —— 它们带有本机绝对路径。
- 名称对齐 mapping (`config/mapping_*.json`) 含产品专属命名，同样不入库；
  仓库只提供 `config/mapping.example.json` 说明结构。

> 请勿把真实素材目录提交进来。如需版本化管理素材，请用私有存储或 Git LFS，
> 并先确认符合公司的对外披露规定。

---

## 真实素材端到端测试（可选）

默认 `python -m pytest -q` 不依赖任何素材，开箱即绿。想跑真实数据用例时，
把本机素材目录指进来：

```bash
set LIMIT_COMPARE_MATERIAL_DIR=D:\material                 # 程序与 datalog 所在目录
set LIMIT_COMPARE_PE_DIR=D:\material\<PE 规格目录>          # 可选，精确指定 PE 目录
python -m pytest -q
```

未设置时相关用例自动 skip。详见 [`tests/real_material.py`](tests/real_material.py)。

---

## 文档索引

- 功能与规划：[`docs/PRD.md`](docs/PRD.md)
- 数据模型：[`docs/db/data-model.md`](docs/db/data-model.md)
- 设计令牌：[`docs/design-system/tokens.css`](docs/design-system/tokens.css)
- 产品完善建议（测试经理视角）：[`docs/产品完善建议-芯片测试经理视角.md`](docs/产品完善建议-芯片测试经理视角.md)
- 贡献与规范：[`CONTRIBUTING.md`](CONTRIBUTING.md)
- 变更记录：[`CHANGELOG.md`](CHANGELOG.md)

## 许可

MIT，见 [`LICENSE`](LICENSE)。
依赖 PySide6（LGPL），用于桌面 GUI 层。
