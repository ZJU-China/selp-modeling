# iGEM 2026 — Molecular Dynamics Platform

Molecular Dynamics Platform — simulation monitoring and analysis：通过 SSH 从远程计算服务器拉取数据，在浏览器中实时展示模拟进度、温度交换、结构轨迹与构象聚类。后端按任务类型（TIGER2 / GROMACS CG）插件化分发，页面随任务类型自动调整。

## 架构

```
┌────────────────┐   /api/*   ┌─────────────────┐   SSH    ┌─────────────────────┐
│  Vite 前端      │ ─────────▶ │  Express 后端    │ ───────▶ │  远程计算服务器       │
│  :5174          │   proxy    │  :3001           │          │  iGEM 127.0.0.1 │
└────────────────┘            └─────────────────┘          │  ZJU  192.0.2.20  │
                                                           └─────────────────────┘
```

- **前端**：React 19 + Recharts 2 + NGL.js（3D 轨迹渲染）+ Vite（Flow Console，:5174），`/api` 代理到后端
- **后端**：Express (:3001)，`routes/*.js`（HTTP 路由）与 `services/*.js`（业务逻辑）分离，SSH ControlMaster 连接，5min TTL 缓存
- **远程**：iGEM 本地服务器（密码认证）+ 浙大集群（SSH 私钥认证），注册于 `backend/servers.json`

## 任务类型（插件化）

任务类型在前后端分别注册，`App.tsx` 按 `taskType` 分发导航与页面组合，不适用页面自动隐藏：

| taskType | 说明 | 导航页 |
|---|---|---|
| `tiger2` | 全原子 TIGER2 副本交换 | Dashboard / Convergence / Temperature / Structure / Clustering / Task Control |
| `tiger2-convergence` | TIGER2 变体（聚焦收敛检测） | 同上 |
| `gromacs_cg` | GROMACS 粗粒化（Martini） | Dashboard / Structure / Task Control |
| `seq_to_pdb` | Transition：序列 → 延伸 PDB（本地生成） | Task Control only |
| `tiger2_dcd_to_gromacs_cg_pdb` | Transition：TIGER2 输出 → CG 输入（本地生成） | Task Control only |

- 后端：`backend/tasktype/<type>/{main.py, lib/, analyze.py, gen_sim_status.py, routes/}`
- 前端：`frontend/src/flow/`（流程式界面：Dashboard / Parameters / Results / Control）与 `frontend/src/components/`；`frontend/src/types.ts` 定义类型
- 任务注册：`backend/tasks.json`（连接信息 + taskType）＋ `backend/tasks/<id>/`（input/scripts/logs/cache/output），详见 `docs/task-creation.md`

## 页面总览

### 1. Dashboard（总览）

| 图表/组件 | 说明 | 数据来源 |
|---|---|---|
| 进度统计卡片 | 当前步骤、已完成周期、每副本时间、总进度% | `/api/data/sim-status` |
| 进度条 | 0–100%，运行/暂停/停止状态标签 | `avg_progress_pct` |
| 温度轨迹 | 各副本温度随模拟步数变化 | `mergeTempTraces(replicas)` |
| 温度访问分布 | 各温度区间停留时间分布 | `temp_visit_counts` |
| 副本状态表 | 周期数、平均温度、交换次数、能量 | `replicas` |
| 时间估算卡片 | 已用/剩余时间、总交换次数、时间步 | `wall_time_s` 等 |
| 系统配置表 | 蛋白、力场、溶剂、HMR、时间步 | `config.*` |
| 轨迹预览 | 最近一段时间的 3D 轨迹动画 | `dcd-last100` / `dcd-preview` |

GROMACS CG 任务显示 "GROMACS CG (Martini)" 类文案，时间步换算不再硬编码 4fs，不适用项自动隐藏。

### 2. Convergence（收敛检测）

分块展示每个副本最近一段时间窗口的端到端距离、回旋半径是否趋于稳定，并给出是否达到收敛标准的判断（`/api/data/convergence`，10min 缓存）。仅 TIGER2 类任务适用；GROMACS CG 显示"不适用于该任务类型"。

### 3. Temperature（温度交换详情）

仅 TIGER2：副本平均温度、全量温度轨迹（点击图例可高亮单副本）、各温度层访问次数、交换次数、温度调度配置。

### 4. Structure（结构分析）

| Tab | 内容 | 数据来源 |
|---|---|---|
| MD Trajectory | NGL.js 3D 轨迹播放（cartoon/stick/sphere/line），副本切换，序列高亮标注，MP4/GIF 导出 | `/api/data/dcd-preview/:filename`、`/api/data/dcd-file/:filename`、`/api/data/sequence-annotations`、`/api/video/*` |
| Radius of Gyration | 回旋半径随帧数变化 + Mean/Min/Max | `/api/data/structure`（`analysis/rg.dat`） |
| End-to-End Distance | 端到端距离 | `analysis/e2e.dat` |
| RMSD | 均方根偏差 | `analysis/rmsd.dat` |
| Secondary Structure | α-螺旋/β-折叠/无规卷曲比例 | DSSP 分析 |

### 5. Cluster（构象聚类）

KMeans（scikit-learn）+ silhouette 自动选 k：聚类占比饼图、Rg–E2E 散点（点击图例过滤）、肘部法、silhouette 评分、聚类详情表。

### 6. Task Control（任务管理）

RunningTasksBar（顶部运行中任务栏，脉冲动画）→ 运行中任务一键展开。任务卡片支持启动/停止、远程文件浏览器、SSH 终端、Flow 流水线管理（创建/重命名/删除/选择），任务间通过 `next` 链接自动传递 output→input，`POST /api/flows/:id/start` 一键顺序启动整个流水线。Transition 任务（`seq_to_pdb`、`tiger2_dcd_to_gromacs_cg_pdb`）本地生成输入文件，无需远程服务器。

## 轨迹数据与缓存

后端不直接访问远程轨迹文件：统一由任务自身的 `main.py route trajectory`（`runMain`）完成远程发现与下载（XTC→DCD 转换），后端只写缓存与状态。轨迹目录：

```
backend/tasks/<id>/cache/trajectory/
├── topology.pdb              # 与 DCD 原子顺序一致的拓扑（查看器用）
├── replica_<n>.dcd           # 每个副本的完整轨迹
├── preview/replica_<n>.dcd   # 抽稀预览（浏览器快速加载）
├── last100/replica_<n>.dcd   # 最近 ~100 帧尾段
├── meta.json                 # samples / previewFrames / last100Frames
└── status.json               # 同步状态（见下）
```

`status.json` 字段：`pdbSize, dcdSize, dcdSizes, previewSizes, previewFrames, samples, replicaSizes, last100Sizes, last100Frames`。`dcdSizes / samples / previewSizes` 为多副本（多 DCD）预留。

相关接口：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/data/trajectory-status?taskId=` | 读取同步状态 |
| POST | `/api/data/trajectory-sync?taskId=` | 触发一次轨迹同步（同任务并发去重） |
| POST | `/api/data/trajectory-sync/start\|stop` | 开启/停止周期性同步 |
| GET | `/api/data/dcd-preview/:filename` | 抽稀预览 DCD（`<taskId>_rep<n>.dcd`） |
| GET | `/api/data/dcd-file/:filename` | 完整 DCD（文件名带 `.dcd` 后缀便于 NGL 识别格式） |
| GET | `/api/data/dcd-last100/:filename` | 尾段 DCD |
| GET | `/api/data/dcd?taskId=` | 兼容旧接口（副本 0 完整 DCD） |
| GET | `/api/data/pdb?taskId=` | 拓扑 PDB |
| GET | `/api/data/sequence-annotations` | 序列高亮标注 |

> **轨迹连续性与多副本**：XTC→DCD 转换时对相邻帧做最小镜像无跳变（unwrap）处理（`tasktype/gromacs_cg/scripts/make_trajectory.py`，坐标与盒子统一以 Å 为单位），保证浏览器里播放不出现周期跨越的"直线"伪影。当前 `gromacs_cg` 任务使用单样本轨迹；多样本直接拼接会在分段边界产生无法消除的大位移，故多副本（多 DCD）模式接口与状态字段已就绪但未启用。

## 视频导出

- `POST /api/video/render`、`GET /api/video/status`、`GET /api/video/download`
- 服务端用 VMD 批量渲染轨迹帧 + ffmpeg 合成 MP4/GIF，支持"尾段窗口"与"完整轨迹"两种范围（`frontend/src/components/VideoDownloadButtons.tsx`）
- 渲染新鲜度校验：渲染代码与参数哈希写入 `<video>.sig` 边车文件（`renderSignature()` / `isVideoFresh()`），渲染逻辑变化后缓存自动视为过期

## 序列高亮

- 任务 `input/sequences.csv` 声明 motif/标签序列 → 后端 `sequence_annotation.py` 计算所有链上的出现位置 → `GET /api/data/sequence-annotations` → 前端在轨迹播放时用不同颜色高亮（详见 `docs/sequence-annotation-workflow.md`）

## 目录结构

```
igem-2026-software/
├── backend/                  # Express 后端
│   ├── index.js              # 入口（:3001）
│   ├── start.sh              # 手动启动脚本
│   ├── routes/               # control / data / files / servers / tasks / video / flows / transition
│   ├── services/             # run-main / trajectory-sync / trajectory-video / sim-status-sync / analysis / task-dir ...
│   ├── _shared/              # 共享 Python 模块：SSHClient / BaseTaskConfig / sequence_annotation / routes(make_dispatch)
│   ├── tasktype/             # 插件化任务类型：tiger2 / gromacs_cg / tiger2_dcd_to_gromacs_cg_pdb / seq_to_pdb
│   ├── tasks/                # 各任务的 input/scripts/logs/cache/output；tasks.json（凭据，gitignore）
│   └── servers.json          # 远程服务器注册（密码/私钥）
├── frontend/                 # Vite + React（Flow Console）
│   └── src/
│       ├── flow/             # 流程式界面（App / api / cards / sections / types）
│       ├── components/       # Structure / Convergence / Temperature / MolecularViewer ...
│       ├── utils/ styles/ theme/
│       └── types.ts          # 顶层类型定义
├── user.md                   # 用户文档（全部主要功能，无技术细节）
├── docs/                     # 技术文档（task-creation / sequence-annotation / feature-gap-analysis）
└── full-workflow-guide.md, visualization-guide.md, etc. / WORKFLOW.md   # MD 工作流与模拟分析指南
```

## 启动与部署

开发模式：

```bash
# 后端
cd backend && node index.js        # :3001

# 前端（开发）
cd frontend && npm run dev         # :5174，/api 代理到 127.0.0.1:3001
```

生产/常驻（推荐，systemd 用户服务）：

```bash
# backend/molecular-dynamics-platform-server.service：WorkingDirectory=backend，Restart=always，端口 3001
systemctl --user restart molecular-dynamics-platform-server.service
systemctl --user status molecular-dynamics-platform-server.service
```

> 若端口 3001 被手动启动的 `node index.js` 占用，systemd 服务会因 `EADDRINUSE` 反复重启，需先停掉手动进程再重启服务。同时运行的旧版本后端进程会把 `status.json` 改回旧结构、覆盖新代码的轨迹状态——排查轨迹同步异常时先确认只有一个后端进程监听 3001。

## 数据流

```
NAMD / GROMACS 远程输出（*.dcd / *.xtc / *.log）
    │  main.py route trajectory（SSH 下载 + XTC→DCD + 无跳变 unwrap）
    ▼
backend/tasks/<id>/cache/trajectory/
    ├── replica_*.dcd / preview / last100  ──▶ Structure / Dashboard / Convergence 的 NGL.js 播放器
    ├── topology.pdb                        ──▶ /api/data/pdb
    └── status.json                         ──▶ /api/data/trajectory-status

模拟日志与检查点
    │  main.py route sim-status / analyze
    ▼
sim-status.json / analysis/*  ──▶ /api/data/sim-status | structure | cluster | convergence
```

## 相关文档

- `user.md` — 面向用户的完整功能说明（无技术细节）
- `docs/task-creation.md` — 任务在磁盘上的表示与 quick-create 通道
- `docs/sequence-annotation-workflow.md` — 序列高亮标注工作流
- `full-workflow-guide.md` / `visualization-guide.md` / `WORKFLOW.md` — 分子动力学模拟与分析流程
- `docs/simulation-principles.md` — TIGER2 与 GROMACS CG 模拟的算法原理与可调参数
- `docs/sequence-to-properties-options.md` — 序列→模量流水线的前端选项、CSV 契约与测试程序
