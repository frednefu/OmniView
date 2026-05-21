# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**switchReader** — 通过 SNMP 从网管交换机读取 IP/MAC/VLAN/端口对应关系，输出 Excel 报表。

## Python 环境

需要 conda 环境（含 pandas + pysnmp）。

## 运行

```bash
python switchReader/switchReader.py
```

输出：项目根目录下的 `network_report.xlsx`。

## 交换机配置

复制模板文件并填入真实设备信息：

```bash
cp switchReader/config.example.json switchReader/config.json
# 编辑 switchReader/config.json，填入交换机 IP 和 SNMP community
```

`config.json` 格式：

```json
{
    "switches": [
        {"ip": "192.168.1.1", "community": "public", "mib": "huawei"},
        {"ip": "192.168.1.1", "community": "public"}
    ],
    "snmp_port": 161,
    "snmp_timeout": 3,
    "snmp_retries": 2,
    "max_workers": 5,
    "walk_limit": 10000
}
```

`mib` 字段可选：`"huawei"` 使用华为私有 MIB（支持 BD 模式），省略则使用标准 MIB。

## 架构

### 并发模型

`ThreadPoolExecutor` 多线程并发扫描多台交换机，每个线程内调用 `asyncio.run()` 运行独立的异步事件循环。

### SNMP 库：pysnmp 7.x（lextudio fork）

当前环境是 **pysnmp 7.1.27**，与旧版 pysnmp 4.x API 完全不同：

- 全部异步（async/await），没有同步 API
- 使用 `pysnmp.hlapi.v1arch.Slim` 封装（提供统一的 `get` / `next` 方法）
- `Slim.next` 循环遍历 OID 子树，替代旧版的 `bulkCmd` 生成器遍历
- `UdpTransportTarget.create((host, port), timeout=, retries=)` 必须用类方法创建
- **已知问题**：`bulk_walk_cmd` 在部分交换机上有 `ProtocolError: Error index out of range` 回调异常，已改用 `Slim.next` 手动 walk 规避

### 交换机类型检测（L2 vs L3）

函数 `_detect_switch_type()`：
- **策略**：遍历 ARP 表 OID（`1.3.6.1.2.1.4.22.1.2`），有数据 → L3，无数据 → L2
- 同时读取 `sysServices`（`1.3.6.1.2.1.1.7.0`）作为辅助参考
- L2 交换机只走 FDB 扫描（无 IP 信息），L3 交换机走 ARP + FDB 合并流程

### 关键 SNMP OID

| 用途 | OID | MIB |
|------|-----|-----|
| 系统服务层级 | `1.3.6.1.2.1.1.7.0` | sysServices |
| ARP 表（IP→MAC） | `1.3.6.1.2.1.4.22.1.2` | ipNetToMediaPhysAddress |
| FDB 转发端口（VLAN 感知） | `1.3.6.1.2.1.17.7.1.2.2.1.2` | dot1qTpFdbPort |
| FDB 转发端口（无 VLAN） | `1.3.6.1.2.1.17.4.3.1.2` | dot1dTpFdbPort（fallback） |
| 桥端口→ifIndex | `1.3.6.1.2.1.17.1.4.1.2` | dot1dBasePortIfIndex |
| 接口名称 | `1.3.6.1.2.1.31.1.1.1.1` | ifName（优先） |
| 接口描述 | `1.3.6.1.2.1.2.2.1.2` | ifDescr（fallback） |

### OID 索引解析

- **ARP 表索引**：`<base>.ifIndex.a.b.c.d`，取末尾 4 段得到 IP
- **Q-BRIDGE-MIB 索引**：`<base>.VLAN.m1.m2.m3.m4.m5.m6`，第 1 段是 VLAN ID，后 6 段是 MAC 的十进制 octet
- **BRIDGE-MIB 索引**：`<base>.m1.m2.m3.m4.m5.m6`，6 段 MAC 十进制 octet（无 VLAN）
- MAC octet 为十进制值，需 `f'{int(p):02x}'` 转为十六进制

### 端口映射链路

```
bridgePort (dot1dTpFdbPort 的值) → dot1dBasePortIfIndex → ifIndex → ifName/ifDescr
```

### 输出字段

| 字段 | 说明 |
|------|------|
| 交换机IP | 交换机管理 IP |
| IP地址 | 终端 IP（仅 L3 ARP 有，FDB 纯 MAC 条目为空） |
| MAC地址 | 终端 MAC |
| VLAN | VLAN ID（Q-BRIDGE-MIB 才有，BRIDGE-MIB fallback 为空） |
| 端口 | 接口名称 |
| 交换机类型 | 二层 / 三层 |

### 当前状态

已验证多台三层和华为 SDN 交换机。L2 交换机路径已实现（`_scan_l2_switch`）。
