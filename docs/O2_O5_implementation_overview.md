# O2–O5 落地实现总览（M3）

> Limit Compare Tool · 2026-09-23 续做 · 用户已拍板 O1–O7（D12–D18）

## 交付内容

| 决策 | 落地点 | 状态 |
|---|---|---|
| **O2** 覆盖率区分整体/局部缺失，按可比温区计 | `src/engine/coverage.py` | ✅ 已落地 + 真数据验证 |
| **O3** 场景4 GU vs FT 固化进 engine + GUI | `src/engine/coverage.py` + `src/ui/main_window.py` + `src/export/report.py` | ✅ 已落地 + 真数据验证 |
| **O4** `analyze_datalog` 加 `--ft-program` | `analyze_datalog.py` | ✅ 已落地 + 单测 |
| **O5** Aligner 反解 limit 消歧同名 function | `src/engine/align.py` | ✅ 已落地 + 单测 |

## 关键设计

- **O2**：`CoverageStatus` 新增 `局部缺失`；项级状态优先级
  `ERROR > 未覆盖 > 整体缺失 > 局部缺失 > 覆盖`；`覆盖率` 改为按**两侧都有值的温区**
  计分（新增 `可比温区数`），消除「QA 仅 Room 有值 → 0.0 假象」。
- **O3**：新增 `evaluate_gu_vs_ft`，逐温区校验 `FT.lo ≤ GU.lo 且 GU.hi ≤ FT.hi`；
  GUI 新增「GU ↔ FT 校验 (FV-5)」模式（加载 FT 程序 + GU 程序）+ `export_gu_vs_ft`。
- **O4**：`--ft-program` 提供 FT 基准；用 `align_datalog_items` 反解 as-run limit 消歧
  同名 function 后取 FT/Room 边界，把 GU 校验从「比 QA 伪合格」改为「比 FT 真校验」。
- **O5**：`Aligner.align_datalog_items` 按名匹配，同名多 function 时用候选同温区同侧
  bound 与反解 limit 比对，唯一命中即解析，否则 `AMBIGUOUS`。

## 验证结果

- 全量测试 **50 passed**（原 43 + 新 7），零回归。
- 真数据（产品C .cpts）：FV-1 覆盖率 **97.56%**（旧逻辑 0.0 假象消除），
  7 项真实未覆盖全在 `Fuse_Check`；场景4 抓到 1 真违规 `某 IQ 休眠电流项`
  （GU.Hi 795 > FT.Hi 794）。GUI/CLI 均复现。
- O4 单测：合成 FT 程序（窄 limit）下 GU 由「比 QA 合格」切到「比 FT 失效」。

## 仍待做（非阻塞，M3 收尾）

- FV-1（FT↔QA 覆盖率）/ FV-4（变更前↔后）的 **GUI 模式**尚未接入
  （当前 GUI 有 PE / datalog / 分析 / GU↔FT 四模式）。
- CPTS 仅拿到单侧（仅 FT 或仅 QA）时的用户提示未实现。

## 改动文件清单

- `src/model.py`、`src/engine/coverage.py`、`src/engine/align.py`
- `analyze_datalog.py`、`src/ui/main_window.py`、`src/export/report.py`
- `tests/test_o2_o3_o4_o5.py`（新增）、`docs/PRD.md`（O1–O7 标为已拍板）
