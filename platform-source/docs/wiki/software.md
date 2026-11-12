# SELP 分子动力学模拟平台

> **页面定位**：本页是 **Flow Console**（新版前端）的**用户使用指南**，只讲"怎么用"。
> 建模方法、力场选择、粗粒化映射、力学模型等技术细节放在专门的 *Method / Model* 页面。
> 平台的开发历程（DBTL 工程设计）见 *Engineering* 页面。
>

---

## 概述

**SELP 分子动力学模拟平台**把一条原本需要手工串起来的分子模拟流程，做成了一个可以逐级查看、
逐级修改的**流水线（Flow）**。

一次完整的分析被拆成若干依次衔接的步骤：

| 步骤 | 任务类型 | 解决的问题 | 在界面中的名称 |
|---|---|---|---|
| 第一步 | `flow_tiger2` | 单体分子的空间结构 + CG 起点结构 | TIGER2 (all-atom MD → CG start) |
| 第二步 | `flow_gromacs_cg` | 粗粒化交联网络与杨氏模量 | GROMACS (coarse-grained) |
| 第三步 | `flow_magnetomech` | 整体力学性质（磁力学响应） | Magnetomechanics (composite + field) |

> **第一步同时完成全原子模拟与 DCD → CG 转换。**
> TIGER2 生成的是 NAMD 轨迹（DCD/coor/vel），GROMACS 读不了，必须先转成 CG 起点结构。
> 这个转换原本是一条独立的中间步骤，现在**并入第一步**：`flow_tiger2` 在拿到轨迹后
> 就地生成 `cg_start.pdb`、`cg_input.mdp` 与 `from-tiger2/`，CG 步骤直接从第一步取用。
> 合并不是把功能删掉，而是让链条少一个"没有 main.py、只能手工触发"的步骤。

每个步骤都在**同一个页面**上拥有自己的参数面板、运行按钮和结果图表。你不需要在多个页面之间
来回切换，也不需要手工拷贝文件——上一步的产物就是下一步的输入。

平台的核心设计是**参数驱动**：每一类步骤都把它的关键物理输入暴露成表单字段，你在网页上改
数值、保存、重跑，任务就会用新参数重新生成自己的输入文件。参数面板保存的是**你的意图**，
而不是生成好的中间文件，因此不会出现"改了参数但结果没变"的错位。

---

## 快速开始

1. 打开平台地址，进入 **Flow Console**。
2. 在 **Flows** 列表里找到你要用的流程，点击任意一行进入。
   - 如果列表为空，点击 **+ New flow** 新建一条（见下节），或点击右上角
     **Sync flow folders** 重新扫描流程目录。
3. 进入流程页后，先看顶部的**进度徽章**，确认上一次跑到了哪一步。
4. 切到 **Parameters** 标签页，从上到下逐个检查各步骤的参数。
5. 切到 **Control** 标签页，按步骤顺序点击 **Start**（第三步是 **Compute**）。
6. 切到 **Results** 标签页查看图表。

流程页面地址形如 `#/flow/<flow-id>`，每个标签页也有独立地址（例如
`#/flow/<flow-id>/parameters`），**可以直接把某个标签页的链接分享给别人**。

### 新建流程：+ New flow

**Flows** 列表标题右侧的 **+ New flow** 用于新建流程。展开后需要填两项：

| 字段 | 说明 |
|---|---|
| **Name** | 流程名称，之后可以用它找到这条流程 |
| **Template** | 步骤模板，决定这条流程包含哪些步骤以及它们的顺序 |
| **Server for the compute steps** | 仅当模板包含需要 SSH 的步骤时出现 |

可选模板：

| 模板 | 步骤顺序 | 适用场景 |
|---|---|---|
| **Empty flow** | 无 | 只想先建一条空流程，之后自己加步骤 |
| **TIGER2 (NAMD) single step** | TIGER2 | 只需要单次全原子模拟 |
| **TIGER2 → GROMACS CG** | TIGER2 → GROMACS CG | 全原子结果直接喂给粗粒化 |
| **Full chain: TIGER2 → CG → Magnetomechanics** | TIGER2 → GROMACS CG → Magnetomechanics | 完整链路，推荐 |

> 与旧模板不同，现在模板直接创建 **`flow_*` 类型的步骤**（`flow_tiger2`、
> `flow_gromacs_cg`、`flow_magnetomech`），而不是底层的裸类型。裸类型没有参数面板；
> 只有 `flow_*` 包装类型才能在这个页面上编辑参数。

选择 **Full chain** 时，面板会直接列出将要创建的步骤顺序，创建后即为此顺序。

> **步骤之间的数据衔接是自动完成的。**
> 创建时系统会同时写好每一步的产物到下一步输入的对应关系，
> 所以第一步算完后就地产出 CG 起点结构，第二步能读到构象，第三步能读到杨氏模量，
> 不需要手工配置任何文件路径。

> **本地步骤不会被分配服务器。**
> 第三步 Magnetomechanics 在后端本机运行，创建时它的 server 字段留空，
> 不会尝试建立 SSH 连接。（第一步的 DCD → CG 转换也在后端本机完成，但它属于需要
> 服务器的第一步，随该步骤一起执行。）

创建完成后会自动跳转到新流程页面。

### 建议的操作顺序

平台允许你任意顺序点击，但**第一次跑一条新流程时**，强烈建议按步骤顺序来：

```
Parameters（填第一步） → Control（Start 第一步） → 等第一步 Done
      → Parameters（填第二步） → Control（Start 第二步） → 等第二步 Done
            → Parameters（填第三步） → Control（Compute 第三步） → Results
```

原因是第二步的 CG 网络需要第一步的构象，第三步的复合模量需要第二步算出的杨氏模量。
虽然平台会在缺失输入时明确报错，但按顺序走可以避免无谓的失败尝试。

---

## 界面总览

### 顶部区域

进入流程后，顶部依次是：

- **返回按钮** `← All flows`，以及流程 ID（灰底等宽字体）。
- **流程名称**（大标题）。
- **一句话进度**：例如 `4 steps · 1 complete · currently at step 2`。
- **状态徽章**：`In progress` / `Step re-running` / `Complete`。
- **步骤徽章**：每个步骤一个，形如 `1. TIGER2 (all-atom MD)`，颜色反映该步骤的状态
  （灰=Pending，蓝=Running，绿=Done，红=Failed）。

页面每 **30 秒**自动刷新一次，也可以随时手动刷新。

### 四个区块标签

流程页主体是四个标签，**只有当前选中的那个会被加载**，所以切换标签不会同时触发三套图表查询：

| 标签 | 内容 |
|---|---|
| **Dashboard** | 整条流程的进度概览 |
| **Parameters** | 所有步骤的参数输入表单 |
| **Results** | 所有步骤的结果图表 |
| **Control** | 所有步骤的运行与视图按钮 |

### 步骤面板

Parameters、Results、Control 三个区块里，每个步骤都包在一个可折叠的面板中。面板标题栏从左到右：

**折叠箭头 ▸ → 步骤序号 → 步骤名称 → 步骤类型 → 结果摘要 → 百分比 → 状态徽章**

- 点击标题栏（或聚焦后按 `Enter` / `Space`）展开或折叠。
- Results 区块的面板**默认折叠**，标题栏上会显示一行摘要，例如
  `trajectory · structure (6) · temperature`，方便快速定位要看的内容。
- 展开后，面板顶部还有一行状态详情，包含状态文字和判定依据（`source:`）。

---

## Dashboard —— 流程进度

Dashboard 区块顶部有一个徽章，形如 `2 / 5 steps complete`，下方是进度卡片
（`FlowProgressCard`），展示每一步的完成情况与当前所在步骤。

它回答的问题只有一个：**这条流程走到哪了、下一步该做什么。**

---

## Parameters —— 参数输入

这是使用平台的主要区域。每个步骤各有一个参数面板，**从上到下依次排列**，
与流程顺序一致，因此从上往下填就是正确的执行顺序。

面板标题右侧有一个状态标记：

- 第一步显示序列长度，例如 `339 residues`；未填时显示 `no sequence yet`。
- 第三步显示水相占比，例如 `water 0.330`（这是自动算出来的，不用填）。
- 第二步不显示标记。

### 保存按钮

每个参数面板底部有两个按钮：

| 按钮 | 行为 |
|---|---|
| **Save** | 只保存参数，不触发运行 |
| **Save & restart** | 先保存，再用新参数重新生成输入并重启该步骤 |

**重要**：**第三步（磁力学）只有 `Save`，没有 `Save & restart`。**
因为它是本地一次性计算，没有"重启"的概念；它的运行按钮是 Control 区块里的 **Compute**，
每次点击都会用当前面板里的数值重新计算。

保存成功后，面板底部会显示提示文字：

- 第一步：`Saved. Restart the step to rebuild the structure and re-run TIGER2 from these values.`
- 第二步 / 第三步：`Saved. Restart the step to regenerate the run inputs from these values.`

点 **Save & restart** 则显示 `Saved and restarted.`。

**部分保存也是安全的**：只提交一两个字段不会把其它字段清空。后端会用该步骤当前已保存的
值填补未提交的字段，所以你随时可以只改其中一个数就保存。

> **为什么改了参数一定要重启？**
> 参数面板保存的是"你想要什么"，而不是"算出来是什么"。任务在每次启动时才用这些参数
> 重新生成自己的输入文件。所以只点 **Save** 不会改变已有结果——这是刻意设计的，
> 目的是避免出现"参数改了、结果却还是旧的"这种无法排查的情况。

---

### Where this step runs —— 运行位置

每个**需要 SSH 的步骤**（第一步、第二步）参数面板里有一个 **Where this step runs**
子面板，用来填运行部署位置，而不是科学参数：

| 字段 | 说明 |
|---|---|
| **Remote working directory** | 服务器上的绝对路径，例如 `/home/selp/igem-2026/MD/run1` |
| **Log / config prefix** | 该步骤 NAMD / GROMACS 日志与配置文件的前缀，例如 `job0` |

- 面板右侧的状态标注：都已填且合法时显示 `configured`，否则显示
  `needed before this step can start`。
- 新建的步骤这两个值是占位符（如 `FILL-IN: ...`），**必须改成真实路径才能启动**。
  占位符永远不会被当作真实目录写入命令，也永远不会被写回配置文件。

字段校验（保存即检查，不需等到运行）：

| 字段 | 拒绝条件 | 提示 |
|---|---|---|
| **Remote working directory** | 不是绝对路径 | `The remote working directory must be an absolute path, e.g. /home/selp/igem-2026/MD/run1` |
| **Remote working directory** | 含 shell 元字符（`; & \| \` $ < >` 等） | `The remote working directory contains characters that are not allowed in a path.` |
| **Log / config prefix** | 含字母数字、点、横线、下划线以外的字符 | `The log prefix may only contain letters, digits, dot, dash and underscore.` |

> **为什么要单独一个子面板？**
> 这两个值会被拼进远端 shell 命令，而且它们是"跑到哪/写到哪"的部署决策，不是物理参数——
> 用一个**绝对路径**就杜绝了"相对路径在某个未知工作目录下解析"的问题，
> 用一个**严格字符集**的 prefix 就保证了拼进 shell 命令时不可能执行别的命令。

---

### 第一步：单体的空间结构（TIGER2 全原子分子动力学）

面板标题：**Sequence & annotation input**

#### 输入字段

| 字段 | 说明 |
|---|---|
| **Protein** | 蛋白名称，仅作标识用，例如 `2KY10 SELP (339 aa)` |
| **Amino-acid sequence** | 一字母氨基酸序列，在多行文本框中输入。面板会实时显示残基数 |
| **PSF topology** | PSF 拓扑文件名，例如 `protein.psf`。它由远端主机生成并放入该步骤的 `input/`，NAMD 启动前必须存在 |

序列支持的标准氨基酸代码会被自动识别；输入非法代码时，面板下方立即出现提示：

> `Unsupported amino-acid code(s): X, Z`

留空序列时保存会被拒绝：`Sequence is required`。

#### Motif annotations（motif 标注）

序列面板下方是 **Motif annotations** 子面板，作用是**在轨迹查看器里把每一个 motif 的出现位置
高亮出来**。表格包含四列：

| 列 | 说明 |
|---|---|
| **Label** | 备注名，留空时默认使用 motif 本身 |
| **Motif** | 要高亮的氨基酸片段 |
| **Matches** | 该 motif 在当前序列中出现的次数 |
| **Color** | 高亮颜色（十六进制，如 `#4c8bf5`），留空时自动配色 |

- 点 **Add motif** 增加一行，点每行末尾的 **Remove** 删除该行。
- 一行都不填时，面板提示 `No motifs. The trajectory will render without highlight regions.`
  ——轨迹仍然可以正常显示，只是没有高亮区域。

有两类输入会被**当场拒绝**，而不是留到跑完才失败：

- motif 在序列中根本不出现：
  `Annotation 1 ("ACDEF") does not occur in the sequence`
- 颜色不是合法的十六进制值：
  `Annotation 1: "blue" is not a hex colour`

这样可以避免出现"表格填了但界面上什么也没高亮"的状况——那种情况看起来像是查看器坏了。

#### Derive sequence from an existing structure（从已有结构反推序列）

如果你手上已有一个 PDB 结构（比如上游步骤产出的），这个子面板可以**从该结构反推出氨基酸序列**，
省去手工录入：

1. 在下拉框中选择同一条流程里的另一个步骤。
2. 点 **Derive**（读取中显示 `Reading…`）。
3. 读取成功后，如果结构包含多条链，会出现 `Use chain A (339 aa)` 这样的按钮，任选一条填入。
4. 再点 **Save & restart**。

面板会明确提示这一步的边界：

> `This recovers the sequence only. Saving and restarting rebuilds a fresh extended chain from it — not the original folded structure.`

也就是说，它恢复的是**序列**，不是原始折叠构象。

如果流程里没有其他步骤可读，面板显示 `No other step in this flow to read a structure from.`

---

### 第二步：粗粒化交联与杨氏模量（GROMACS）

面板标题：**CG network & deformation input**

#### 输入字段

| 字段 | 单位 | 说明 |
|---|---|---|
| **System** | — | 体系名称，例如 `2KY10 SELP CG network` |
| **Crosslinks** | 条 | 周期性 CG 网络中的交联边数量 |
| **Chains** | 条 | 网络中的链数 |
| **Temperature** | K | 写入 GROMACS mdp 的恒温器参考温度 |
| **Stretch** | ε | 沿各轴采样的轴向 Hencky 应变，逗号分隔，例如 `0.05,0.10` |
| **Replicas** | 个 | 副本数 |
| **Steps / cycle** | 步 | 每个循环的步数 |
| **Cycles** | 个 | 循环总数 |

#### 交联密度提示

**Crosslinks** 字段下方会实时显示一个派生量——**每条链的交联数**，例如
`1.375 crosslinks per chain`，并附一句说明：

> `this is the crosslink density the network is prepared to match.`

这是填参时最有用的一个实时反馈：它在你输入时就更新，让你在调整交联数时立刻看到网络密度
是否达到了目标区间，而不必跑完整个模拟才知道。只有当 **Crosslinks** 与 **Chains** 都大于 0 时
才会显示。

#### 关于杨氏模量的结果

第二步算出的橡胶弹性汇总（包含杨氏模量）会写入该步骤的分析输出目录，
同时出现在步骤的 `output/` 中：

```
tasks/<step-id>/cache/analysis/rubber_elasticity_summary.json
tasks/<step-id>/output/rubber_elasticity_summary.json
```

该文件同时给出多个网络模型下的估计值，便于横向比较。第三步会自动读取它，
**不需要你手工填写杨氏模量**。

> 如果第二步的 Results 区块里没有出现模量曲线，说明该步骤的分析尚未跑完。
> 请先在 Control 区块点击 **Start**，等待步骤状态变为 **Done**。

#### 输入校验

以下情况会在保存时被拒绝，并给出明确原因：

| 字段 | 拒绝条件 | 提示 |
|---|---|---|
| **Stretch** | 不是数字 | `Stretch: "abc" is not a number` |
| **Stretch** | 小于或等于 0 | `Stretch strains must be greater than 0` |
| **Stretch** | 大于 1（100%） | `Stretch strains must be 1 (100%) or less` |
| **Temperature** | 低于 10 K | 温度必须为正值模拟 |
| **Chains** | 小于 1，或非整数 | — |
| **Steps / cycle**、**Cycles** | 小于 1，或非整数 | — |

**Stretch 必须用英文逗号分隔**，且不要带单位符号；面板上的 `ε` 只是单位提示，不需要输入。

---

### 第三步：整体力学性质（磁力学）

面板标题：**Polymer & nanoparticle fractions, applied field**

#### 体积分数

| 字段 | 说明 |
|---|---|
| **Polymer fraction** | 聚合物骨架的体积分数 |
| **Nanoparticle fraction** | 磁性颗粒的体积分数 |

**这两个分数相加不能超过 1。** 面板下方会实时显示组成校验：

```
Solid phases 0.6700 + water 0.3300 = 1.0000. Water is the remainder and is set for you.
```

也就是说**水相占比不需要你填**，它由平台自动算出并写入，保证四个相加起来恒等于 1。
如果两个分数加起来超过 1，面板会变红警告：

```
These fractions add up to 1.8500, leaving -0.8500 for water. Their sum must not exceed 1.
```

此时保存会被拒绝，错误定位到 **Nanoparticle fraction** 字段。

#### 外加磁场

| 字段 | 出现条件 | 说明 |
|---|---|---|
| **Field mode** | 始终 | 下拉选择：`Uniform` / `Gradient` / `From file` |
| **Base field** (T) | Uniform、Gradient | 样品起始端的磁场强度 |
| **Field rise** (T) | Gradient | 沿样品高度方向磁场的**增量** |
| **Sample height** (mm) | 始终 | 样品高度 |
| **Profile points** | 始终 | 沿高度方向的采样点数 |

> **关于 Gradient 的方向**：在 Gradient 模式下，磁场从 **Base field** 出发，沿样品高度
> **线性上升** Field rise。因此剖面的峰值等于 `Base field + Field rise`。
> 若你想要的是一个恒定磁场，请选 **Uniform**。

#### 从文件导入磁场剖面（From file）

把 **Field mode** 切换为 `From file` 后，面板下方会出现一个文件槽：

- **Upload** — 选择本地 CSV 文件上传到该步骤的 `input/` 目录。
- **Download** — 把当前已上传的文件下载回本地。

上传完成后会显示：

```
Uploaded field_profile.csv (1.2 kB) to input/field_profile.csv. Save to attach it to the run.
```

注意 **Upload 和 Save 是两步**：上传只是把文件放进目录，点 **Save** 才会把它关联到本次运行。

##### CSV 格式要求

CSV 首行必须是表头，且包含**一个位置列**和**一个磁场列**：

| 列 | 可接受名称 | 单位 |
|---|---|---|
| 位置 | `z` 或 `x` | 米 |
| 位置 | `z_mm`、`x_mm`、`position_mm` | 毫米 |
| 磁场 | `b` | 特斯拉 (T) |
| 磁场 | `h` | 安培/米 (A/m) |

示例：

```csv
z_mm,b
0,0.0
2,0.2
4,0.4
6,0.6
8,0.8
10,1.0
```

> **单位必须明确。** 裸列名 `z` / `x` 一律按**米**解释，`_mm` 结尾的按**毫米**解释。
> 这是平台刻意的设计：把毫米当成米曾经导致磁场被读成接近零，而且很难察觉。
> 如果你确实想用毫米，请写 `z_mm`。

以下情况会在保存时被拒绝，并告诉你实际找到了哪些列：

| 情况 | 提示 |
|---|---|
| 文件为空 | `The field file is empty.` |
| 没有位置列 | `The field file needs a position column named z or x (metres) or z_mm (millimetres). Columns found: ...` |
| 没有磁场列 | `The field file needs a field column named b or h. Columns found: ...` |
| 位置没有覆盖样品高度 | `The field file positions span 0.0000..4.0000 mm, which does not cover the sample (0..10 mm); a profile taken from another origin cannot be applied to this sample.` |
| 位置范围远超样品高度 | `The field file positions span ... but the sample is only 10 mm tall, so the applied profile would be wrong. Rename the column to z_mm if these values are millimetres.` |

后两条尤其重要，因为它们各自对应一种**不会报错、只会给出错误结果**的失败模式：

- 位置区间**够不到**样品高度时，剖面会被截断并贴住最近一端——磁场退化成一条常数线。
- 位置区间**远超**样品高度时，只有靠近原点的那几行落在样品内——这正是"毫米被当成米"的表现。

平台选择在保存时就把这两种情况拦下来，并顺带提示你检查单位，
而不是让你跑完看到一张接近零的图再回头猜。

---

## Control —— 运行与视图

Control 区块为每个步骤提供一组按钮，分为两行。

### Run（运行）

按钮因步骤类型而异：

| 步骤 | 按钮 | 说明 |
|---|---|---|
| 第一步 TIGER2 | **Start** / **Stop** / **Restart** / **Pause** / **Continue** | 全原子分子动力学的启动、停止、重启、暂停与继续（轨迹就绪后顺带生成 CG 起点结构） |
| 第二步 GROMACS | **Start** / **Stop** / **Restart** / **Pause** / **Continue** | CG 模拟的启动、停止、重启、暂停与继续 |
| 第三步 磁力学 | **Compute** | 本地一次性计算，秒级返回 |

> **现在第二步可以在应用内直接启动。**
> 过去 CG 步骤只能给你一条 "launch with sbatch on the cluster" 的提示，让你去服务器上手工
> 提交作业。现在的 **Start / Restart** 会真正在应用内完成 `grompp` + `mdrun` 的启动：
>
> - 服务器上有 SLURM（如 ZJU 集群）：自动写好批处理脚本并用 `sbatch` 提交，
>   返回作业号 (`jobId`)。
> - 服务器上没有 SLURM（如 iGEM 服务器）：用 `setsid` 分离启动，让模拟在 SSH 断开后
>   继续运行。
>
> 启动后会做两次存活检查：第一次确认进程真的起来了，第二次排除"刚起来就死在坏的 tpr 上"
> 的情况。一个**很快跑完的冒烟测试**同样算成功（`completed: true`），不会被误报成失败。

> **第三步只有 Compute，没有 Start/Stop/Pause。**
> 这一步在你的浏览器之外立刻算完并返回结果图，所以不需要"启动"和"停止"的概念。
> 点击 **Compute** 即从头重新计算一次。

#### Pause 与 Continue 的实际行为

**Pause 会真的让模拟停下来**，而不是仅仅禁止自动重启：

| 步骤 | 实现方式 | 效果 |
|---|---|---|
| 第一步 TIGER2 | 向远端 NAMD 进程发送 `SIGSTOP` | 进程挂起，不再消耗 CPU；已积累的状态完整保留 |
| 第二步 GROMACS | `scontrol suspend`（SLURM 集群）；无 SLURM 时对进程发信号 | 作业在调度器层面挂起 |
| 恢复 | `SIGCONT` / `scontrol resume` | 从暂停处继续，不重新计算 |

> **GROMACS 为什么用 `scontrol` 而不是直接停进程？**
> CG 模拟通常运行在 SLURM 集群的计算节点上。直接对登录节点上的进程发信号既找不到作业，
> 也会出现"模拟已冻结但 SLURM 仍显示 RUNNING"的矛盾状态。

> **如果模拟本来就没在运行，按 Pause 会明确提示。**
> 例如返回 `No running NAMD process matched ... so STOP did nothing.`，
> 而不是假装暂停成功。这样可以区分"没有任务在跑"和"已成功暂停"。

点击后按钮上会短暂显示进行中的状态（例如 `Start…`），完成后在面板下方给出反馈：

- 成功：`Accepted — OK`
- 失败：`Failed — <后端返回的具体原因>`

> **为什么参数面板的按钮和 Control 区块的按钮要分开？**
> Parameters 负责"改参数"，Control 负责"运行"。这样你可以先把各步骤的参数都填好、
> 依次保存，再统一按顺序启动，而不会因为改一个参数就立刻触发一次长时间计算。

### View（视图）

View 行里的按钮用于**跳到 Results 区块中对应的结果标签**，无需离开当前页面：

| 步骤 | 按钮 | 对应的 Results 标签 |
|---|---|---|
| 第一步 | **Temperature** / **Convergence** / **Structure** | Temperature / Convergence / Structure |
| 第二步 | **Structure** | Structure |
| 第三步 | **Field deformation** | Field & deformation |

若某一步没有可用的控制项，面板显示 `No controls for this step type.`

面板底部还会显示该步骤的工作目录：

```
Working directory: /home/selp/igem-2026/igem-2026-software/backend/tasks/<step-id>
```

本地运行的步骤（第三步 Magnetomechanics）旁边会额外标注 `runs locally on the backend host`。

### Execution —— 运行环境

Control 面板下方是 **Execution** 面板，回答"这一步到底在哪里跑、数据在哪、
外部程序怎么调用"。右上角的标签标明运行方式：

| 标签 | 含义 |
|---|---|
| `local` | 在后端所在机器上直接运行，不建立 SSH 连接 |
| `ssh` | 通过 SSH 连到指定服务器执行 |
| `unresolved` | 该任务没有配置服务器，运行前需要先配置 |

面板列出以下内容：

| 行 | 说明 |
|---|---|
| **Runs on** | 实际执行位置。本地任务显示 `Runs on this machine (no SSH)`；远程任务显示 `SSH to selp@127.0.0.1:22` |
| **NAMD** | 该服务器配置的 NAMD 可执行文件（仅 TIGER2 步骤） |
| **Input** / **Output** | 该步骤的本地输入与输出目录 |
| **Remote dir** | 远端工作目录（仅 SSH 任务） |
| **gmx** / **matlab** | 外部程序的调用方式与解析结果 |

> **NAMD 的实际路径在启动时解析。**
> 面板显示的是服务器配置里的 NAMD 值；真正启动 NAMD 时，后端会在远端优先使用配置值，
> 配置为空则自动探测已安装的 NAMD 构建目录。探测结果会随启动结果一起返回。

#### 外部程序（gmx / matlab）

每个程序会显示**实际生效的调用命令**：

| 显示 | 含义 |
|---|---|
| `gmx` → `/usr/bin/gmx` | 通过名字调用，已在 PATH 中找到（箭头后是解析结果） |
| `docker exec matlab-gui matlab` `in container` | 在容器内调用 |
| 红色显示 + `— is not on PATH` / `does not exist` | **该程序当前不可用**，配置需要修正 |

> **为什么值得看这一行？**
> `gmx` 和 `matlab` 经常不在 PATH 上，或者装在非标准路径。配置错误以前只会在
> 等完一次运行之后才以"运行失败"的形式暴露出来；现在在运行之前就能看到。

---

## Results —— 结果查看

Results 区块为每个步骤按**结果类别**分组。该步骤实际产出了哪些结果，就只显示哪些标签——
未完成的步骤只会给出一份简短、诚实的清单，而不是一排空面板。

可能的标签有五个：

| 标签 | 内容 | 适用步骤 |
|---|---|---|
| **Trajectory** | 3D 轨迹动画，可选择副本 | 有轨迹输出的步骤 |
| **Structure** | 结构分析图表 | 第一步、第二步 |
| **Convergence** | 收敛检测 | 仅第一步 |
| **Temperature** | 温度交换详情 | 仅第一步 |
| **Field & deformation** | 磁力学场量图 | 仅第三步 |

步骤还没有产出任何结果时，面板显示：

```
No result artefacts yet for this step. Analysis output appears under
tasks/<step-id>/cache/analysis/ once the step has run.
```

### Structure —— 结构分析

根据该步骤实际生成的数据，图表会自动增减：

- **Radius of gyration**（回旋半径，Å）
- **End-to-end distance**（端到端距离，Å）
- **RMSD**（均方根偏差，Å）
- **Secondary structure**（二级结构含量，%）
- **Per-chain Rg**（每条链的回旋半径，Å）
- **Energy**（能量，kJ/mol）
- **Box vectors**（模拟盒矢量，nm）
- **Crosslinks**（交联数，随帧变化）

### Convergence —— 收敛检测

以表格形式列出各收敛判据的通过情况，用 `✓` / `✗` 标注，右侧给出整体判定徽章
（`All replicas pass` 或 `3/4 pass`）。

### Temperature —— 温度交换

**固定温度运行的步骤不适用。** 例如第二步会明确提示：

```
This step runs at a fixed temperature (310 K, no replica exchange),
so temperature-exchange analysis is not applicable.
```

### Field & deformation —— 场量图

第三步的结果页分为两部分：

1. **一张主结果图**，图注为 `Computed deformation under the applied field`——
   外加磁场下计算得到的形变。
2. **六张场量图组成的网格**：

| 图 | 含义 |
|---|---|
| **Local axial modulus** | 局部轴向模量 |
| **Displacement field** | 位移场 |
| **Axial strain** | 轴向应变 |
| **Pore pressure** | 孔隙压力 |
| **Axial stress** | 轴向应力 |
| **Applied field** | 外加磁场 |

---

## 常见问题与提示

### 面板显示"This panel is read-only: the step has no task id."

该步骤还没有被分配任务 ID，因此参数面板只能查看、不能编辑。确认流程中的步骤已正确关联到
任务后再操作。

### 保存后提示 "needed before this step can start"

第一步 / 第二步的 **Where this step runs** 子面板还没有填好。补上
**Remote working directory**（绝对路径）和 **Log / config prefix** 并保存，
子面板状态会变成 `configured`，这一步才能启动。

### 我改了参数，结果没变

这是**预期行为**。参数面板保存的是输入意图，必须让步骤重新运行才会生效：

- 第一步、第二步：点 **Save & restart**，或在 Control 里点 **Restart**。
- 第三步：点 **Save**，然后在 Control 里点 **Compute**。

### 保存后提示我重启，但我不想重跑

只点 **Save** 即可。参数已经保存，等你准备好再重启。

### 步骤状态一直是 Failed

展开该步骤面板，标题栏下方会显示状态详情和 `source:`（判定依据）。控制区的按钮下方也会
显示 `Failed — <具体原因>`。这两处通常直接给出可操作的信息。

### 第二步的模量结果在哪里

见上文[「关于杨氏模量的结果」](#关于杨氏模量的结果)：在步骤的
`cache/analysis/rubber_elasticity_summary.json` 与 `output/` 中，并且会自动被第三步读取。

### CG 步骤能不能不通过应用、直接在服务器上跑

可以，但没必要。如果在 iGEM 服务器（无 SLURM）上，应用内 **Start** 就等价于
`setsid gmx mdrun` 的分离启动；如果在 ZJU 集群上，应用内 **Start** 会自动
`sbatch`。两种方式都会在 `{deffnm}_run.sh`（SLURM）或 `{deffnm}_submit.log`（setsid）
里留下提交记录。

### 交叉链接的流程页面过期了

流程页地址就是它的 URL，直接复制地址栏即可。每个标签页也有独立地址。

---

## 步骤之间的数据传递与集成

平台内部通过**步骤产物 + 任务配置**在阶段间传递数据，用户不需要手工搬运文件：

```
第一步  序列 → 全原子轨迹 + CG 起点结构（cg_start.pdb + cg_input.mdp + from-tiger2/）
          │  产物
          ▼
第二步  CG 交联网络 + 杨氏模量 (rubber_elasticity_summary.json)
          │  产物
          ▼
第三步  复合模量 + 磁力学响应
```

DCD → CG 转换（并入第一步）产出三种东西：CG 起点结构 `cg_start.pdb`、`cg_input.mdp`，
以及一个 `from-tiger2/` 目录（存放转换明细）。`cg_start.pdb` 与 `cg_input.mdp` 就是第二步
GROMACS 的 `grompp` 输入。转换读的是第一步自己落盘的全原子轨迹；轨迹经同步（或轨迹查看器
下载）出现在第一步的 `output/` 或 `cache/trajectory/` 后，转换会随之重新生成这些文件。

平台也提供几个明确的对外接口，便于与其他工具或自动化流程对接：

| 能力 | 说明 |
|---|---|
| **文件上传 / 下载** | 第三步的磁场剖面 CSV 可在面板内上传与下载，便于与实验测量数据交换 |
| **结构反推序列** | `Derive` 子面板可从同流程内任意步骤的结构反推序列 |
| **REST API** | 后端提供 `/api/flows`、`/api/tasks`、`/api/data/*` 等接口，前端使用的每一个操作都是一次 API 调用，可直接用于脚本化或批量处理 |
| **整链启动** | `POST /api/flows/:id/start` 会按创建顺序自动启动整条链：第一步算出轨迹并就地生成 CG 起点结构后，再把产物拷给下一步。若某步仍在运行，则停止并报告 `waiting`（等它算完再点一次即可继续），不会把空输入传给下游 |
| **源文件位置透明** | 每个步骤的工作目录都显示在 Control 面板底部，分析产物路径显示在 Results 空状态提示中，便于直接取数做后处理 |

---

## 架构概览

平台采用**前端 / 后端 / 计算**三层结构：

```
┌────────────────────┐   /api/*   ┌─────────────────┐   SSH    ┌─────────────────────┐
│  Flow Console      │ ─────────▶ │  Express 后端   │ ───────▶ │  远程计算服务器      │
│  (React + Vite)    │   proxy    │                 │          │  NAMD / GROMACS      │
└────────────────────┘            └─────────────────┘          └─────────────────────┘
                                            │
                                            └── 本地计算：第一步的 DCD → CG 转换 + 磁力学
```

- **前端**：React + Vite，端口 5174。界面按流程组织，而非按单个任务组织。
  四个区块共用同一份流程概览数据，因此切换标签不会重复发起图表查询。
- **后端**：Express，端口 3001。路由层（`routes/`）与业务逻辑层（`services/`）分离。
- **计算**：第一、二步的模拟在远程服务器上执行（通过 SSH 连接，使用密钥认证）；
  第一步附带的 DCD → CG 转换与第三步在后端主机本地完成——前者是秒级的轨迹格式转换，
  后者是一次数值计算。
- **任务类型插件化**：新增一类步骤只需要在后端注册任务类型与参数模板，
  前端会自动为它生成对应的参数面板和运行控件，无需改动前端代码。

> 详细的架构说明、参数含义与建模方法，请参见项目的 *Method* 与 *Software Architecture* 页面。

---

## 设计取舍

在设计过程中，我们对几个关键点做了取舍，这些选择直接影响了你日常的使用方式：

**1. 参数驱动，而不是文件驱动。**
我们选择让用户修改表单参数、由任务自动生成输入文件，而不是让用户手工准备拓扑和配置文件。
代价是重启步骤时会多花一点时间重新生成输入；换来的是**参数与结果永远一致**——
不存在"改了配置文件但任务仍读旧文件"的情况。

**2. 只有一个页面，而不是每个任务一个页面。**
流程天然是有顺序的，把步骤放在同一页面上，用户能看到整体进度，
也不用在多个标签之间来回切换。代价是单页信息密度更高，因此我们用可折叠面板来保持可读性。

**3. 立即校验，而不是跑完再报错。**
非法序列、不存在的 motif、超过 100% 的应变、加起来超过 1 的体积分数、
单位错误的磁场文件、**不是绝对路径的 remoteDir**、**含非法字符的 logPrefix**——
这些都在**点保存的那一瞬间**报错，并指出是哪个字段。
代价是校验规则需要持续维护；换来的是用户不必等待几小时的计算才发现输入有问题。

**4. 磁力学本地计算，而不是占用集群。**
这一步是秒级的数值计算，提交到集群的排队时间反而远大于计算本身。
代价是它不享受集群的算力；换来的是交互式的即时反馈。

**5. 磁场剖面的单位必须明确。**
平台把裸列名 `z` / `x` 严格解释为米，毫米必须写 `_mm`。
这是为了避免"毫米被当成米"这种**几乎不可能从结果本身发现**的错误——
如果放行，磁场会退化成接近零的值，而结果看上去仍然像一个正常的图。

**6. 运行位置单独成子面板，且用绝对路径。**
`remoteDir` 和 `logPrefix` 是部署决策而不是物理参数，放在参数面板里会跟科学参数混在一起，
也更容易被写成相对路径。把它单列成一个 **Where this step runs** 子面板、
强制绝对路径、限制 prefix 字符集，就杜绝了"相对路径在未知目录下解析"和
"路径里夹带 shell 命令"这两类问题。

---

## 安装与部署

平台由前端与后端两部分组成，部署步骤：

1. **获取代码**

   ```bash
   git clone <repository-url>
   cd igem-2026-software
   ```

2. **后端依赖**

   ```bash
   cd backend
   npm install
   ```

3. **前端依赖**

   ```bash
   cd frontend
   npm install
   ```

4. **启动后端**（默认端口 3001）

   ```bash
   cd backend
   npm start
   ```

5. **启动前端**（默认端口 5174，`/api` 自动代理到 3001）

   ```bash
   cd frontend
   npm run dev
   ```

6. 在浏览器中打开前端地址即可。

远程计算服务器与本地集群的连接信息集中登记在后端的服务器配置文件中，
使用 SSH 密钥认证；密钥不在代码仓库中，需要单独配置。

> 环境准备、服务器注册、任务创建与参数参考等更详细的技术文档，见项目仓库中的
> `docs/` 目录。

---

## 仓库与许可

| 项目 | 内容 |
|---|---|
| **代码仓库** | `<!-- 填写 GitLab 仓库地址 -->` |
| **开源许可** | `<!-- 填写许可证名称与链接，如 MIT / Apache-2.0 / BSD-3-Clause -->` |
| **后端服务** | Express (Node.js) |
| **前端服务** | React + Vite (TypeScript) |
| **科学计算** | `<!-- 填写模拟与分析所用的主要软件/语言，如 NAMD、GROMACS、Python/MATLAB -->` |

---

## 致谢

`<!-- 填写致谢：指导老师、合作团队、服务器与集群支持、开源项目贡献者等 -->`