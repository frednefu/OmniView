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
- **Worker 容器化** — Celery Worker 独立 Docker 部署 + 共享密钥注册认证 + 心跳监控，支持多实例水平扩容
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

#### Worker 独立部署

```bash
# 单独启动 Worker 容器（连接已有 MySQL + Redis）
docker-compose -f docker-compose.worker.yml up -d

# 扩容到 3 个 Worker 实例
docker-compose -f docker-compose.worker.yml up -d --scale worker=3

# 环境变量需在 .env 中配置 WORKER_TOKEN（与 API 服务器一致）
```

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
│   │   ├── views/               # Login, Dashboard, SwitchList/Detail, VCenterList/Detail, F5List/Detail, ZDNSList/Detail, QAXList/Detail, Results, Routes, SubnetManage, SearchResult, ScanLogs, ScanMonitor, History, AssetProfile, UserManage, Profile
│   │   ├── components/          # AppLayout, SwitchFormDialog, VCenterFormDialog, F5FormDialog, ZDNSFormDialog
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
| CRUD | /api/users | 用户管理（管理员） |
| PUT | /api/users/{id}/reset-password | 重置用户密码（管理员） |
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

### 交换机配置

SNMP v2c，通过 Web 界面添加交换机（IP + community）。支持两种 MIB 模式：

- **标准 MIB** — IP-MIB + Q-BRIDGE-MIB + BRIDGE-MIB，适用于通用厂商
- **华为私有 MIB** — HUAWEI-L2MAM-MIB + HUAWEI-ARP-MIB，支持 BD/VPN 模式

Web 后端复用 `switchReader/switchReader.py` 的所有 SNMP 采集函数，每次扫描创建独立的 pysnmp Slim 实例。

### 开发阶段

| 阶段 | 状态 |
|------|------|
| Phase A: MySQL 数据库切换 | ✅ |
| Phase B: Celery + Redis 异步任务队列 | ✅ |
| Phase 1: 项目脚手架 + Docker + 认证 | ✅ |
| Phase 2: 交换机管理 + SNMP 扫描 | ✅ |
| Phase 3: 仪表盘 + 地址段 + IP 搜索 | ✅ |
| Phase 4: 历史追踪（IP↔MAC 变更记录） | ✅ |
| Phase 5: 定时任务 + 用户管理 + 个人中心 | ✅ |
| Phase 6: vCenter 虚拟机清单采集 | ✅ |
| Phase 7: 历史记录优化 — 数据源分离 + 去重优化 + vCenter/F5/ZDNS 历史 | ✅ |
| Phase 8: F5 负载均衡管理 — 设备管理 + iControl REST 扫描 + 应用映射 + 历史追踪 | ✅ |
| Phase 9: ZDNS 域名服务器管理 — 设备管理 + API 扫描 + 域名→IP 映射 + 历史追踪 | ✅ |
| Phase 10: 统一扫描日志 — 多数据源支持 + 分页 + 清除 + 扫描耗时记录 | ✅ |
| Phase 11: 仪表盘增强 — 多数据源统计卡片 + 环形图/饼图 + 点击下探 + 子网占用 IP | ✅ |
| Phase 12: 资产画像 — 跨源数据关联 + 完整链路 + 统计摘要 + 搜索排序 | ✅ |
| Phase 13: ZDNS IP 可达性扫描 — 在线状态判定 + ping 探测 + 定时调度 + 过滤筛选 | ✅ |
| Phase 14: 奇安信椒图集成 — 服务器清单采集 + 端口/进程/软件详情 + 定时调度 | ✅ |
| Phase 15: vCenter 增强采集 — VM 存储使用 + ESXi 主机信息 + Datastore 存储系统 + 仪表盘新图表 + 存储类型分类 | ✅ |
| Phase 16: 扫描监控面板 — 实时进度卡片 + 步骤详情 + 终端输出 + 单条删除/批量清除 + 增强扫描日志 | ✅ |
| Phase E: Worker 容器化 + 注册认证 — 独立 Docker 部署 + 共享密钥认证 + 心跳监控 + 水平扩容 | ✅ |
| Phase 17: 信息系统数据管理 — 导入信息系统数据，资产编号/采购编号/合同编号关联 | 🔲 待开发 |
| Phase 18: 合同管理 — 合同原文及主要信息录入，合同有效期管理 | 🔲 待开发 |
| Phase 19: 人员管理 — CAS 对接获取人员基本信息，工号与账号关联，仅管理员添加的工号获取人员信息 | 🔲 待开发 |
| Phase 20: 组织架构 — API 获取组织架构基本信息，部门/岗位/层级同步 | 🔲 待开发 |
| Phase 21: 资源关联 — 现有资源（信息系统/管理人/供应链）多向关联映射 | 🔲 待开发 |
| Phase 22: 供应链信息采集 — 公网加密链接生成 + 短信提醒 + 一次性密码填写（无需系统账号），密码有效期控制 | 🔲 待开发 |
| Phase 23: 信息资产认领 — 三级权限管理（管理员/部门管理员/普通用户），主管领导与分管领导设置，资产类型（域名/虚拟服务器/信息系统/数据库/应用系统/中间件），资产画像关联链路权限自动继承 | 🔲 待开发 |
| Phase 24: 数据库信息管理 — 支持 Oracle/MySQL/Redis/MSSQL 等多种数据库，与主机关联 | 🔲 待开发 |
| Phase 25: Web 前端管理 — Web 前端信息录入，与主机关联 | 🔲 待开发 |
| Phase 26: 监控系统对接 — 信息资产自动发布到监控系统，建立规范化监控体系 | 🔲 待开发 |
| Phase 27: 系统运行状态检测 — 系统组成拓扑图，数据库/前端/DNS/负载均衡/CPU/内存/磁盘/IOPS/会话数等运行指标 | 🔲 待开发 |
| Phase 28: 监控大屏 — 服务器虚拟化系统整体运行状态可视化展示 | 🔲 待开发 |
| Phase 29: 信息告警 — 系统级监控告警，覆盖服务器/虚拟机/域名/负载均衡/响应性能，实时告警通知 | 🔲 待开发 |
