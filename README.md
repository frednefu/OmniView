# IPAM

企业级 IP 地址管理与资产发现系统。通过集成多种 IT 基础设施接口，实现对网络设备、虚拟化平台、应用交付设备及域名服务的自动化数据采集与集中化管理。

### 核心能力

- **多源数据采集** — SNMP / vSphere API / iControl REST / ZDNS API 等多种协议，主动同步交换机、vCenter、F5、DNS 资源
- **全链路资产映射** — 自动梳理"物理端口 → 虚拟化平台 → 业务负载 → 域名"的完整关系
- **实时变更追踪** — 以复合键增量 diff，记录字段级新旧值对比，支持回查历史
- **Web 可视化管控** — 仪表盘统计、地址段利用率图表、全局 IP/MAC 搜索、多维度过滤

## 技术栈

| 层 | 技术 |
|---|------|
| 后端框架 | FastAPI (Python 3.10+) |
| ORM | SQLAlchemy 2.0 |
| 数据库 | MySQL 8.0 / SQLite (开发) |
| SNMP | pysnmp 7.1+ (Slim API) |
| vCenter | pyVmomi 9.1+ (VMware vSphere SDK) |
| F5 | iControl REST API (HTTPS + Basic Auth) |
| ZDNS | REST API (HTTPS + Basic Auth, GET with body) |
| 前端 | Vue.js 3 + Element Plus + ECharts |
| 部署 | Docker Compose (MySQL + Redis + backend + frontend) |

## 功能

- **仪表盘** — 全栈资源概览，集成交换机/vCenter/F5/ZDNS/椒图 多数据源统计卡片（点击弹出明细对话框：域名/公网服务/内网服务/IP地址/MAC地址/虚拟机，含搜索），VM 开关机/Pool 状态/DNS 记录类型/扫描次数 环形图与饼图，地址段利用率图表点击下探已占用 IP 明细，椒图/vCenter OS 分布 + CPU 核数/内存容量/ESXi CPU 类型/存储容量 多维度图表，扫描成功率摘要，可用 IP 查询
- **交换机管理** — CRUD、批量导入(Excel/CSV)、模板下载、SNMP 连接测试、扫描状态/结果展示、全部扫描/全部删除
- **SNMP 扫描** — 自动识别 L2/L3 交换机，支持标准 MIB 和华为私有 MIB，ARP+FDB 数据合并，空 IP 自动回填
- **扫描结果** — 主机信息（IP/MAC/VLAN/端口/交换机来源）翻页列表（自动去重显示最新）、路由表翻页列表
- **扫描日志** — 统一的扫描记录中心，支持按数据源（交换机/vCenter/F5/ZDNS）和状态筛选、分页、清除
- **地址段管理** — CRUD、IP 可用性计算、利用率统计
- **搜索** — 全局搜索二级策略（资产画像优先，扫描结果兜底），完整 IP 自动精确匹配（避免模糊搜索定位不准），MAC 模糊查找
- **历史记录** — 交换机以 (IP, MAC) 为复合键，vCenter 以 (VM名称, vCenter) 为复合键，F5 以 (VS名称, 域名, Pool) 为复合键，ZDNS 以 (域名, 记录类型) 为复合键，字段变化时自动记录新增/删除/修改，JSON change_detail 字段级新旧值对比，支持按 IP/MAC/VM名称/日期范围过滤，前端 Tab 式切换
- **用户认证** — JWT + bcrypt，admin/user 角色
- **用户管理** — 管理员可创建/编辑/删除/重置密码用户，搜索过滤，角色和状态管理
- **个人设置** — 修改邮箱、修改密码
- **定时扫描** — APScheduler 后台调度，按设备配置的扫描间隔自动触发采集
- **vCenter 管理** — CRUD、连接测试、pyVmomi 扫描采集虚拟机清单（18 个字段：数据中心/集群/ESXi/资源池/文件夹/名称/电源/IP/MAC/网络/VLAN/OS/CPU/内存/存储/备注），扫描后自动通过 MAC 匹配交换机数据回填缺失 IP，支持多字段搜索 + 电源/OS/网络/文件夹下拉筛选
- **vCenter ESXi 主机** — 自动采集 ESXi 主机信息（主机名/管理 IP/处理器类型/逻辑处理器数/内存/Hypervisor 类型/物理网卡数/连接状态），独立 Tab 展示
- **vCenter 存储器** — 自动采集 Datastore 信息（名称/状态/类型/总容量/可用空间/挂载主机数/存储类别），使用率进度条可视化，自动识别共享存储（多主机挂载）、共享NAS（NFS 类型多主机挂载）、本地存储（单主机挂载），仪表盘按存储类型分组统计容量
- **VM 清单** — 独立 `vm_inventory` 表，按 vCenter/VM 名称/IP 搜索过滤，分页展示
- **F5 负载均衡管理** — CRUD、连接测试、iControl REST API 扫描采集虚拟服务器+Pool成员+iRules，自动构建域名→VS IP:端口→Pool 成员 IP:端口的应用映射清单，支持搜索（域名/VS名称/IP/端口/Pool/成员IP/iRule），定时扫描，历史变更追踪
- **F5 原始数据** — 虚拟服务器、Pool 成员（含 up/down 状态）、iRules（含 TCL 脚本内容）三个 Tab 各自支持搜索和分页
- **ZDNS 域名管理** — CRUD、连接测试、REST API 分页采集 DNS 记录（视图/区/记录），自动生成域名→IP 映射清单（IPv4/IPv6 + 内网/外网自动分类），定时扫描，历史变更追踪
- **ZDNS 原始数据** — DNS 记录和域名→IP 映射清单两个 Tab 各自支持搜索和分页，域名清单支持按记录类型/启用状态/IP 状态筛选
- **ZDNS IP 可达性扫描** — 自动关联交换机和 F5 数据判定 IP 在线状态（在线/离线/禁用/待定），支持一键 ping 探测和定时 IP 扫描，独立扫描间隔配置
- **资产画像** — 跨 ZDNS/F5/vCenter/交换机 四源数据关联，按 Pool（域名+公网IP:端口）聚合分组；F5 Rules/Pool 双模式识别（Pool 模式 VS 伪域名显示"不确定"），内网服务 IP:端口+状态合并展示（彩色标签），8 枚统计卡片（ZDNS域名/F5域名/公网IP端口/内网服务/虚拟机/VM IP/VLAN/文件夹，前端去重），多维度筛选（来源精确匹配/状态/网络名称下拉，选项动态生成），全局搜索，多列排序，前端分页
- **奇安信椒图管理** — CRUD、连接测试、REST API 批量采集服务器清单（名称/IP/OS/CPU/内存/磁盘/在线状态/分组），自动采集端口（端口号/协议/进程名/启动用户）/进程（进程名/PID/用户/CPU%/内存%）/软件（名称/版本/安装路径）三级详情，定时扫描（默认 24 小时），扫描日志

## 快速开始

```bash
# 1. 启动全部服务
docker-compose up -d

# 2. 初始化种子数据
docker-compose exec backend python seed.py

# 3. 访问
# 前端: http://localhost
# API 文档: http://localhost:8000/docs
```

默认账号：`admin` / `Admin123!`、`viewer` / `Viewer123!`

### 本地开发

```bash
# 后端 (SQLite)
cd backend
cp .env.example .env  # 编辑 DATABASE_URL=sqlite:///./ipam.db
pip install -r requirements.txt
python seed.py
uvicorn app.main:app --reload

# 前端
cd frontend
npm install
npm run dev
```

## 项目结构

```
├── docker-compose.yml
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI + lifespan
│   │   ├── config.py            # Pydantic Settings
│   │   ├── database.py          # SQLAlchemy engine
│   │   ├── models/              # User, Switch, ScanResult, RouteTable, ScanLog, Subnet, History, VCenter, VMInventory, EsxiHost, Datastore, F5*, ZDNS*, QAX*
│   │   ├── schemas/             # Pydantic 请求/响应
│   │   ├── api/                 # auth, switches, results, history, scan_logs, dashboard, subnets, search, users, vcenters, f5, zdns, asset_profile
│   │   ├── services/            # scanner_service, history_service, scheduler_service, vcenter_scanner_service, f5_scanner_service, zdns_scanner_service, zdns_ip_scanner_service, asset_profile_service
│   │   └── utils/               # security (JWT, bcrypt)
│   ├── seed.py                  # 默认用户初始化
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── views/               # Login, Dashboard, SwitchList, SwitchDetail, VCenterList, VCenterDetail, F5List, F5Detail, ZDNSList, ZDNSDetail, Results, Routes, SubnetManage, SearchResult, ScanLogs, History, UserManage, Profile
│   │   ├── components/          # AppLayout, SwitchFormDialog, VCenterFormDialog, F5FormDialog, ZDNSFormDialog
│   │   ├── api/                 # Axios 封装（auth, switches, results, history, scanLogs, users, vcenters, f5, zdns）
│   │   ├── store/               # Pinia auth
│   │   └── router/              # Vue Router（含 admin 角色守卫）
│   └── nginx.conf
└── switchReader/
    └── switchReader.py          # SNMP 采集引擎（Web 后端复用）
```

## API 路由

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/auth/login | 登录 |
| GET | /api/auth/me | 当前用户信息 |
| CRUD | /api/switches | 交换机管理 |
| POST | /api/switches/test | SNMP 连接测试 |
| POST | /api/switches/{id}/scan | 触发扫描（遇卡住的 running 自动重置） |
| POST | /api/switches/{id}/cancel-scan | 取消扫描（手动重置卡住的 running） |
| POST | /api/switches/scan-all | 全部扫描（所有启用交换机，自动重置卡住状态） |
| DELETE | /api/switches/all | 删除所有交换机及关联数据 |
| GET | /api/switches/template | 下载导入模板 |
| POST | /api/switches/import | 批量导入交换机 |
| GET | /api/results | 扫描结果（分页+过滤） |
| GET | /api/results/routes | 路由表（分页+过滤） |
| GET | /api/scan-logs | 扫描日志（分页+按数据源/状态过滤） |
| DELETE | /api/scan-logs | 清除扫描日志（支持按数据源过滤） |
| GET | /api/dashboard/stats | 仪表盘多源统计（含 vCenter/F5/ZDNS 嵌套数据） |
| GET | /api/dashboard/subnet-utilization | 地址段利用率 |
| GET | /api/dashboard/available-ips | 可用 IP 列表 |
| GET | /api/dashboard/subnet-occupied-ips | 子网已占用 IP 清单（分页，含交换机/MAC/VLAN，搜索） |
| GET | /api/dashboard/asset-details | 资产明细（域名/公网服务/内网服务，搜索） |
| GET | /api/dashboard/ip-mac-list | IP 或 MAC 去重列表（分页+搜索，独立去重） |
| GET | /api/dashboard/vm-details | VM 明细（分页+搜索，含完整字段） |
| CRUD | /api/subnets | 地址段管理 |
| GET | /api/search | IP/MAC 搜索 |
| GET | /api/history | 历史记录（分页+按数据源/设备/日期过滤） |
| GET | /api/history/ip/{ip} | 某 IP 的变更历史 |
| GET | /api/history/mac/{mac} | 某 MAC 的变更历史 |
| PUT | /api/auth/profile | 修改个人资料 |
| PUT | /api/auth/change-password | 修改密码 |
| CRUD | /api/users | 用户管理（管理员） |
| PUT | /api/users/{id}/reset-password | 重置用户密码（管理员） |
| CRUD | /api/vcenters | vCenter 管理 |
| POST | /api/vcenters/test | vCenter 连接测试 |
| POST | /api/vcenters/{id}/scan | 触发 vCenter 扫描（遇卡住的 running 自动重置） |
| POST | /api/vcenters/{id}/cancel-scan | 取消 vCenter 扫描（手动重置卡住的 running） |
| POST | /api/vcenters/scan-all | 全部扫描（所有启用 vCenter，自动重置卡住状态） |
| DELETE | /api/vcenters/all | 删除所有 vCenter 及关联 VM 数据 |
| GET | /api/vcenters/vms | 全局 VM 清单（分页+过滤） |
| GET | /api/vcenters/{id}/vms | 某 vCenter 的 VM 清单（分页+过滤） |
| GET | /api/vcenters/{id}/vm-filter-options | VM 过滤下拉选项（电源/OS/网络/文件夹） |
| GET | /api/vcenters/{id}/hosts | ESXi 主机清单 |
| GET | /api/vcenters/{id}/datastores | 存储器清单 |
| CRUD | /api/f5 | F5 设备管理 |
| POST | /api/f5/test | F5 连接测试 |
| POST | /api/f5/{id}/scan | 触发 F5 扫描（遇卡住的 running 自动重置） |
| POST | /api/f5/{id}/cancel-scan | 取消 F5 扫描（手动重置卡住的 running） |
| POST | /api/f5/scan-all | 全部扫描（所有启用 F5，自动重置卡住状态） |
| DELETE | /api/f5/all | 删除所有 F5 设备及关联数据 |
| GET | /api/f5/{id}/virtual-servers | F5 虚拟服务器清单（分页+搜索） |
| GET | /api/f5/{id}/pool-members | F5 Pool 成员清单（分页+搜索） |
| GET | /api/f5/{id}/rules | F5 iRules 清单（分页+搜索） |
| GET | /api/f5/{id}/application-map | F5 应用映射清单（核心接口） |
| CRUD | /api/zdns | ZDNS 设备管理 |
| POST | /api/zdns/test | ZDNS 连接测试 |
| POST | /api/zdns/{id}/scan | 触发 ZDNS 扫描（遇卡住的 running 自动重置） |
| POST | /api/zdns/{id}/cancel-scan | 取消 ZDNS 扫描（手动重置卡住的 running） |
| POST | /api/zdns/{id}/cancel-ip-scan | 取消 ZDNS IP 扫描（手动重置卡住的 IP running） |
| POST | /api/zdns/scan-all | 全部扫描（所有启用 ZDNS，自动重置卡住状态） |
| DELETE | /api/zdns/all | 删除所有 ZDNS 设备及关联数据 |
| GET | /api/zdns/{id}/records | ZDNS DNS 记录清单（分页+搜索） |
| GET | /api/zdns/{id}/domain-map | ZDNS 域名→IP 映射清单（核心接口，分页+搜索+过滤） |
| POST | /api/zdns/{id}/ip-scan | 触发 ZDNS IP 可达性扫描（ping 探测） |
| CRUD | /api/qax | 椒图设备管理 |
| POST | /api/qax/test | 椒图连接测试 |
| POST | /api/qax/{id}/scan | 触发椒图扫描（遇卡住的 running 自动重置） |
| POST | /api/qax/{id}/cancel-scan | 取消椒图扫描（手动重置卡住的 running） |
| POST | /api/qax/scan-all | 全部扫描（所有启用椒图，自动重置卡住状态） |
| DELETE | /api/qax/all | 删除所有椒图设备及关联数据 |
| GET | /api/qax/{id}/servers | 椒图服务器清单（分页+搜索） |
| GET | /api/qax/{id}/servers/{sid}/ports | 某服务器的端口列表 |
| GET | /api/qax/{id}/servers/{sid}/processes | 某服务器的进程列表 |
| GET | /api/qax/{id}/servers/{sid}/software | 某服务器的软件列表 |
| GET | /api/asset-profile | 资产画像（跨源关联+统计+搜索+排序+分页） |

## 交换机配置

SNMP v2c，通过 Web 界面添加交换机（IP + community）。支持两种 MIB 模式：

- **标准 MIB** — IP-MIB + Q-BRIDGE-MIB + BRIDGE-MIB，适用于通用厂商
- **华为私有 MIB** — HUAWEI-L2MAM-MIB + HUAWEI-ARP-MIB，支持 BD 模式

Web 后端复用了 `switchReader/switchReader.py` 的所有 SNMP 采集函数，每次扫描创建独立的 pysnmp Slim 实例。

## 开发阶段

| 阶段 | 状态 |
|------|------|
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
| Phase 15: vCenter 增强采集 — VM 存储使用 + ESXi 主机信息 + Datastore 存储系统 + 仪表盘新图表 | ✅ |
| Phase 16: 信息系统数据管理 — 导入信息系统数据，资产编号/采购编号/合同编号关联 | 🔲 待开发 |
| Phase 17: 合同管理 — 合同原文及主要信息录入，合同有效期管理 | 🔲 待开发 |
| Phase 18: 人员管理 — CAS 对接获取人员基本信息，工号与账号关联，仅管理员添加的工号获取人员信息 | 🔲 待开发 |
| Phase 19: 组织架构 — API 获取组织架构基本信息，部门/岗位/层级同步 | 🔲 待开发 |
| Phase 20: 资源关联 — 现有资源（信息系统/管理人/供应链）多向关联映射 | 🔲 待开发 |
| Phase 21: 供应链信息采集 — 公网加密链接生成 + 短信提醒 + 一次性密码填写（无需系统账号），密码有效期控制 | 🔲 待开发 |
| Phase 22: 信息资产认领 — 三级权限管理（管理员/部门管理员/普通用户），主管领导与分管领导设置，资产类型（域名/虚拟服务器/信息系统/数据库/应用系统/中间件），资产画像关联链路权限自动继承 | 🔲 待开发 |
| Phase 23: 数据库信息管理 — 支持 Oracle/MySQL/Redis/MSSQL 等多种数据库，与主机关联 | 🔲 待开发 |
| Phase 24: Web 前端管理 — Web 前端信息录入，与主机关联 | 🔲 待开发 |
| Phase 25: 监控系统对接 — 信息资产自动发布到监控系统，建立规范化监控体系 | 🔲 待开发 |
| Phase 26: 系统运行状态检测 — 系统组成拓扑图，数据库/前端/DNS/负载均衡/CPU/内存/磁盘/IOPS/会话数等运行指标 | 🔲 待开发 |
| Phase 27: 监控大屏 — 服务器虚拟化系统整体运行状态可视化展示 | 🔲 待开发 |
| Phase 28: 信息告警 — 系统级监控告警，覆盖服务器/虚拟机/域名/负载均衡/响应性能，实时告警通知 | 🔲 待开发 |
