# 项目现状与功能差异分析

更新时间：2026-08-17（本地仓库 HEAD `1ccc667`，分支 `master`）

---

## 1. 已完成的重构

### 1.1 后端拆分 ✅

`backend/index.js` 已拆分为独立模块：

- `routes/servers.js` — 服务器 CRUD + connect/disconnect
- `routes/tasks.js` — 任务 CRUD + SSH exec + running 状态注入（从 jobs 数组合并）
- `routes/files.js` — 远程文件浏览器
- `routes/data.js` — 模拟数据接口（sim-status / structure / cluster / trajectory / convergence）
- `routes/flows.js` — Flow 流水线管理 + `POST /:id/start` 顺序启动
- `routes/video.js` — VMD 视频渲染
- `routes/transition.js` — Transition 任务本地生成
- `store.js` — JSON 持久化存储
- `cache.js` — SWR 缓存 + 磁盘持久化
- `ssh.js` — SSH 会话管理

### 1.2 前端重构 ✅

组件按功能域拆分：

- `Dashboard/` — SimStatsCards / SimProgress / TimeEstimate / TemperatureTrace / ReplicaStatus / ConvergenceSection
- `Temperature/` — TemperaturePage / ReplicaSummary / ScheduleConfig / VisitExchange
- `Structure/` — TrajectoryTab / ReplicaGrid / RmsdChart / RgChart / E2eChart / SsChart
- `Cluster/` — ScatterPlot / ClusterTable / PiePopulation
- `Convergence/` — ConvergencePage / ConvergenceSummary / ReplicaDetails / BlockChart
- `TaskConfig/` — TaskCard / FlowBar / RunningTasksBar / FileBrowser / TaskTerminal / TransitionForm / CreateTaskForm / ServerManager

### 1.3 共享 Python 模块 ✅

`backend/_shared/` 包含：

- `ssh_client.py` — SSHClient（superset，支持 exec/upload/download/list）
- `task_config_base.py` — BaseTaskConfig + merge + write_default
- `sequence_annotation.py` — 肽链 motif 标注
- `routes/__init__.py` — make_dispatch 工厂函数
- `routes/files.py` / `routes/shell.py` / `routes/sequences.py` — 共享路由

tiger2 和 gromacs_cg 的 routes 变为薄 wrapper，转发到 `_shared`。

### 1.4 Flow 流水线系统 ✅

- Flow CRUD（创建/重命名/删除/任务归属）
- 任务 `next` 链：output → input 文件自动传递
- `POST /api/flows/:id/start`：按拓扑顺序启动，transition 任务自动等待完成
- RunningTasksBar：顶部运行中任务栏，脉冲动画，一键展开

### 1.5 Transition 任务 ✅

- `seq_to_pdb`：序列 → 延伸 PDB + annotation CSV + NAMD config（本地生成）
- `tiger2_dcd_to_gromacs_cg_pdb`：TIGER2 输出 → CG 输入 PDB + MDP 模板（本地生成）

---

## 2. 当前任务与服务器

### 任务

| ID | 名称 | taskType | 服务器 |
|---|---|---|---|
| `tiger2_legacy` | TIGER2 Legacy (Implicit GBIS, CPU) | tiger2 | iGEM Server |
| `tiger2_2ky5` | TIGER2 2KY5-SnoopyTag (100ns each replica) | tiger2 | iGEM Server |
| `tiger2_gpu` | TIGER2 GPU (OpenMM OpenCL, AMD RX 9070 XT) | tiger2 | iGEM Server |
| `tiger2_zju` | TIGER2 ZJU Remote (100ns each replica) | tiger2 | ZJU Remote |
| `gromacs_cg_zju` | GROMACS CG ZJU (positive control shear) | gromacs_cg | ZJU Remote |

### 服务器

| 名称 | 主机 | 认证 |
|---|---|---|
| iGEM Server | 127.0.0.1:22 | 密码 + conda startup |
| ZJU Remote | 192.0.2.20:20009 | SSH 私钥 |

---

## 3. 待办事项

- [ ] **ZJU NAMD 性能调优** — 当前 ZJU 上 NAMD3 运行在 CPU，需测试 GPU 加速
- [x] **GROMACS CG 启动** — `lib/launch.py`：自动 grompp + mdrun；有 sbatch 则提交，否则 setsid 脱离 SSH；二次存活检查与失败日志
- [ ] **Convergence 自动检测定时任务** — 定期运行 convergence-check，自动标记收敛/未收敛
- [ ] **多副本轨迹拼接** — gromacs_cg 多样本轨迹合并（接口已就绪，未启用）
- [ ] **user.md 文档更新** — 需与最新功能（Flow 流水线、RunningTasksBar、Transition 任务）对齐
- [ ] **清理遗留文件** — `backend/services/video.js`（重复）、`Dashboard/index.tsx`、`Convergence/index.tsx`（死代码）

---

## 4. Annotation 传递与 Flow 链

### 4.1 当前状态

Annotation 数据（蛋白质结构区域标注）已完整传递到 2KY-10 flow 中的4个任务：

| 任务 | taskType | Annotations | 来源 |
|---|---|---|---|
| task_msxcqeruutpe | seq_to_pdb | 13 | 原始创建时设置 |
| task_msxcr29y8je7 | tiger2 | 13 | 从 seq_to_pdb 复制 |
| task_msxcqesvfb2j | tiger2_dcd_to_gromacs_cg_pdb | 13 | 从 tiger2 复制 |
| task_msxcr2adecs0 | gromacs_cg | 13 | 从 tiger2_dcd_to_gromacs_cg_pdb 复制 |

13 个 annotation 区域：N-SnoopTag → N-linker → 9× SELP repeat → C-linker → C-SnoopTag

### 4.2 Flow 链结构

正确的 flow 顺序（按 createdAt）：

```
seq_to_pdb → tiger2 → tiger2_dcd_to_gromacs_cg_pdb → gromacs_cg
```

Flow links 通过 symlink 实现：
- `tasks/<id>/input/flow-<prevId>` → `tasks/<prevId>/output`

### 4.3 Task 创建时的模板提取

`POST /api/tasks/create` 时：
1. 从 `tasktype/<type>/task_config.template.json` 读取模板
2. 写入 `tasks/<id>/scripts/task_config.json`
3. 不覆盖已有文件（幂等操作）

模板包含 FILL-IN 占位符，需手动填写。

### 4.4 已知问题

- Annotation 不会自动从上游任务传递到下游任务（需手动复制或通过 API 更新）
- Flow 链顺序依赖 createdAt 时间戳，创建任务时需注意顺序
- tiger2_dcd_to_gromacs_cg_pdb 的 generate.py 不读取上游 annotation（annotation 仅用于前端显示）
