# OmniView — 全维视界

企业级多源 IT 资产发现与治理平台。通过集成交换机、虚拟化、负载均衡、DNS 及主机安全五类基础设施接口，实现自动化资产测绘、全链路关系映射与集中可视化管控。

### 核心能力

- **全源主动发现** — SNMP / vSphere API / iControl REST / ZDNS API / 椒图 API 五种协议并行采集，覆盖网络层、虚拟化层、应用交付层、域名解析层、主机安全层
- **跨源关系融合** — 以 MAC/IP/域名 为纽带自动关联五源数据，构建"物理端口 → 虚拟机 → 业务负载 → 域名 → 主机进程"的完整资产画像
- **字段级变更追踪** — 每数据源独立复合键，增量 diff 记录新增/删除/修改，JSON change_detail 保存字段级新旧值对比，支持历史回查
- **智能可视化分析** — 全局仪表盘多维度统计（ESXi CPU 类型/存储类型/OS 分布/扫描成功率），地址段利用率图表，点击下探明细，全局搜索联动
- **弹性异步任务队列** — Celery + Redis 异步任务队列，APScheduler 按设备独立调度提交任务，Worker 线程池并发执行，意外中断自动恢复

### 技术栈

| 层 | 技术 |
|---|------|
| 后端框架 | FastAPI (Python 3.10+) |
| ORM | SQLAlchemy 2.0 |
| 数据库 | MySQL 8.0 / SQLite (开发) |
| 异步队列 | Celery 5.6 + Redis |
| SNMP | pysnmp 7.1+ (Slim API，支持标准 MIB + 华为私有 MIB) |
| vCenter | pyVmomi 9.1+ (VMware vSphere SDK) |
| F5 | iControl REST API (HTTPS + Basic Auth) |
| ZDNS | REST API (HTTPS + Basic Auth, GET with body) |
| 椒图 | 云锁 REST API (Api-Token 签名认证) |
| 前端 | Vue 3 + Element Plus + ECharts |
| 部署 | Docker Compose (MySQL + Redis + backend + frontend) |

### 功能

- **仪表盘** — 全源资源概览：统计卡片（ZDNS域名/F5域名/公网IP端口/内网服务/虚拟机/VM IP/VLAN/文件夹）点击弹出明细搜索对话框，VM 开关机/Pool 状态/DNS 记录类型/扫描次数环形图与饼图，地址段利用率图表点击下探已占用 IP，ESXi CPU 类型分布/存储类型容量统计/OS 分布/CPU 核数/内存容量多维度可视化，扫描成功率摘要，可用 IP 查询
- **交换机管理** — CRUD、批量导入(Excel/CSV)、模板下载、SNMP 连接测试、扫描状态/结果展示、全部扫描/全部删除
- **SNMP 扫描** — 自动识别 L2/L3 交换机，支持标准 MIB 和华为私有 MIB（含 BD 模式），ARP+FDB 多源合并，空 IP 自动回填，路由表采集
- **扫描结果** — 主机信息（IP/MAC/VLAN/端口/交换机来源）分页列表（自动去重显示最新）、路由表分页列表
- **扫描监控** — 实时任务监控面板：全部6类数据源扫描进度卡片（进度条 + 当前步骤 + 已用时间），点击展开查看分步详情（步骤状态 + 成功/失败计数）和终端输出，支持取消扫描、单条删除、全部删除，5秒自动轮询 + 可开关自动刷新，默认筛选运行中任务
- **扫描日志** — 统一多数据源扫描记录中心（交换机/vCenter/F5/ZDNS/椒图），支持按数据源和状态筛选、分页、清除、耗时记录，增强扫描器终端输出：采集统计（VM 电源/OS/存储/ESXi 明细、Pool 状态分布、DNS 记录类型/内外网分布、Ping 在线/离线汇总）和细粒度进度更新，扫描器连接状态与采集进度实时反馈
- **地址段管理** — CRUD、IP 可用性计算、利用率统计、已占用 IP 明细下探
- **全局搜索** — 二级策略（资产画像优先 + 扫描结果兜底），完整 IP 自动精确匹配，MAC 模糊查找
- **变更历史** — 交换机 (IP, MAC) / vCenter (VM名, vCenter) / F5 (VS名, 域名, Pool) / ZDNS (域名, 记录类型) 四源复合键追踪，字段级新旧值对比，按IP/MAC/VM名称/日期范围过滤，Tab 式切换
- **用户认证与权限** — JWT + bcrypt，admin/user 角色，管理员可管理用户（CRUD/重置密码/角色状态）
- **个人设置** — 修改邮箱、修改密码
- **定时调度** — APScheduler 按设备独立扫描间隔自动触发，扫描中断（running 卡住）自动重置 + 手动取消端点全覆盖
- **Worker 容器化** — Celery Worker 独立 Docker 部署 + Worker 启动自动注册 + 关闭自动注销 + 心跳监控，支持多实例水平扩容
- **Worker 管理面板** — 管理员前端查看所有 Worker 节点（状态/能力/并发/心跳），支持手动注册、状态下拉筛选、自动刷新、删除离线节点
- **vCenter 管理** — CRUD、连接测试、pyVmomi 扫描采集 VM 清单（20 个字段：数据中心/集群/ESXi/资源池/文件夹/名称/IP/MAC/网络/VLAN/OS/CPU/内存/置备存储/已用存储/备注），MAC 匹配交换机回填缺失 IP，多字段搜索 + 电源/OS/网络/文件夹下拉筛选
- **vCenter ESXi 主机** — 自动采集物理主机信息（主机名/管理 IP/处理器类型/逻辑处理器数/内存/Hypervisor/网卡数/连接状态），独立 Tab 展示
- **vCenter 存储器** — 自动采集 Datastore 详情（名称/状态/类型/总容量/可用空间/挂载主机数），使用率进度条可视化，自动分类共享存储/共享NAS/本地存储，仪表盘按类型汇总
- **VM 清单** — 全局 `vm_inventory` 视图，跨 vCenter 搜索过滤，分页展示
- **F5 负载均衡管理** — CRUD、连接测试、iControl REST 扫描虚拟服务器+Pool成员+iRules，自动构建域名→VS IP:端口→Pool 成员 IP:端口的应用映射，搜索过滤，定时扫描，历史追踪
- **F5 原始数据** — 虚拟服务器、Pool 成员（含 up/down 状态）、iRules（含 TCL 脚本）三个 Tab 独立搜索分页
- **ZDNS 域名管理** — CRUD、连接测试、REST API 分页采集 DNS 记录，域名→IP 映射（IPv4/IPv6 + 内外网自动分类），定时扫描，历史追踪
- **ZDNS 记录与映射** — DNS 记录和域名→IP 映射清单各自搜索分页，支持记录类型/启用状态/IP 状态筛选
- **ZDNS IP 可达性扫描** — 关联交换机和 F5 数据判定 IP 在线状态（在线/离线/禁用/待定），一键 ping 探测 + 定时 IP 扫描，独立扫描间隔
- **资产画像** — 五源关联（ZDNS/F5/vCenter/交换机/椒图），双栏布局（左域名列表 + 右资产链路树），域名→VIP→Pool成员→VM→网络/VLAN 完整链路追踪，F5 Rules/Pool 双模式精准匹配 + HTTP→HTTPS 重定向检测，VIP 入口智能分类（内网/IPv4公网/IPv6公网），ESXi 宿主机/椒图主机详情联动展示，五源筛选 + 域名搜索 + Excel 导出
- **奇安信椒图管理** — CRUD、连接测试、批量采集服务器清单（名称/IP/OS/CPU/内存/磁盘/在线状态/分组），端口/进程/软件三级详情自动采集，定时调度（默认 24h），扫描日志
- **信息系统管理** — 信息系统资产台账维护（38字段），Excel 四格式智能导入（系统导出/资产导出/资产清单/信息系统管理，表头驱动映射，3种去重策略，asset_id/system_name双键匹配，TRIM防重复），供应链厂商自动入库，38列中文全字段导出，批量删除/字段排序/多维筛选（6个筛选器），数据同步（域名清洗→ZDNS匹配→自动/注销→IP替换→入口地址→验证状态），人员查询三步检索（系统用户→本地教职工库→数据中台API），自动注册补全信息（邮箱/电话/手机/部门/性别），等保系统名称本地下拉联动，导入时管理员自动建号，等保/ICP/供应链三页面统一样式分页，显式字段枚举消除 Proxy 枚举遗漏，通用类型清洗（Date/Integer/Float 空值→NULL），管理员/负责人按钮区分标签，保存成功后返回变更字段列表
- **鼎甲备份对接** — 备份记录自动采集，/d2/r/v2/sets API 获取每个VM的备份集（minor_resource_name/backup_start_time/backup_end_time），时区修正（UTC→东八区），持续时间计算，可展开历史版本子表（按时间倒序），默认开始时间倒序+VM名称正序，分页排序/记录统计
- **菜单重构** — 分组标题改为子菜单，仪表盘管理员/普通用户分流，系统管理增加角色管理占位（待开发），集成管理/日志信息/网络资产信息 三级菜单收纳

### 快速开始

```bash
# 1. 启动 MySQL + Redis
docker-compose -f docker-compose.local.yml up -d

# 2. 后端
cd backend
cp .env.example .env         # 编辑数据库连接
pip install -r requirements.txt
python seed.py
uvicorn app.main:app --host 0.0.0.0 --port 8000 &

# 3. Celery Worker（必须单独启动，Windows 使用 threads 池）
celery -A app.tasks.celery_app worker --pool=threads --concurrency=8 --loglevel=info &

# 4. 前端
cd frontend
npm install
npm run dev

# 5. 访问
# 前端: http://localhost:5173
# API 文档: http://localhost:8000/docs
```

默认账号：`admin` / `Admin123!`、`viewer` / `Viewer123!`

#### 生产部署

```bash
# 启动全部服务（MySQL + Redis + Backend + Frontend + Celery Worker）
docker-compose up -d

# 初始化种子数据
docker-compose exec backend python seed.py

# 访问
# 前端: http://localhost
# API 文档: http://localhost:8000/docs
```

### Worker 分布式运行机制

#### 拓扑架构

```
                          ┌──────────────────────────┐
                          │      核心节点 (主控)       │
                          │  FastAPI + MySQL + Redis  │
                          │      10.0.0.1:8000        │
                          └────────────┬─────────────┘
                                       │
                         Redis 任务队列 (6 个数据源)
                         ┌──────────┬──┴────────┬──────────┐
                         │          │     │          │        │
                    queue:scan:  switch vcenter  f5  zdns zdns_ip qax
                         │          │     │          │        │
              ┌──────────┼──────────┼─────┼──────────┼────────┼──────────┐
              │          │          │     │          │        │          │
         ┌────┴────┐ ┌───┴────┐ ┌──┴───┐ ┌┴──────┐ ┌─┴────┐ ┌──┴────┐
         │Worker 1 │ │Worker 2│ │Worker│ │Worker │ │Worker│ │Worker │
         │10.0.0.2 │ │10.0.0.3│ │  N   │ │  N+1  │ │ N+2  │ │  N+3  │
         │snmp     │ │vcenter │ │ f5   │ │ zdns  │ │zdnsip│ │  qax  │
         │vcenter  │ │ f5     │ │ zdns │ │zdns_ip│ │ qax  │ │ snmp  │
         │f5,zdns  │ │zdns_ip │ │ qax  │ │ snmp  │ │vcenter│ │ f5    │
         └─────────┘ └────────┘ └──────┘ └───────┘ └──────┘ └───────┘
              │          │          │         │          │
              │          │          │         │          │
              └──────────┴──────────┴─────────┴──────────┘
                         定期心跳上报 + 任务状态回写
                               ▼
                     POST /api/workers/{id}/heartbeat
```

**核心节点** 负责 Web 界面、API 网关、数据库、Redis 消息队列。Worker 节点仅运行 Celery 消费者进程，无需数据库或 Web 服务。

**Worker 节点** 均使用同一 Docker 镜像，所有扫描能力内置。启动时通过 `capabilities.task_types` 声明要处理的数据源类型，可声明全部或部分类型。多个 Worker 声明相同类型即可实现该类型的多实例并行消费。

**6 种任务类型 → 独立队列**：

| 任务类型 | 队列名 | 说明 |
|----------|--------|------|
| switch | `scan:switch` | 交换机 SNMP 扫描 |
| vcenter | `scan:vcenter` | vCenter 虚拟机采集 |
| f5 | `scan:f5` | F5 负载均衡配置采集 |
| zdns | `scan:zdns` | ZDNS 域名解析记录采集 |
| zdns_ip | `scan:zdns_ip` | ZDNS IP 可达性检测 |
| qax | `scan:qax` | 椒图主机安全信息采集 |

Worker 根据 `WORKER_TASK_TYPES` 环境变量订阅对应队列，只消费能力范围内的任务。任务提交时自动路由到对应队列，队列无人订阅则任务排队等待。

**并发计数器（跨进程共享）**：Worker 使用 prefork 进程池，任务在子进程中执行。通过 `multiprocessing.Value` 实现主进程心跳线程与子进程的计数器共享，确保心跳上报的 `current_tasks` 实时反映实际并发数。任务开始 → counter+1、status=busy，任务结束 → counter-1、status=online。

**扫描日志追溯**：每个任务的 `scan_log` 记录 `worker_name` 字段，前端扫描监控和扫描日志页面可查看每条记录由哪个 Worker 节点执行。

#### 注册认证流程

```
Worker 容器启动
    │
    ├─ 环境变量: WORKER_TOKEN, WORKER_NAME, API_BASE_URL
    │
    ▼
Celery worker_ready 信号触发
    │
    ├─ POST /api/workers/register  (Bearer WORKER_TOKEN)
    │    Body: { worker_name, capabilities, version }
    │    ← API 自动记录客户端 IP (request.client.host)
    │    ← 返回 worker_id，存储到 Worker 内存
    │
    ▼
Worker 进入就绪状态，开始消费 Redis 任务队列
    │
    ├─ 定期心跳: POST /api/workers/{id}/heartbeat (每 15s)
    │    Body: { current_tasks, status }
    │    Status: "busy" 当 current_tasks > 0，否则 "online"
    │
    ▼
Worker 关闭 (SIGTERM)
    │
    ├─ SIGTERM 信号处理器 → 即时调用 deregister
    └─ Celery worker_shutdown 信号 → 补充保障
         → 状态标记为 offline，current_tasks 清零
    │
    ▼
API 端定时清理 (每 30s)
    └─ 心跳超过 45 秒未更新 → 标记为 offline
```

#### 认证机制

| 组件 | 认证方式 | 说明 |
|------|---------|------|
| Worker → API | Bearer `WORKER_TOKEN`（共享密钥）| `secrets.compare_digest()` 时序安全比较 |
| Admin → Worker API | Bearer Admin JWT | 管理员通过前端管理 Worker |

**注册端点双认证**（`verify_worker_or_admin`）：
- 先尝试 Worker Token 认证 → 工作节点自注册
- Token 不匹配则尝试 Admin JWT → 管理员手动注册

#### 生产环境分布式部署

**前置条件**：核心节点已完成部署（MySQL + Redis + FastAPI + Frontend），网络互通。

**步骤**：

```bash
# 1. 在每一台 Worker 主机上克隆项目
git clone <repo-url> /opt/omniview
cd /opt/omniview

# 2. 配置环境变量 (.env)
# WORKER_TOKEN=<与核心节点一致的共享密钥>
# REDIS_PASSWORD=<与核心节点一致的 Redis 密码>
# REDIS_URL=redis://:密码@10.0.0.1:6379/0  ← 核心节点 Redis 地址
# API_BASE_URL=http://10.0.0.1:8000       ← 核心节点 API 地址
# WORKER_NAME=omniview-worker-01           ← 本机唯一标识

# 3. 启动 Worker（仅启动 worker 服务，不含 mysql/redis）
docker-compose -f docker-compose.worker.yml up -d

# 4. 同一主机扩容（多实例并行）
docker-compose -f docker-compose.worker.yml up -d --scale worker=4

# 5. 手动创建单个 Worker（指定名称和并发数）
docker run -d \
  --name omniview-worker-02 \
  --network <network_name> \
  -e DATABASE_URL="mysql+pymysql://ipam:password@mysql:3306/ipam?charset=utf8mb4" \
  -e REDIS_URL="redis://:password@redis:6379/0" \
  -e WORKER_TOKEN="<shared-secret>" \
  -e API_BASE_URL="http://host.docker.internal:8000" \
  -e WORKER_NAME="worker-02" \
  -e WORKER_CONCURRENCY="8" \
  -e WORKER_TASK_TYPES="switch,vcenter,f5,zdns,zdns_ip,qax" \
  -e TZ="Asia/Shanghai" \
  -v "$(pwd)/backend:/app" \
  -v "$(pwd)/switchReader:/app/switchReader" \
  <worker-image>:latest \
  celery -A app.tasks.celery_app worker --concurrency=8 --loglevel=info --time-limit=3600 --soft-time-limit=3300
```

**`docker run` 参数说明**：

| 参数 | 说明 |
|------|------|
| `--name` | 容器名，必须唯一 |
| `--network` | 必须与 MySQL/Redis 容器同一网络 |
| `WORKER_NAME` | Worker 注册名称，必须唯一，与手动注册名称一致则认领 pending 状态 |
| `--concurrency=N` | **并发任务数**，即 Worker 同时可执行的任务数（默认 4） |
| `--time-limit` | 单个任务硬超时（秒），超时强制终止 |
| `--soft-time-limit` | 单个任务软超时（秒），超时抛出异常供任务自行处理 |

**多主机部署示例**（3 台 Worker 主机，每台 4 实例 = 12 并发）：

| 主机 | IP | Worker 名称 | 实例数 |
|------|-----|-------------|--------|
| Worker 主机 A | 10.0.0.2 | worker-a-{n} | 4 |
| Worker 主机 B | 10.0.0.3 | worker-b-{n} | 4 |
| Worker 主机 C | 10.0.0.4 | worker-c-{n} | 4 |

**关键环境变量**（`.env` 和 `docker-compose.worker.yml`）：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `WORKER_TOKEN` | 共享密钥，必须与核心节点一致 | 必填 |
| `API_BASE_URL` | 核心节点 API 地址 | `http://backend:8000` |
| `WORKER_NAME` | Worker 唯一名称 | 主机名 |
| `WORKER_VERSION` | Worker 版本标识（默认从 `VERSION` 文件读取） | `1.0.0` |
| `WORKER_CONCURRENCY` | 并发任务数（需与 --concurrency 一致） | `4` |
| `WORKER_TASK_TYPES` | 该 Worker 处理的数据源（逗号分隔） | `switch,vcenter,f5,zdns,zdns_ip,qax` |
| `REDIS_PASSWORD` | Redis 认证密码，所有节点必须一致 | 必填 |
| `REDIS_URL` | Redis 连接串（含密码） | `redis://:password@redis:6379/0` |

**注意事项**：
- 所有 Worker 的 `WORKER_TOKEN` 必须与核心节点 `.env` 中的一致，否则注册被拒
- **Redis 密码认证**：跨主机通信必须使用 `requirepass`，`REDIS_URL` 格式为 `redis://:密码@主机:6379/0`
- Worker 通过 `API_BASE_URL` 访问核心节点 API，确保网络可达（防火墙放行 8000 + 6379 端口）
- Worker 容器与核心节点共享 Redis 队列，Redis 连接信息从 `.env` 读取
- Worker 意外断连后，心跳超时（45 秒）自动标记为 offline，前端状态变更为离线（灰色）

#### 本地开发

```bash
# 基础服务（MySQL + Redis）
docker-compose -f docker-compose.local.yml up -d

# 后端
cd backend
cp .env.example .env
pip install -r requirements.txt
python seed.py
uvicorn app.main:app --reload --port 8000

# Celery Worker（另开终端）
cd backend
celery -A app.tasks.celery_app worker --pool=threads --concurrency=8 --loglevel=info

# 前端（另开终端）
cd frontend
npm install
npm run dev
```

### 项目结构

```
├── docker-compose.yml
├── docker-compose.worker.yml
├── backend/
│   ├── Dockerfile
│   ├── Dockerfile.worker
│   ├── app/
│   │   ├── main.py              # FastAPI + lifespan
│   │   ├── config.py            # Pydantic Settings
│   │   ├── database.py          # SQLAlchemy engine
│   │   ├── models/              # User, Switch, ScanResult, RouteTable, ScanLog, ScanWorker, Subnet, History, VCenter, VMInventory, EsxiHost, Datastore, F5*, ZDNS*, QAX*
│   │   ├── schemas/             # Pydantic 请求/响应
│   │   ├── api/                 # auth, switches, results, history, scan_logs, dashboard, subnets, search, users, vcenters, f5, zdns, qax, asset_profile, workers, worker_auth
│   │   ├── services/            # scanner(SNMP), history, scheduler, scan_step_service, vcenter_scanner, f5_scanner, zdns_scanner, zdns_ip_scanner, qax_scanner, asset_profile, subnet
│   │   ├── tasks/               # Celery 异步任务（celery_app, scan_tasks）
│   │   └── utils/               # security (JWT, bcrypt)
│   ├── seed.py                  # 默认用户初始化
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── views/               # Dashboard, AssetProfile, InfoSystem, DjDj, Icp, SupplyChain, SwitchList, VCenterList, F5List, ZDNSList, QAXList, DingJia, Results, Routes, Subnets, ScanLogs, ScanMonitor, History, AccountManage, Departments, Workers, Scheduler, ApiConfig, Profile
│   │   ├── components/          # AppLayout（菜单：信息资产/网络资产/集成管理/日志/系统管理）
│   │   ├── api/                 # Axios 封装
│   │   ├── store/               # Pinia auth
│   │   └── router/              # Vue Router（含角色守卫）
│   └── nginx.conf
└── switchReader/
    └── switchReader.py          # SNMP 采集引擎（Web 后端复用）
```

### API 路由

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/auth/login | 登录 |
| GET | /api/auth/cas/login | CAS 登录重定向 |
| GET | /api/auth/cas/callback | CAS 回调验证 + JWT 签发 |
| GET | /api/auth/cas/logout | CAS 单点登出 |
| GET | /api/auth/me | 当前用户信息 |
| PUT | /api/auth/profile | 修改个人资料 |
| PUT | /api/auth/change-password | 修改密码 |
| CRUD | /api/switches | 交换机管理 |
| POST | /api/switches/test | SNMP 连接测试 |
| POST | /api/switches/{id}/scan | 触发扫描（遇卡住的 running 自动重置） |
| POST | /api/switches/{id}/cancel-scan | 取消扫描（手动重置） |
| POST | /api/switches/scan-all | 全部扫描（自动重置卡住状态） |
| DELETE | /api/switches/all | 删除所有交换机及关联数据 |
| GET | /api/switches/template | 下载导入模板 |
| POST | /api/switches/import | 批量导入 |
| GET | /api/results | 扫描结果（分页+过滤） |
| GET | /api/results/routes | 路由表（分页+过滤） |
| GET | /api/scan-logs | 扫描日志（分页+按数据源/状态过滤） |
| GET | /api/scan-logs/{id} | 扫描日志详情 |
| GET | /api/scan-logs/{id}/steps | 扫描步骤清单（分步进度 + 成功/失败状态） |
| GET | /api/scan-logs/{id}/output | 扫描终端输出（实时追加） |
| DELETE | /api/scan-logs/{id} | 删除单条扫描记录 |
| DELETE | /api/scan-logs | 批量清除（支持按数据源、按状态过滤） |
| WS | /ws/scan-progress | WebSocket 扫描进度实时推送（JWT 鉴权 + Redis Pub-Sub） |
| POST | /api/workers/register | Worker 注册（共享密钥认证，幂等） |
| POST | /api/workers/{id}/heartbeat | Worker 心跳上报 |
| POST | /api/workers/{id}/deregister | Worker 注销 |
| GET | /api/workers | Worker 列表（管理员，分页+筛选） |
| GET | /api/workers/{id} | Worker 详情（管理员） |
| DELETE | /api/workers/{id} | 删除 Worker 记录（管理员） |
| GET | /api/dashboard/stats | 仪表盘多源统计（含 vCenter/F5/ZDNS/椒图 嵌套数据） |
| GET | /api/dashboard/subnet-utilization | 地址段利用率 |
| GET | /api/dashboard/available-ips | 可用 IP 列表 |
| GET | /api/dashboard/subnet-occupied-ips | 子网已占用 IP 清单（分页，含交换机/MAC/VLAN） |
| GET | /api/dashboard/asset-details | 资产明细（域名/公网服务/内网服务，搜索） |
| GET | /api/dashboard/ip-mac-list | IP/MAC 去重列表 |
| GET | /api/dashboard/vm-details | VM 明细（分页+搜索） |
| CRUD | /api/subnets | 地址段管理 |
| GET | /api/search | 全局 IP/MAC 搜索 |
| GET | /api/history | 历史记录（分页+按数据源/设备/日期过滤） |
| GET | /api/history/ip/{ip} | 某 IP 的变更历史 |
| GET | /api/history/mac/{mac} | 某 MAC 的变更历史 |
| CRUD | /api/users | 用户管理（管理员，支持部门/工号筛选） |
| PUT | /api/users/{id}/reset-password | 重置用户密码（管理员） |
| GET | /api/sys/api-config | 获取 API 配置（管理员） |
| PUT | /api/sys/api-config | 保存 API 配置（管理员） |
| POST | /api/sys/api-config/test | 测试 API 连接（管理员） |
| POST | /api/sys/departments/sync | 同步组织机构（管理员） |
| GET | /api/sys/departments/tree | 组织树（管理员，支持仅显示有用户部门） |
| GET | /api/sys/departments/{id}/users | 部门下用户列表（管理员） |
| POST | /api/sys/staff/lookup | 教职工查询（管理员，OR 模糊匹配） |
| GET | /api/assets/departments/{id}/vms | 部门 VM 清单（分页/筛选/增强数据） |
| GET | /api/assets/departments/{id}/domains | 部门域名清单（去重/分页/类型筛选） |
| GET | /api/assets/search | 全局资产搜索（IP/MAC/VM名/域名） |
| GET | /api/assets/tree | 资产组织树（VM/Domain/System 三数字统计） |
| GET | /api/assets/vm-filters | VM 筛选选项 |
| GET | /api/assets/auto-match/preview | 自动关联预览 |
| POST | /api/assets/auto-match | 执行自动关联 |
| POST | /api/assets/claim | 资产认领 |
| POST | /api/assets/assign | 管理员指派 |
| CRUD | /api/vcenters | vCenter 管理 |
| POST | /api/vcenters/test | vCenter 连接测试 |
| POST | /api/vcenters/{id}/scan | 触发 vCenter 扫描 |
| POST | /api/vcenters/{id}/cancel-scan | 取消 vCenter 扫描 |
| POST | /api/vcenters/scan-all | 全部扫描 |
| DELETE | /api/vcenters/all | 删除所有 vCenter 及关联 VM 数据 |
| GET | /api/vcenters/vms | 全局 VM 清单（分页+过滤） |
| GET | /api/vcenters/{id}/vms | 某 vCenter 的 VM 清单 |
| GET | /api/vcenters/{id}/vm-filter-options | VM 过滤下拉选项 |
| GET | /api/vcenters/{id}/hosts | ESXi 主机清单 |
| GET | /api/vcenters/{id}/datastores | 存储器清单 |
| CRUD | /api/f5 | F5 设备管理 |
| POST | /api/f5/test | F5 连接测试 |
| POST | /api/f5/{id}/scan | 触发 F5 扫描 |
| POST | /api/f5/{id}/cancel-scan | 取消 F5 扫描 |
| POST | /api/f5/scan-all | 全部扫描 |
| DELETE | /api/f5/all | 删除所有 F5 设备及关联数据 |
| GET | /api/f5/{id}/virtual-servers | F5 虚拟服务器清单 |
| GET | /api/f5/{id}/pool-members | F5 Pool 成员清单 |
| GET | /api/f5/{id}/rules | F5 iRules 清单 |
| GET | /api/f5/{id}/application-map | F5 应用映射清单（核心接口） |
| CRUD | /api/zdns | ZDNS 设备管理 |
| POST | /api/zdns/test | ZDNS 连接测试 |
| POST | /api/zdns/{id}/scan | 触发 ZDNS 扫描 |
| POST | /api/zdns/{id}/cancel-scan | 取消 ZDNS 扫描 |
| POST | /api/zdns/{id}/cancel-ip-scan | 取消 ZDNS IP 扫描 |
| POST | /api/zdns/scan-all | 全部扫描 |
| DELETE | /api/zdns/all | 删除所有 ZDNS 设备及关联数据 |
| GET | /api/zdns/{id}/records | DNS 记录清单 |
| GET | /api/zdns/{id}/domain-map | 域名→IP 映射清单（核心接口） |
| POST | /api/zdns/{id}/ip-scan | 触发 IP 可达性扫描 |
| CRUD | /api/qax | 椒图设备管理 |
| POST | /api/qax/test | 椒图连接测试 |
| POST | /api/qax/{id}/scan | 触发椒图扫描 |
| POST | /api/qax/{id}/cancel-scan | 取消椒图扫描 |
| POST | /api/qax/scan-all | 全部扫描 |
| DELETE | /api/qax/all | 删除所有椒图设备及关联数据 |
| GET | /api/qax/{id}/servers | 椒图服务器清单（分页+搜索） |
| GET | /api/qax/{id}/servers/{sid}/ports | 某服务器的端口列表 |
| GET | /api/qax/{id}/servers/{sid}/processes | 某服务器的进程列表 |
| GET | /api/qax/{id}/servers/{sid}/software | 某服务器的软件列表 |
| GET | /api/asset-profile | 资产画像（跨源关联+统计+搜索+排序+分页） |
| GET | /api/version | 系统版本号（从 VERSION 文件读取） |
| CRUD | /api/info-systems | 信息系统维护（分页/搜索/筛选） |
| POST | /api/info-systems/import | 信息系统 Excel 导入 |
| GET | /api/info-systems/export | 信息系统 Excel 导出 |
| POST | /api/info-systems/sync-from-platform | 域名同步（匹配 ZDNS 数据） |
| CRUD | /api/info-systems/djdj | 等保备案记录维护 |
| POST | /api/info-systems/djdj/import | 等保 Excel 导入 |
| GET | /api/info-systems/djdj/export | 等保 Excel 导出 |
| POST | /api/info-systems/djdj/batch-delete | 等保批量删除 |
| CRUD | /api/info-systems/icp | ICP 备案记录维护 |
| POST | /api/info-systems/icp/import | ICP Excel 导入 |
| GET | /api/info-systems/icp/export | ICP Excel 导出 |
| CRUD | /api/info-systems/supply-chain | 供应链信息维护（分页/搜索） |
| POST | /api/info-systems/supply-chain/import | 供应链 Excel 导入（自动去重+行业名称适配） |
| GET | /api/info-systems/supply-chain/export | 供应链 Excel 导出 |
| POST | /api/info-systems/supply-chain/batch-delete | 供应链批量删除 |
| GET | /api/info-systems/supply-chain/names | 供应链单位名称列表（下拉联动） |
| GET | /api/info-systems/djdj-search | 等保系统名称搜索（信息系统自动补全） |
| GET | /api/sys/scheduler | 定时任务状态查看 |
| PUT | /api/sys/scheduler/{job_id} | 定时任务间隔修改 |

### 交换机配置

SNMP v2c，通过 Web 界面添加交换机（IP + community）。支持两种 MIB 模式：

- **标准 MIB** — IP-MIB + Q-BRIDGE-MIB + BRIDGE-MIB，适用于通用厂商
- **华为私有 MIB** — HUAWEI-L2MAM-MIB + HUAWEI-ARP-MIB，支持 BD/VPN 模式

Web 后端复用 `switchReader/switchReader.py` 的所有 SNMP 采集函数，每次扫描创建独立的 pysnmp Slim 实例。

### 开发阶段

**已完成：基础架构 + 全源采集层**

| 阶段 | 说明 | 状态 |
|------|------|------|
| Phase A | MySQL 数据库切换 + 本地开发模式 | ✅ |
| Phase B | Celery + Redis 异步任务队列（5→6 数据源独立队列） | ✅ |
| Phase C | 扫描步骤日志 + 实时监控面板（进度卡片/步骤详情/终端输出） | ✅ |
| Phase D | WebSocket 进度推送 + 前端稳定性修复（最终采用轮询方案） | ✅ |
| Phase E | Worker 容器化 + 注册认证（共享密钥/心跳/自动注销/水平扩容） | ✅ |
| Phase F | Worker 管理面板 + 调度增强（队列路由/并发计数/执行追溯/技能统一） | ✅ |
| Phase G | 版本管理 — VERSION 文件统一前后端 + Worker 版本号 | ✅ |
| Phase H | Redis 缓存优化 — 资产画像 5min + 仪表盘 30s TTL | ✅ |
| Phase J | 组织机构管理 + 账号体系升级 — 外部 API 对接/组织树/教职工验证/部门绑定 | ✅ |
| Phase K | 信息资产管理 — 资产-部门关联/自动匹配/资产认领/管理员指派/VM增强/域名去重 | ✅ |
| Phase L | CAS 统一身份认证 — 自动跳转 CAS 登录/票据验证/单点登出/本地密码登录备用 | ✅ |
| Phase M | 资产数据独立 — asset_inventory 表隔离管理数据与扫描数据 | ✅ |
| Phase N | 鼎甲备份系统对接 — REST API + Celery 任务队列 + 扫描日志 | ✅ |
| Phase O | 信息系统管理 — 信息系统/等保/ICP/供应链四大模块，Excel 导入导出，批量删除 | ✅ |

**已完成：功能模块**

| 模块 | 核心能力 | 状态 |
|------|---------|------|
| 项目脚手架 | Docker Compose + JWT 认证 + 角色权限 | ✅ |
| 交换机管理 | SNMP v2c 采集（标准 MIB + 华为私有 MIB），L2/L3 自动识别，ARP+FDB 合并，路由表 | ✅ |
| vCenter 管理 | pyVmomi 采集 VM/ESXi/Datastore，MAC↔IP 回填，存储类型分类 | ✅ |
| F5 管理 | iControl REST 采集 VS/Pool/iRules，应用映射（域名→VIP→Pool Member） | ✅ |
| ZDNS 管理 | REST API 采集 DNS 记录，域名→IP 映射，IP 可达性扫描（ping 探测） | ✅ |
| 椒图管理 | 云锁 REST API 采集服务器/端口/进程/软件，三级详情 | ✅ |
| 仪表盘 | 多源统计卡片 + 环形图/饼图/地址段利用率 + 点击下探 | ✅ |
| 资产画像 | 五源关联（ZDNS→F5→vCenter→交换机→椒图），完整链路追踪，Excel 导出 | ✅ |
| 扫描监控 | 6 类数据源实时进度卡片 + 步骤详情 + 终端输出 + Worker 执行追溯 | ✅ |
| 扫描日志 | 统一多源扫描记录，按数据源/状态筛选，批量清除 | ✅ |
| 地址段管理 | CRUD + IP 可用性计算 + 利用率统计 + 已占用 IP 明细 | ✅ |
| 全局搜索 | IP/MAC 精确+模糊搜索，资产画像优先 + 扫描结果兜底 | ✅ |
| 变更历史 | 五源复合键追踪，字段级新旧值对比，Tab 式切换 | ✅ |
| 用户管理 | JWT + bcrypt，admin/user 角色，管理员 CRUD/重置密码/启用禁用，本校/校外类型 | ✅ |
| 组织机构管理 | 外部 API 同步院系所，树形展示（含上级），部门→用户关联，教职工验证 | ✅ |
| 信息资产管理 | VM/域名/信息系统关联部门，自动匹配(vm_folder→部门编码)，管理员指派（人员搜索+部门同步），资产同步（新增标记unlinked+僵尸清理），文件夹树（/分隔路径，隐藏空节点，随部门联动），默认排序（资源池→名称→电源），外链填报（加密token+可选密码+过期时间+独立认证+外部填报保存） | ✅ |
| 系统管理 | API 配置管理，菜单分组（资产管理/扫描分析/系统管理子菜单） | ✅ |
| 定时调度 | APScheduler 按设备独立间隔自动触发，卡住自动重置 | ✅ |

**待开发：治理与运维层**

| 阶段 | 说明 | 状态 |
|------|------|------|
| Phase I | 远程部署 Worker（SSH/Docker Remote API） | 🔲 下一步 |
| 信息系统管理 | 信息系统台账/等保备案/ICP备案/供应链信息维护，Excel 导入导出，域名自动同步 | ✅ |
| 合同管理 | 合同原文及主要信息录入，合同有效期管理 | 🔲 |
| 人员管理 | CAS 对接，无本系统账号禁止登录 | ✅ |
| 组织架构 | API 获取组织架构基本信息，部门/岗位/层级同步 | ✅ |
| 资源关联 | 现有资源（信息系统/管理人/供应链）多向关联映射 | 🔲 |
| 供应链信息采集 | 公网加密链接 + 短信提醒 + 一次性密码填写 | 🔲 |
| 信息资产认领 | 三级权限管理，主管领导设置，资产画像权限继承 | 🔲 |
| 数据库/前端管理 | Oracle/MySQL/Redis 等数据库信息 + Web 前端信息录入 | 🔲 |
| 监控系统对接 | 信息资产自动发布到监控系统，建立规范化监控体系 | 🔲 |
| 系统运行状态检测 | 系统拓扑图，数据库/前端/DNS/负载均衡/CPU/内存/磁盘等指标 | 🔲 |
| 监控大屏 | 服务器虚拟化系统整体运行状态可视化展示 | 🔲 |
| 信息告警 | 系统级监控告警，覆盖服务器/虚拟机/域名/负载均衡/响应性能 | 🔲 |
| Phase I | 远程部署 Worker（SSH/Docker Remote API） | 🔲 远期 |
