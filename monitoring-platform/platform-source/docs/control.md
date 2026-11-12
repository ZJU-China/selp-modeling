# 任务运行状况对照表（control）

本文档记录当前「AI task-guard」服务与各模拟任务的运行状况，含一次性排障记录（`ERROR TOLERANCE` 误报），供运行时对照排查。

> 状态采集时间：2026-09-01 19:1x (UTC+8)。服务器主体：iGEM `127.0.0.1`（igem），远端：ZJU `192.0.2.20:20009`。
> 采集命令示例：`curl http://127.0.0.1:3001/api/data/checkpoint?taskId=<id>`、`systemctl --user status md-*`、`tail /tmp/md-guard.log`。

## 1. 服务进程（systemd 托管，唯一实例）

后端 :3001 / 前端 :5173 均已通过 systemd 用户服务管理，`Restart=always` 自动守护，**不允许再有手动 `node index.js` 实例**（曾出现双后端竞争同写 guard-state.json）。

| 服务 | 端口 | 启动方式 | 日志 |
|---|---|---|---|
| `md-server.service` | 3001 | `/usr/bin`/conda `node index.js`，cwd=`backend/` | `journalctl --user -u md-server`、`/tmp/md-guard.log` |
| `md-frontend.service` | 5173 | `npx vite --host 0.0.0.0 --port 5173` | `journalctl --user -u md-frontend` |

部署：本地 `git push igemgit master` → 远端 `git reset --hard <commit>` → `systemctl --user restart md-server`。

## 2. 各任务运行状态总览

| 任务 ID | 类型 | 服务器 | guard | 当前 | 最后活跃 | 进度 | checkpoint | 备注 |
|---|---|---|---|---|---|---|---|---|
| `tiger2_2ky5` | tiger2 | iGEM | on | **停止** | 2026-08-25 06:26 | 25005000 步 = 1667/1667 cycle | restart1667 全套(0–3) | **正常完成 100ns×4 副本**，非异常中断 |
| `tiger2_legacy` | tiger2 | iGEM | on | **停止** | 2026-07-30 | 6255000 步 = 417/417 cycle | 0–3 齐全 | 正常完成 / 长期挂起，无新产出 |
| `tiger2_zju` | tiger2 | ZJU | on | **停止** | 2026-07-29 | 18450000 步（cycle 1230） | 副本进度不一(750/700…) | 经 192.0.2.20:20009，任务未运行 |
| `gromacs_cg_zju` | gromacs_cg | ZJU | on | **停止** | 2026-07-29 | 无 job | 无 | 未启动/已清空 |
| `tiger2_gpu` | tiger2 | `srv_mruclkyupw7h` | on | **停止** | — | — | — | **server 未注册于 servers.json**，`/api/data/checkpoint` 报 500 |

> ZJU 远端 ssh 私钥 `~/.ssh/id_ed25519_example` + `StrictHostKeyChecking=no`（绕过 post-quantum warning）可连，无 namd3 进程。
> 本机 iGEM 无 namd3 进程。

## 3. task-guard 运行状态

- **循环**：每 60s 一轮（`MD_GUARD_INTERVAL`），汇总所有 `serverId` 任务。
- **当前决策（tiger2_2ky5）**：`no_action`（任务已正常完成，日志无真实错误签名）→ **修复后不再调用 LLM classify**。
- **LLM 端点**：`127.0.0.1:8080`（wanglab llama.cpp，Nemotron-3-Nano-30B-A3B）。`timeoutMs=120000`，`retry=2`（HTTP 非 2xx 冷启动重试）。
- **节流**：同一任务重复失败，LLM 每 2h 最多分类 1 次（`MD_GUARD_LLM_INTERVAL_MS`），窗口内复用上次决策且不重复写事件。
- **状态持久化**：git-ignored `backend/guard-state.json`（cooldown / restartCount / pause / lastClassify / events ≤500）。
- 事件计数（截至采集）：29 条。唯一一次自动重启尝试 `08-31 22:30:24 UTC action=restart_failed`（restart #1，`runMain restart` 未确认 running → 记 error 并冷却 15min）。

### guard 触发逻辑简表

| 情形 | 是否调 LLM | 落地事件 | 动作 |
|---|---|---|---|
| 进程 running | 否 | 无 | skip ok |
| 停止 + 日志无 error 签名 | 否 | 无 | ok（正常完成/手动停止） |
| 停止 + error 签名 + 非监控类型 | 否 | warn/report | report |
| 停止 + error 签名 + 监控类型 | 是（2h 节流） | restart→自动 restart；report→error 事件 | restart / report |
| LLM 不可用/JSON 解析失败 | （classify 内重试 3 次） | error/report，`gave up safely` | report |

## 4. 排障记录：`ERROR TOLERANCE` 误报修复（2026-09-01）

**现象**：guard 对 `tiger2_2ky5` 每分钟输出 `classify ... throttled, reusing no_action`，但任务实际早已正常停止。

**根因**：`scanErrorLogs` 的 `ERROR_PATTERNS` 含 `/\bERROR\b/i`，NAMD 正常启动信息 `Info: ERROR TOLERANCE : 1e-08` 被命中 → 正常日志被判定为 error 签名 → 触发向 LLM 分类（消耗 throttle 额度、空洞白跑），且 LLM 因内容正常永远判 `no_action`，掩盖真实 `restart` 判定。

**修复**（commit `8fd9c86`）：
```
- /FATAL ERROR/i, /\bERROR\b/i, ...
+ /FATAL ERROR/i, /\bERROR\s*(:|occurred|encountered)/i, ...
```
- 部署后 `scan.failed=false`（用同款逻辑复扫 4 副本日志验证），guard 不再误判、不再无谓调 LLM。
- 次要观察：`backend/tasks/<id>/logs/*` 为旧同步缓存（2KY5 停更于 08-13，真实 production 日志在远端 `~/igem-2026/MD/2KY5_snoopytag/production/`），guard 扫的是本地镜像日志，**同步链路可能长期未刷新**——若需 guard 基于最新日志工作，需确认 logs 同步是否继续。

## 5. 处理建议

1. `tiger2_2ky5` 已正常完成（100ns×4），可标记完成或归档，guard 判 `no_action` 属正确。若需补跑/重跑请手动操作。
2. `tiger2_legacy` 无新产出近 5 周+，`tiger2_zju`/`gromacs_cg_zju` 停摆超 5 周，`tiger2_gpu` server 未注册——均建议确认是「已完成归档」还是「被遗忘」，避免 guard 长期空转（虽然已节流，仍会每轮走 status/route 扫描）。
3. 若确认某任务停止且需恢复：手动 `POST /api/guard/check {taskId}` 立即触发一轮评估，或到前端 TaskControl 起始；guard 只在「LLM 判 restart」时才自动拉起（且仅 `tiger2` 类）。