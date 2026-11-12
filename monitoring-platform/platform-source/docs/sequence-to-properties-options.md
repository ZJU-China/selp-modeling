# 序列 → 性质流水线:前端选项与测试

本文档汇总「从一条氨基酸序列得到水凝胶杨氏模量」整条链路上可调的前端选项、
配置键、CSV 契约,以及对应的后端 CLI 参数和测试程序。对应前端实现
`frontend/src/utils/crosslinkSites.ts` 与 `frontend/src/components/TaskConfig/TransitionForm.tsx`。

## 1. 前端流程概览

```
序列 ──▶ [前端] 交联位点选择 ──▶ [前端] 序列/位点标注 ──▶ [后端] seq_to_pdb
   ──▶ map_aa_to_cg ──▶ generate_32chain_candidates ──▶ rubber/force-balance ──▶ 杨氏模量
```

前端本身只负责「序列 → 交联位点 / 标注」;模量由后端 CG 脚本计算
(见 `docs/simulation-principles.md`)。

## 2. 前端算法选项 `selectCrosslinkSites()`

入口: `frontend/src/utils/crosslinkSites.ts`

| 参数 | 类型 | 默认 | 含义 |
|---|---|---|---|
| `targets` | `string[]` | (必填) | 目标残基 1-letter 码,大小写不敏感;空/非法字母被忽略。例: `["Y"]`(Tyr)、`["Y","C"]`(Tyr+Cys) |
| `maxCount` | `number` | 不限 | 保留位点数量上限 |
| `minSpacing` | `number` | `0` | 相邻保留位点的最小残基间距(≥1);`0` 表示不稀释 |
| `spread` | `boolean` | `false` | 按链长均匀分布(复现模板 core-Tyr 规则,每 ~51 aa 一个交联点) |
| `excludeTermini` | `number` | `0` | 仅与 `spread` 一起用:跳过距链端该范围内的残基 |

返回值 `CrosslinkSelection`:

| 字段 | 含义 |
|---|---|
| `sites[]` | `{ position(1-based), residue(1-letter), residueName(3-letter) }` |
| `csv` | 逗号分隔的 1-based 位点列表(供 UI/导入) |
| `summary` | 人类可读的汇总文本(数量、残基类型、位点) |

### 3. 表单可调项(仅 `seq_to_pdb` 任务类型)

`TransitionForm.tsx` 的 "Crosslink Sites" 区:

| 表单字段 | 保存到 config 键 | 说明 |
|---|---|---|
| Target Residues(1-letter) | `clxTargets` | 例: `Y`、`YC` |
| Max Sites | `clxMaxCount` | 保留上限 |
| Min Spacing (aa) | `clxSpacing` | 最小间距 |
| spread evenly along chain | `clxSpread` | 均匀分布开关 |
| (计算结果) | `clxSites` | `number[]`,1-based 位点 |

保存时(点击 **Save Form**)额外写入:

- config 的 `clxTargets/clxMaxCount/clxSpacing/clxSpread/clxSites`
- `input/annotations.csv`(标注行,格式同 `docs/sequence-annotation-workflow.md`)
- `input/crosslink_sites.csv`,仅当有选中位点:
  ```
  position,residue,residue_name
  49,Y,TYR
  ...
  ```

## 4. 后端 CLI 选项(序列 → 模量各阶段)

以下脚本的完整参数即该阶段的可调项:

| 阶段 | 脚本 | 关键选项(默认值) |
|---|---|---|
| 全流程编排 | `scripts/cg_autopilot.py` | `--sequence`(缺省=从模板 PDB 推导)、`--n-chains 32`、`--n-crosslinks 44`、`--seeds 3201 3202 3203`、`--temperature-k 310.0`、`--volume-nm3 23112.90`、`--skip-remote` |
| 序列 → AA PDB | `backend/tasktype/seq_to_pdb/generate.py` | `--task-id --local-dir --task-config` |
| AA → CG 映射 | `src/map_aa_to_cg.py` | `--input --output --expected-sequence`(校验 bead 数) |
| 网络生成 | `src/generate_32chain_candidates.py` | `--seeds --output --randomize-periodic-directions` |
| 橡胶模量 | `src/analyze_rubber_elasticity.py` | `--temperature-k 310.0 --volume-nm3 (必填) --actual-pairs --actual-base-periodic` |
| 单轴力平衡 | `src/analyze_uniaxial_force_balance.py` | `--temperature-k 310.0 --volume-nm3 (必填) --log-strains 0.005 0.01 0.02 --tile-shape 2 2 1 --chains-per-tile 8 --beads-per-chain 964` |

## 5. 测试程序

| 命令 | 覆盖范围 |
|---|---|
| `npm run test:crosslink` (`frontend/scripts/check-crosslink-sites.ts`) | 前端交联位点算法:检测、稀释、间距、spread 复现模板 core-Tyr 模式 |
| `npm run test:sequence` (`frontend/scripts/sequence-to-properties.test.ts`) | 整条链路:序列规范化 → 位点选择(全部模式)→ 序列化契约(config 键 + CSV)→ 与 CORE_TYR_SITES 交叉验证 → 后端 CG 链端到端模量 |
| `npm test` | 上述两者 |
| `python3 CG/.../tests/` (unittest) | CG 包内建单元测试 |

`test:sequence` 的第 5 节需要本地存在 CG 包与 `python3`,否则跳过并提示。
Node ≥ 22.6 即可直接运行 TS 测试(无需编译)。

## 6. 已知约束

- 网络生成器目前的交联位点表 `CORE_TYR_SITES` 与模板序列(564 aa, Tyr 间距
  51 aa)绑死;前端 `spread` 选出的位点与该表一致(见 `test:sequence` 第 4 节)。
  给定其它序列时位点选择是通用的,但生成器仍需支持从用户位点导入
  (见 `docs/feature-gap-analysis.md`)。
- 杨氏模量端到端验证依赖本机 CG 包与可执行后端脚本;远程 MD 需在 iGEM/ZJU 上运行。