# 数据模型说明（Limit Compare）

> 文档为单一事实来源，代码不得与本文档分叉。
> 本工具为离线桌面软件，**不使用数据库**；持久化仅为本地 JSON。

---

## 1. 核心约定（铁律）

1. `LimitValue = float | None`。`None` 表示**未设置**，
   **绝不允许存 0，也绝不允许按 0 参与比较**。
   （来源：PE 表中大量空单元格；程序文件中未填的温区/侧别。）
2. 对齐键：`function + '|' + test_item`。
3. `bounds` 结构：`bounds[TempZone][SourceType] = Bound`，
   只存放实际存在的 (温区, 侧别) 组合。
4. `0/0` 的语义由**用户确认**：在 PE 侧表示「待测未定」，不是有效 limit。
   仅当 `lo == 0 且 hi == 0` 时判为未定；单边为 0（如 `0 ~ 1`）仍是合法单边 limit。
5. 浮点比较必须用容差（相对 + 绝对 `1e-9`），禁止 `==` 直接判等。

---

## 2. 实体

### Bound
| 字段 | 类型 | 说明 |
|---|---|---|
| lo | float \| None | 下限 |
| hi | float \| None | 上限 |

### LimitItem（程序中的一个测试项）
| 字段 | 类型 | 说明 |
|---|---|---|
| function | str | Function 名（`.pds` 的 section / `.cpts` 的 function） |
| test_item | str | 测试项名 |
| unit | str | 单位 |
| sub_test_nmbr | str | 子测试号 |
| bounds | dict | `{TempZone: {SourceType: Bound}}` |
| source_files | list[str] | 来源文件 |
| machine_type | MachineType | ETS88 / CTA8290 |

### ProgramModel（一个测试程序）
`id`, `name`, `machine_type`, `functions: list[str]`, `items: list[LimitItem]`

### PeItem（PE 规格表中的一行）
| 字段 | 类型 | 说明 |
|---|---|---|
| name | str | PE 的 Test item（可能与程序名不一致） |
| unit | str | 单位 |
| ate_test_no | str | ATE Test# |
| ft_lo / ft_hi | float \| None | PE 给的 FT 目标 |
| qa_lo / qa_hi | float \| None | PE 给的 QA 目标 |
| old_lo / old_hi | float \| None | PE 记录的「Old program」值，用于三方基线校验 |
| guardband | float \| None | PE 的 Comments 列（QA = FT ± GB） |
| source_file / row | str / int | 溯源：来自哪份 PE 文件第几行 |

### Datalog（一次生产实测）
`program_name`, `data_sheet`, `lot`, `limit_tag`, `side`, `zone`,
`items: list[DatalogItem]`, `measurements: dict[str, list[float]]`, `bins: list[str]`

---

## 3. 枚举

| 枚举 | 取值 | 用途 |
|---|---|---|
| MachineType | ETS88 / CTA8290 | 机台 |
| SourceType | FT / QA / GU | 侧别 |
| TempZone | Room / Hot / Cold | 温区（当前仅用 Room） |
| MatchStatus | exact / prefix / mapped / filename_hint / ambiguous / unmatched | 名称对齐 |
| UpdateStatus | 无需更新 / 需更新 / 程序缺项 / 仅程序有 / PE待测未定 | FV-2 结果 |
| Direction | 收紧 / 放宽 / 混合 / 一致 / 补值 / — | 变更方向 |
| CoverageStatus | covered / uncovered / missing / error | FV-1（待实现） |
| ChangeDirection | tighter / looser / same / onlyInA / onlyInB | FV-4（待实现） |
| Verdict | 过松 / 过紧 / 偏心 / 合理 / 无波动 / 无限值 / 数据不足 | FV-6 |
| GuVerdict | GU 更紧(合格) / GU 与 FT 相同 / GU 比 FT 宽(失效) / 无法判定 | FV-5 |
| Severity | block / warn / info | 校验（待实现） |

**方向语义（易混淆，务必按此理解）**
- `收紧` = 目标值比当前更严（程序现比 PE 松 → **漏放风险**，必须改）
- `放宽` = 目标值比当前更松（程序现比 PE 紧 → 过杀，可选优化）

**GU 语义（侧别，务必按此理解）**
- CTA8290 由 `_GU_` 命名的程序文件提供**真实 GU**（写入 `SourceType.GU`）。
- ETS88 程序**无独立 GU 列**，其 QA limit 在 GU↔FT 校验（FV-5）中作为「GU 程序」载入时，由 `promote_qa_to_gu` 视为 GU limit——**仅当该温区 GU 缺失时把 QA 补位为 GU，不覆盖已有真实 GU**。
- 该映射只发生在 GU↔FT 路径的「GU 程序」上；FV-1 覆盖率等其它模式仍按原语义读取 QA，不受影响。

---

## 4. 本地持久化（JSON，非数据库）

### `config/mapping_<product>.json` — 名称对齐人工决策
```json
{
  "IQVDD333P15VSW": "IQ|IQ_VDD33_3P15V_SW",
  "CS1NOC0P28VCMP": "Compara_Ramp|CS1_NOC_0P28V_CMP"
}
```
键为 PE 名归一化结果（大写、仅保留字母数字），值为 `function|test_item`。
**人工决策只做一次，后续导入自动复用。**

### `config/settings.json`（待实现）
```json
{
  "density": "comfortable",
  "zone": "Room",
  "cpk_tight": 1.33,
  "cpk_loose": 2.0,
  "cpk_skew": 0.30,
  "gu_sigma_k": 3.0,
  "export_dir": ""
}
```

### `config/recent.json`（待实现）
```json
{ "program": [], "pe_dir": [], "datalog": [] }
```

---

## 5. 产物（输出文件）

| 文件 | Sheet | 说明 |
|---|---|---|
| `PE_limit_update_list_<id>.xlsx` | 摘要 / 待更新 / 程序缺项 / 基线漂移 / 未匹配待确认 / 全部明细 | FV-2 |
| `AsRun_Limit_<id>.xlsx` | 实际 Limit / 元信息 | FV-3 |
| `datalog_vs_PE_<id>.xlsx` | 摘要 / 待更新 / … | FV-3 对比 |
| `datalog_analysis_<id>.xlsx` | 摘要 / Cpk 分析 / GU 建议 | FV-5 + FV-6 |
