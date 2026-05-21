# switchReader

通过 SNMP 从网管交换机自动读取 IP / MAC / VLAN / 端口对应关系，输出 Excel 报表。  
最终目标：构建企业 IP 地址管理（IPAM）系统，通过 Web 界面直观管理 IP 资源。

## 当前功能

- 支持 **二层和三层交换机** 自动识别
- 并发扫描多台交换机（线程池），单次运行全覆盖
- 输出 ARP 表（IP → MAC）与 MAC 转发表（MAC → VLAN/端口）的合并结果
- 支持 **华为 SDN 交换机**（CE 系列）私有 MIB（HUAWEI-L2MAM），含 VLAN 和 BD（Bridge-Domain）双模式
- 支持 **标准 MIB** 交换机（Q-BRIDGE / BRIDGE），适用于其他厂商设备
- MIB 三级回退策略：华为私有 MIB → Q-BRIDGE-MIB → BRIDGE-MIB
- 输出字段：交换机IP、IP地址、MAC地址、VLAN/BD、VLAN类型、端口、交换机类型
- 结果保存为 `network_report.xlsx`（Excel 格式）

## 开发进展

| 阶段 | 状态 |
|------|------|
| SNMP 基础读取（ARP + FDB） | ✅ 已完成 |
| 华为 SDN 交换机私有 MIB 支持 | ✅ 已完成 |
| 交换机类型自动检测（L2/L3） | ✅ 已完成 |
| 多线程并发扫描 | ✅ 已完成 |
| MIB 探测工具（`huawei_mib_test.py`） | ✅ 已完成 |
| IP 地址使用率统计 | 🔜 计划中 |
| IP 历史占用 MAC 清单 | 🔜 计划中 |
| Web 管理界面 | 🔜 计划中 |

## 最终目标

构建完整的 IP 地址生命周期管理系统：

1. **自动采集** — 定期从交换机获取 IP-MAC-端口绑定信息
2. **IP 利用率** — 按地址段展示已用/可用 IP 比例，快速定位资源紧张的子网
3. **IP 状态视图** — 直观区分占用、空闲、预留 IP，支持搜索和筛选
4. **历史追溯** — 记录每个 IP 的历史 MAC 占用清单，了解哪些设备曾使用过该 IP
5. **Web 界面** — 浏览器中查看所有数据，替代 Excel 报表

## 运行环境

- Python 环境：conda 环境（pandas + pysnmp）
- SNMP v2c

```bash
python switchReader/switchReader.py
```

## 项目结构

```
switchReader/
├── switchReader.py        # 主程序：SNMP 扫描 + Excel 报表输出
└── huawei_mib_test.py     # 华为 MIB 探测工具：发现交换机支持哪些 OID
```

## 添加交换机

编辑 `switchReader/switchReader.py` 中的 `SWITCH_CONFIGS` 列表：

```python
{"ip": "192.168.1.1", "community": "public"},                     # 标准 MIB
{"ip": "192.168.1.2", "community": "public", "mib": "huawei"},    # 华为 SDN
```
