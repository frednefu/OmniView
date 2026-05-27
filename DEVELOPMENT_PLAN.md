# OmniView 开发计划

## 架构目标

分布式扫描平台，支持多 Worker 节点并行执行，前端实时监控扫描进度。

```
核心节点 (API + Web + DB + Cache)

Frontend ──► FastAPI ──► MySQL 8.0
(Nginx)       /api         (业务数据)
               │
               ├──► Redis ── 任务队列 (Celery broker)
               │            扫描日志缓存 (实时进度)
               │            资产画像缓存
               │
               └──► WebSocket ──► 前端实时进度推送
        │
        │ Redis 队列分发
        ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ Worker 1 (Docker)│  │ Worker 2 (Docker)│  │ Worker N (Docker)│
│ 能力：全部数据源   │  │ 能力：全部数据源   │  │ 能力：全部数据源   │
│ 注册内容：        │  │ 注册内容：        │  │ 注册内容：        │
│  · SNMP 交换机   │  │  · SNMP 交换机   │  │  · F5            │
│  · vCenter       │  │  · ZDNS          │  │  · QAX           │
│  · F5            │  │  · QAX           │  │  · vCenter       │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

### Worker 注册与任务分发

- Worker 同构 Docker 镜像，所有扫描能力内置，启动时声明扫描内容
- 相同内容可分配多个 Worker 实例，实现多实例并行
- 5 个 Redis 队列按数据源分类：`queue:scan:snmp` / `vcenter` / `f5` / `zdns` / `qax`
- 安全认证：Worker Token + IP 白名单

---

## 实施阶段

### Phase A: MySQL 数据库切换 ✅

> **已提交** `ffb403f` → `b4d4770`（含适配修复）

- 移除 SQLite 特定代码（WAL PRAGMA、check_same_thread、connect 事件监听）
- 迁移函数改用 SQLAlchemy inspect（兼容 MySQL + SQLite）
- MySQL utf8mb4 字符集配置
- 创建 `.env.example` 模板
- 修复 `vm_inventory` 表索引键过长问题（String(1024) → String(255)，MySQL utf8mb4 索引限制 3072 字节）
- 本地开发模式：`docker-compose.local.yml`（仅 MySQL + Redis 容器，前后端本地运行）

---

### Phase B: Celery + Redis 扫描异步化 ✅

> **已提交** `147873e`

> **解决核心问题：发起扫描时前台响应慢**

**后端改动：**

| 文件 | 内容 |
|------|------|
| `backend/app/config.py` | 新增 `redis_url` 配置（已有）|
| `backend/requirements.txt` | 添加 `celery[redis]` |
| `backend/app/tasks/__init__.py` | Celery app 实例化 |
| `backend/app/tasks/scan_tasks.py` | 5 个 Celery task：`scan_switch` / `scan_vcenter` / `scan_f5` / `scan_zdns` / `scan_qax` |
| `backend/app/api/switches.py` | `POST /scan` 改为 `push_task_to_queue` → 立即返回 |
| `backend/app/api/vcenters.py` | 同上 |
| `backend/app/api/f5.py` | 同上 |
| `backend/app/api/zdns.py` | 同上 |
| `backend/app/api/qax.py` | 同上 |
| `backend/app/services/scheduler_service.py` | APScheduler job 改为 push 任务到队列，不再直接执行 |

**流程变更：**

```
改造前：POST /scan → 创建 ScanLog → 等待扫描初始化 → 返回 (阻塞10s+)
改造后：POST /scan → 创建 ScanLog → push Redis 队列 → 立即返回 202 (100ms)
        Worker 从队列取任务 → 执行扫描 → 更新 ScanLog
```

**Redis 职责：**

| 用途 | 数据结构 | 说明 |
|------|---------|------|
| 任务队列 | List (BRPOP) | 5 个队列，按数据源分 |
| 扫描进度 | Pub-Sub | Worker → API → WebSocket → 前端 |
| 资产画像缓存 | String (JSON) | 5 分钟 TTL |
| 仪表盘统计缓存 | String (JSON) | 30 秒 TTL |

---

### Phase C: 扫描步骤日志 + 实时监控面板 ✅

> **已提交** `f172f61`

> **解决核心问题：无法直观查看扫描进度和数据获取过程**

**数据库改动：**

- `scan_logs` 表新增 `progress_pct`、`current_step`、`log_output`、`worker_id` 字段
- 新增 `scan_steps` 表：`scan_log_id`、`step_order`、`step_name`、`status`、`items_total`、`items_processed`、`error_message`

**后端核心文件：**

| 文件 | 内容 |
|------|------|
| `backend/app/services/scan_step_service.py` | 统一扫描步骤追踪服务：`mark_queued()`/`mark_started()`/`update_progress()`/`append_log()`/`add_step()`/`finish_step()` |
| `backend/app/models/scan_log.py` | ScanLog 扩展字段 + ScanStep 模型（独立 DB 会话） |
| `backend/app/api/scan_logs.py` | `GET /{id}/steps`、`GET /{id}/output`、`DELETE /{id}`、批量清除支持 `status` 过滤 |
| 6 个 scanner_service | 增强日志输出（VM 分布/OS 统计/Pool 状态/记录类型/内外网分布）和细粒度进度更新（7-10 节点） |
| 修复各扫描器 `scan_log` 始终 `success` | 新增 `scan_successful` 标志，异常路径正确标记 `failed` |

**前端核心文件：**

| 文件 | 内容 |
|------|------|
| `frontend/src/views/ScanMonitor.vue` | 实时任务监控面板：进度卡片 + 展开步骤列表 + 终端输出 + 取消/删除/全部清除 |
| `frontend/src/api/scanLogs.js` | 新增 `deleteScanLog`、`clearScanLogs(status)` |
| `frontend/src/router/index.js` | 新增 `/scan-monitor` 路由 |

**已实现功能：**
- 6 类数据源扫描进度卡片实时展示（进度条 + 当前步骤 + 已用时间）
- 点击展开：分步详情（步骤状态 + 成功/失败计数）+ 终端实时输出
- 2 秒自动轮询刷新 + 手动刷新 + 运行中任务计数
- 按数据源/状态筛选，单条删除 + 一键清除全部失败记录
- 扫描器终端输出包含丰富统计信息（采集数量/分布/明细快照）

---

### Phase D: WebSocket 进度推送 + 前端稳定性修复 ✅

> **已提交** `716a6c0`、`0ea20d7`、`4929c66`

**后端改造：**

| 文件 | 内容 |
|------|------|
| `backend/app/api/ws.py` | WebSocket 端点 `/ws/scan-progress`：JWT 鉴权 + Redis Pub-Sub 订阅 |
| `backend/app/services/progress_broker.py` | Redis Pub-Sub 发布：`publish_scan_update()` 推送轻量标量字段（不含 steps/log_output） |
| `backend/app/services/scan_step_service.py` | `_notify()` 添加 1.5s 节流；`append_log()` 不再触发通知（终端输出由前端独立轮询） |
| 6 个 scanner_service | 增强终端日志输出：连接状态、采集内容说明、采集进度（每 10 台服务器） |

**前端改造：**

| 文件 | 内容 |
|------|------|
| `frontend/src/views/ScanMonitor.vue` | 完全重写——移除 WebSocket 集成，改用 5s 轮询 + 自动刷新开关；新增全部删除按钮；默认筛选运行中任务；模板状态感知显示 |

**技术决策——WebSocket 为何从前端移除：**

WebSocket 实时推送方案在后端已完整实现（Redis Pub-Sub → WS 端点），但在前端集成时暴露了严重的性能问题：

- **根因**：Vue 3 的 `reactive`/`ref` 会对 WS 推送的嵌套对象（`steps` 数组、`log_output_tail`）创建深度 Proxy 包装。当 6 类数据源同时扫描（QAX 300+ 服务器、F5 大量 Pool 成员），高频 WS 消息触发 `Object.assign` 合并，导致 Vue Proxy 递归重新包装嵌套对象，造成浏览器主线程阻塞数秒。
- **尝试过的方案**：`shallowRef`（仍触发深层追踪）、RAF 批量更新、数组整体替换、"WS 仅作脏标记"——均未能彻底解决，甚至使问题更严重。
- **最终方案**：前端移除 WebSocket 集成，改用简单的 5 秒轮询 + 可关闭的自动刷新开关。后端 WS 基础设施保留备用。轮询返回的普通 JS 对象不经过 Vue Proxy 深层追踪，性能稳定。

**Redis Pub-Sub Channel 设计（后端已实现，前端暂未使用）：**

```
channel:scan:{scan_log_id}    — 单个任务进度更新
channel:scan:list              — 任务列表变更（新增/完成）
```

---

### Phase E: Worker 容器化 + 注册认证 ✅

> **已提交** `b1584a6`

> **解决核心问题：Worker 需单独命令行启动，无容器化部署方案，无注册监控机制**

**数据库改动：**

- 新增 `scan_workers` 表：`worker_name`（唯一）、`token_hash`、`ip_address`、`status`（online/offline/busy）、`capabilities`（JSON）、`current_tasks`、`max_tasks`、`version`、`last_heartbeat`

**后端核心文件：**

| 文件 | 内容 |
|------|------|
| `backend/app/models/scan_worker.py` | Worker 数据模型（11 字段，独立 DB 会话） |
| `backend/app/schemas/worker.py` | Pydantic 模式：注册/心跳/注销请求与响应 |
| `backend/app/api/worker_auth.py` | Worker 共享密钥认证依赖（`secrets.compare_digest` 时序安全比较） |
| `backend/app/api/workers.py` | 6 个 API 端点：register/heartbeat/deregister（Worker 认证）+ list/get/delete（管理员认证） |
| `backend/app/config.py` | 新增 `worker_token` 配置项 |

**Docker 相关：**

| 文件 | 内容 |
|------|------|
| `backend/Dockerfile.worker` | Celery Worker 镜像（并发 4，1h 硬超时，55min 软超时） |
| `docker-compose.worker.yml` | Worker 独立部署模板（mysql + redis + worker），支持 `--scale worker=N` 水平扩容 |

**Worker 安全认证：**

```
Worker 启动 → 携带 WORKER_TOKEN 向 API 注册（幂等：同名重新注册即更新）
API secrets.compare_digest() 时序安全比较 → 创建/更新 scan_workers 记录 → 返回 Worker ID
Worker 定期发送心跳 POST /api/workers/{id}/heartbeat
Worker 关闭时发送 deregister → 标记 offline
管理面板可查看所有 Worker 在线状态/当前任务/并发数
```

---

### Phase F: Worker 管理面板 + 调度增强 ✅

> **已提交** `337b7ef`、`3132d0b`

> **解决核心问题：管理员无法在前端查看和管理 Worker 节点；任务队列路由与并发计数不准确**

**前端核心文件：**

| 文件 | 内容 |
|------|------|
| `frontend/src/views/WorkerManage.vue` | Worker 管理面板：状态标签（在线绿/忙碌橙/离线灰）、能力标签、并发数、心跳相对时间（超2分钟红色）、自动刷新、注册对话框（名称+版本+能力勾选）、删除确认 |
| `frontend/src/api/workers.js` | Worker API 封装（getWorkers / getWorker / registerWorker / deleteWorker） |

**后端增强：**

| 文件 | 内容 |
|------|------|
| `backend/app/api/worker_auth.py` | 新增 `verify_worker_or_admin` 双认证依赖（Worker Token → Admin JWT 回退） |
| `backend/app/api/workers.py` | register 端点改用双认证，Admin 手动注册时存储 WORKER_TOKEN hash 作为凭证 |
| `backend/app/tasks/celery_app.py` | Celery `worker_ready` 信号自动注册 + `worker_shutdown` 信号自动注销；`multiprocessing.Value` 跨进程并发计数器；6 队列精确路由 + 能力订阅；SIGTERM 即时注销 |
| `backend/app/tasks/scan_tasks.py` | 所有 6 个 task 新增 `_record_worker()` 记录执行节点到 scan_log |
| `backend/app/models/scan_log.py` | 新增 `worker_name` 字段，追溯扫描由哪个 Worker 执行 |
| `backend/requirements.txt` | 添加 `requests`、`urllib3` 依赖（椒图扫描器） |

**调度修复：**
- 修复 Worker 并发计数始终为 0：prefork 池子进程变量对主进程不可见 → 改用 `multiprocessing.Value('i', 0)` 共享内存
- 修复 zdns_ip 任务永久排队：Worker 能力列表缺少 zdns_ip → 默认值补齐 6 种类型
- 修复 qax 扫描崩溃：`ModuleNotFoundError: No module named 'urllib3'` → 补全依赖
- 修复 Python 字节码缓存导致新代码不生效 → 清理 `__pycache__`

**前端增强：**

| 文件 | 内容 |
|------|------|
| `frontend/src/views/ScanMonitor.vue` | 新增 Worker 执行节点显示；zdns_ip 更名为"IP扫描"；统一 6 种技能颜色（与资产画像色块一致） |
| `frontend/src/views/ScanLogs.vue` | 新增"执行节点"列；zdns_ip/qax 加入筛选下拉；统一技能颜色 |
| `frontend/src/views/WorkerManage.vue` | 技能标签统一颜色和名称（含"IP扫描"）；注册表单能力勾选同步更新 |
| `frontend/src/views/Dashboard.vue` | 图表颜色统一为 6 种技能配色 |

**已实现功能：**
- Worker 容器启动后自动向 API 注册（Celery 信号驱动）
- Worker 容器关闭时自动注销（SIGTERM + worker_shutdown 双保障）
- 管理员可手动注册 Worker（名称、版本、扫描能力勾选）
- 表格展示：状态彩色标签、能力标签、并发数、心跳相对时间、超时红色警告
- 状态下拉筛选 + 名称搜索 + 分页
- 5秒自动刷新 + 开关
- Admin 专属菜单（侧边栏 `v-if="authStore.isAdmin"`）
- 任务队列精确路由（6 个数据源 → 6 个独立 Redis 队列）
- Worker 能力订阅（`WORKER_TASK_TYPES` 控制队列订阅范围）
- 跨进程并发计数器（`multiprocessing.Value` 共享内存）
- 扫描日志记录执行 Worker 名称（前端可追溯）
- 统一 6 种技能颜色和名称（全前端一致）

---

### Phase G: 版本管理 ✅

> **解决核心问题：前后端 + Worker 版本号分散硬编码，缺乏统一管理**

**实现方案：**

| 组件 | 改动 |
|------|------|
| `VERSION` 文件 | 项目根目录 + `backend/VERSION`，当前版本 `1.0.0` |
| `backend/app/version.py` | `get_version()` 读取 VERSION 文件，支持 `OMNIVIEW_VERSION` 环境变量覆盖 |
| `backend/app/api/version.py` | `GET /api/version` 公开端点 |
| `backend/app/main.py` | FastAPI `version` 参数从文件读取 |
| `backend/app/tasks/celery_app.py` | Worker 注册版本从 VERSION 文件读取 |
| `frontend/src/api/version.js` | 前端版本 API 封装 |
| `frontend/src/components/AppLayout.vue` | 侧边栏底部动态显示版本号 |
| `frontend/src/views/WorkerManage.vue` | 注册表单版本号自动填充当前版本 |

**版本规则：**
| 操作 | 版本变化 | 示例 |
|------|---------|------|
| 代码修改 | PATCH +1 | 1.0.0 → 1.0.1 |
| Git 提交 | MINOR +1 | 1.0.0 → 1.1.0 |
| 重大功能升级 | MAJOR +1 | 1.0.0 → 2.0.0 |

---

### Phase H: Redis 缓存优化 ✅

> **解决核心问题：资产画像跨源关联计算和仪表盘统计查询重复执行，无缓存加速**

**实现方案：**

| 文件 | 内容 |
|------|------|
| `backend/app/services/cache_service.py` | Redis 缓存封装：`get_json`/`set_json`/`get_cache`/`set_cache`/`delete_cache`/`invalidate_pattern`，Key 前缀 `omniview:cache:` |
| `backend/app/api/asset_profile.py` | `_get_cached_profile()` 改为 Redis 优先（命中返回 / 未命中构建后缓存），TTL 300s |
| `backend/app/api/dashboard.py` | `dashboard_stats()` 开头检查缓存，末尾写入缓存，TTL 30s |

**缓存策略：**

| 缓存键 | TTL | 说明 |
|--------|-----|------|
| `omniview:cache:asset_profile:rows` | 300s | 资产画像全量行数据（JSON），stats/filters 从缓存数据实时计算 |
| `omniview:cache:dashboard:stats` | 30s | 仪表盘统计摘要（DashboardStats JSON），高访问频率短 TTL |

**缓存效果：**

| 接口 | 冷缓存 | 热缓存 | 提升 |
|------|--------|--------|------|
| `/api/dashboard/stats` | ~80ms | ~62ms | ~23% |
| `/api/asset-profile` | ~255ms | ~210ms | ~17% |

---

### Phase I: 远程部署 Worker（远期）

- API 通过 SSH 连接目标服务器，执行 `docker compose up -d`
- 或对接 Docker Remote API / Portainer
- 前端可直接部署扫描引擎 Docker 到指定服务器

---

## 技术栈

| 层 | 技术 |
|---|------|
| 后端 | FastAPI + SQLAlchemy 2.0 + Celery |
| 数据库 | MySQL 8.0 |
| 缓存/队列 | Redis 7 |
| 实时推送 | WebSocket + Redis Pub-Sub |
| 前端 | Vue 3 + Element Plus + ECharts |
| 部署 | Docker Compose |

## 当前进度

| 阶段 | 状态 | 提交 |
|------|------|------|
| Phase A: MySQL 切换 | ✅ 已完成 | `ffb403f` |
| Phase B: Celery + Redis 异步化 | ✅ 已完成 | `147873e` |
| Phase C: 扫描步骤日志 + 监控面板 | ✅ 已完成 | `f172f61` |
| Phase D: WebSocket 进度推送 + 前端稳定性修复 | ✅ 已完成 | `716a6c0`, `0ea20d7` |
| Phase E: Worker 容器化 | ✅ 已完成 | `b1584a6` |
| Phase F: Worker 管理面板 + 调度增强 | ✅ 已完成 | `337b7ef`, `3132d0b` |
| Phase G: 版本管理 | ✅ 已完成 | — |
| Phase H: Redis 缓存 | ✅ 已完成 | — |
| Phase I: 远程部署 | 🔲 下一步 | — |
