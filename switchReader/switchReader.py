import asyncio
import json
import os
import sys
import pandas as pd
from pysnmp.hlapi.v1arch import (
    Slim,
    ObjectType,
    ObjectIdentity,
)
from concurrent.futures import ThreadPoolExecutor

# ============================================================
# 配置：从外部 JSON 文件加载
# ============================================================

def _load_config():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, 'config.json')
    example_path = os.path.join(script_dir, 'config.example.json')

    if not os.path.exists(config_path):
        print(f"配置文件不存在：{config_path}")
        print(f"请复制 {config_path} 参考 {example_path} 模板创建。")
        print(f"  cp {example_path} {config_path}")
        sys.exit(1)

    with open(config_path, 'r', encoding='utf-8') as f:
        cfg = json.load(f)

    return {
        'switches': cfg['switches'],
        'snmp_port': cfg.get('snmp_port', 161),
        'snmp_timeout': cfg.get('snmp_timeout', 3),
        'snmp_retries': cfg.get('snmp_retries', 2),
        'max_workers': cfg.get('max_workers', 5),
        'walk_limit': cfg.get('walk_limit', 10000),
    }

_config = _load_config()

# 交换机列表
#   每项字段：
#     ip:        交换机管理 IP 地址
#     community: SNMP v2c 读团体字（read community string）
#     mib:       FDB 表优先使用的 MIB 库，可选值:
#                "huawei"  — 优先使用华为私有 MIB (HUAWEI-L2MAM)，支持 BD 模式
#                "standard" — 优先使用标准 MIB (Q-BRIDGE)，适用于非华为交换机
#                省略时默认 "standard"
SWITCH_CONFIGS = _config['switches']

SNMP_PORT    = _config['snmp_port']
SNMP_TIMEOUT = _config['snmp_timeout']
SNMP_RETRIES = _config['snmp_retries']
MAX_WORKERS  = _config['max_workers']
WALK_LIMIT   = _config['walk_limit']

# ============================================================
# SNMP OID 定义
# ============================================================

# -- 系统 --
OID_SYS_SERVICES = '1.3.6.1.2.1.1.7.0'       # sysServices（辅助判断交换机类型）

# -- ARP 表 (IP-MIB, 仅三层交换机有) --
OID_ARP_PHYS_ADDRESS = '1.3.6.1.2.1.4.22.1.2'  # ipNetToMediaPhysAddress（IP → MAC）

# -- 接口名称 --
OID_IF_NAME  = '1.3.6.1.2.1.31.1.1.1.1'  # ifName（优先使用）
OID_IF_DESCR = '1.3.6.1.2.1.2.2.1.2'     # ifDescr（ifName 不可用时回退）

# -- 桥端口号 → ifIndex 映射 (标准 MIB 路径需要) --
OID_BRIDGE_PORT_IFINDEX = '1.3.6.1.2.1.17.1.4.1.2'  # dot1dBasePortIfIndex

# ---- 标准 MIB: MAC 转发表 ----
# Q-BRIDGE-MIB（VLAN 感知，优先）
OID_QBRIDGE_FDB_PORT = '1.3.6.1.2.1.17.7.1.2.2.1.2'  # dot1qTpFdbPort
# BRIDGE-MIB（无 VLAN 信息，最终回退）
OID_BRIDGE_FDB_PORT = '1.3.6.1.2.1.17.4.3.1.2'  # dot1dTpFdbPort

# ---- 华为私有 MIB: MAC 转发表 (HUAWEI-L2MAM-MIB) ----
# 优势：同时支持 VLAN 和 Bridge-Domain 模式，且直接给出 ifIndex 无需桥端口映射
# OID 前缀: 1.3.6.1.4.1.2011 (华为企业号)
# 列 OID = hwL2MacDynamicEntry(.42.2.1) + column_number
OID_HW_L2MAC_ENTRY      = '1.3.6.1.4.1.2011.5.25.42.2.1'      # hwL2MacDynamicEntry
OID_HW_L2MAC_IFINDEX    = '1.3.6.1.4.1.2011.5.25.42.2.1.3'    # hwL2MacIfIndex（接口索引）
OID_HW_L2MAC_VLAN_TYPE  = '1.3.6.1.4.1.2011.5.25.42.2.1.5'    # hwL2MacVlanType（1=VLAN, 2=BD）

# ---- 华为私有 MIB: ARP 表 (HUAWEI-ARP-MIB) ----
# 当标准 IP-MIB ARP 在 VPN 实例下不可用时，使用华为私有 ARP MIB
OID_HW_ARP_ENTRY        = '1.3.6.1.4.1.2011.5.25.38.2'        # hwARPDynEntry (column .2)

# ============================================================
# SNMP 工具 (pysnmp 7.x 异步, 使用 Slim API)
# ============================================================

async def _snmp_get_scalar(slim, ip, community, oid):
    """获取单个标量值，失败返回 None。"""
    err, err_status, err_idx, varBinds = await slim.get(
        community, ip, SNMP_PORT,
        ObjectType(ObjectIdentity(oid)),
        timeout=SNMP_TIMEOUT, retries=SNMP_RETRIES,
    )
    if err or err_status:
        return None
    return varBinds[0][1] if varBinds else None


async def _snmp_walk(slim, ip, community, oid):
    """使用 Slim.next 循环遍历 OID 子树，返回 {OID字符串: 值} 字典。"""
    data = {}
    next_vb = ObjectType(ObjectIdentity(oid))

    for _ in range(WALK_LIMIT):
        err, err_status, err_idx, varBinds = await slim.next(
            community, ip, SNMP_PORT,
            next_vb,
            timeout=SNMP_TIMEOUT, retries=SNMP_RETRIES,
        )
        if err or err_status:
            break
        if not varBinds:
            break
        for vb in varBinds:
            oid_str = str(vb[0])
            if not oid_str.startswith(oid + '.') and oid_str != oid:
                return data  # 已走出目标子树
            data[oid_str] = vb[1]
            next_vb = ObjectType(ObjectIdentity(oid_str))

    return data


# ============================================================
# 索引 / 值解析
# ============================================================

def parse_ip_from_arp_index(oid_str):
    """从 ipNetToMediaEntry 索引中提取 IP 地址。

    索引格式: <base>.ifIndex.a.b.c.d
    返回: "a.b.c.d" 或 None
    """
    parts = oid_str.split('.')
    if len(parts) >= 4:
        return '.'.join(parts[-4:])
    return None


def _format_mac(octet_parts):
    """十进制数字列表 → 'xx:xx:xx:xx:xx:xx'"""
    return ':'.join(f'{int(p):02x}' for p in octet_parts)


def _parse_standard_fdb_index(oid_str, base_oid):
    """从标准 MIB 的 FDB 表索引中提取 VLAN(如果存在)和 MAC。

    Q-BRIDGE-MIB: <base>.VLAN.m1.m2.m3.m4.m5.m6  (7 段 suffix)
    BRIDGE-MIB:   <base>.m1.m2.m3.m4.m5.m6        (6 段 suffix)

    返回: (vlan, mac_str) — vlan 在 BRIDGE-MIB 下为 None
    """
    suffix = oid_str[len(base_oid) + 1:]
    parts = suffix.split('.')
    if len(parts) == 7:
        return int(parts[0]), _format_mac(parts[1:7])
    elif len(parts) == 6:
        return None, _format_mac(parts)
    return None, None


def _parse_hw_fdb_index(oid_str, column_oid):
    """从华为 hwL2MacDynamicEntry 索引中提取 VLAN/BD ID 和 MAC。

    索引格式 (标准):   <column_oid>.VlanIndex.m1.m2.m3.m4.m5.m6
    索引格式 (CE6881H): <column_oid>.VlanIndex.m1.m2.m3.m4.m5.m6.x.y.z

    返回: (vlan_or_bd_id, mac_str) 或 (None, None)
    """
    suffix = oid_str[len(column_oid) + 1:]
    parts = suffix.split('.')
    if len(parts) >= 7:  # 至少 1 个 VLAN/BD ID + 6 个 MAC octet（后面可能还有额外字段）
        return int(parts[0]), _format_mac(parts[1:7])
    return None, None


def _hw_vlan_type_label(vlan_type_value):
    """华为 hwL2MacVlanType 数值 → 中文标签。

    1=VLAN, 2=BD(Bridge-Domain), 3=Super-VLAN, 4=Super-BD
    """
    mapping = {1: 'VLAN', 2: 'BD', 3: 'Super-VLAN', 4: 'Super-BD'}
    return mapping.get(int(vlan_type_value), f'Type{vlan_type_value}')


# ============================================================
# 接口名称映射
# ============================================================

async def _build_ifindex_names(slim, ip, community):
    """构建 ifIndex → 接口名称 映射（ifName 优先，不可用时回退到 ifDescr）。"""
    ifindex_to_name = {}
    for oid_str, val in (await _snmp_walk(slim, ip, community, OID_IF_NAME)).items():
        ifidx = oid_str.rsplit('.', 1)[-1]
        ifindex_to_name[ifidx] = str(val)
    if not ifindex_to_name:
        for oid_str, val in (await _snmp_walk(slim, ip, community, OID_IF_DESCR)).items():
            ifidx = oid_str.rsplit('.', 1)[-1]
            ifindex_to_name[ifidx] = str(val)
    return ifindex_to_name


async def _build_bridge_port_map(slim, ip, community, ifindex_names):
    """构建 bridgePort → 端口名称 映射（仅标准 MIB 路径需要）。

    链路: bridgePort(dot1dTpFdbPort) → ifIndex(dot1dBasePortIfIndex) → ifName
    """
    bridge_to_ifindex = {}
    for oid_str, val in (await _snmp_walk(slim, ip, community, OID_BRIDGE_PORT_IFINDEX)).items():
        bridge_port = oid_str.rsplit('.', 1)[-1]
        bridge_to_ifindex[bridge_port] = str(val)

    port_map = {}
    for bp, ifidx in bridge_to_ifindex.items():
        port_map[bp] = ifindex_names.get(ifidx, f"ifIndex{ifidx}")
    return port_map


# ============================================================
# FDB 获取：三级回退策略
# ============================================================

async def _get_fdb_huawei(slim, ip, community):
    """尝试华为私有 MIB (hwL2MacDynamicTable)。

    成功返回 dict: {mac: {"vlan": int, "port": str, "vlan_type": "VLAN"|"BD"|...}}
    失败返回 None
    """
    # 遍历 ifIndex 列
    ifindex_data = await _snmp_walk(slim, ip, community, OID_HW_L2MAC_IFINDEX)
    if not ifindex_data:
        return None

    # 遍历 VlanType 列
    vlan_type_data = await _snmp_walk(slim, ip, community, OID_HW_L2MAC_VLAN_TYPE)

    # 建立 ifIndex → 端口名称 映射（华为 MIB 直接给出 ifIndex）
    ifindex_names = await _build_ifindex_names(slim, ip, community)

    fdb = {}
    for oid_str, val in ifindex_data.items():
        vlan_id, mac = _parse_hw_fdb_index(oid_str, OID_HW_L2MAC_IFINDEX)
        if mac is None:
            continue
        ifidx = str(val)

        # 查找对应的 VlanType（1=VLAN, 2=BD 等）
        vlan_type_tag = ''
        for vt_oid, vt_val in vlan_type_data.items():
            vt_vlan, vt_mac = _parse_hw_fdb_index(vt_oid, OID_HW_L2MAC_VLAN_TYPE)
            if vt_vlan == vlan_id and vt_mac == mac:
                vlan_type_tag = _hw_vlan_type_label(vt_val)
                break

        port_name = ifindex_names.get(ifidx, f"ifIndex{ifidx}")
        fdb[mac] = {
            "vlan": vlan_id,
            "port": port_name,
            "vlan_type": vlan_type_tag,
        }

    return fdb


async def _get_fdb_standard(slim, ip, community):
    """尝试标准 MIB（Q-BRIDGE → BRIDGE）。

    成功返回 dict: {mac: {"vlan": int|None, "port": str, "vlan_type": ""}}
    失败返回 None
    """
    ifindex_names = await _build_ifindex_names(slim, ip, community)
    bridge_port_map = await _build_bridge_port_map(slim, ip, community, ifindex_names)

    # 优先 Q-BRIDGE-MIB
    fdb_raw = await _snmp_walk(slim, ip, community, OID_QBRIDGE_FDB_PORT)
    fdb_oid = OID_QBRIDGE_FDB_PORT
    if not fdb_raw:
        # 回退到 BRIDGE-MIB
        fdb_raw = await _snmp_walk(slim, ip, community, OID_BRIDGE_FDB_PORT)
        fdb_oid = OID_BRIDGE_FDB_PORT

    if not fdb_raw:
        return None

    fdb = {}
    for oid_str, val in fdb_raw.items():
        vlan, mac = _parse_standard_fdb_index(oid_str, fdb_oid)
        if mac is None:
            continue
        bridge_port = str(val)
        port_name = bridge_port_map.get(bridge_port, f"Port{bridge_port}")
        fdb[mac] = {
            "vlan": vlan,
            "port": port_name,
            "vlan_type": '',
        }
    return fdb


async def _get_fdb(slim, ip, community, mib_pref='standard'):
    """获取 FDB 表，按配置的 MIB 优先级获取。

    mib_pref='huawei':  华为 MIB → 标准 MIB
    mib_pref='standard': 标准 MIB (Q-BRIDGE → BRIDGE)
    """
    if mib_pref == 'huawei':
        # 华为设备：优先华为私有 MIB，更准确且支持 BD
        fdb = await _get_fdb_huawei(slim, ip, community)
        if fdb:
            print(f"  {ip}: 华为私有 MIB (HUAWEI-L2MAM)")
            return fdb
        # 回退标准 MIB
        fdb = await _get_fdb_standard(slim, ip, community)
        if fdb:
            print(f"  {ip}: 标准 MIB (Q-BRIDGE) [华为 MIB 不可用，已回退]")
            return fdb
    else:
        # 标准设备：优先标准 MIB
        fdb = await _get_fdb_standard(slim, ip, community)
        if fdb:
            print(f"  {ip}: 标准 MIB (Q-BRIDGE)")
            return fdb
        # 回退华为 MIB（可能实际是华为设备）
        fdb = await _get_fdb_huawei(slim, ip, community)
        if fdb:
            print(f"  {ip}: 华为私有 MIB (HUAWEI-L2MAM) [标准 MIB 不可用，已回退]")
            return fdb

    print(f"  {ip}: 未获取到任何 FDB 数据")
    return {}


# ============================================================
# 交换机类型检测
# ============================================================

async def _detect_switch_type(slim, ip, community):
    """检测交换机是二层还是三层。

    - 尝试遍历 ARP 表：有数据 → L3，无数据 → L2
    - sysServices 作为辅助参考
    """
    svc = await _snmp_get_scalar(slim, ip, community, OID_SYS_SERVICES)
    arp_data = await _snmp_walk(slim, ip, community, OID_ARP_PHYS_ADDRESS)

    if arp_data:
        print(f"  {ip} -> 三层交换机 (ARP 表可用)")
        return 'L3'
    else:
        svc_str = f", sysServices={svc}" if svc is not None else ""
        print(f"  {ip} -> 二层交换机 (无 ARP 表{svc_str})")
        return 'L2'


# ============================================================
# 二层交换机扫描
# ============================================================

async def _scan_l2_switch(slim, ip, community, mib_pref='standard'):
    """扫描二层交换机：仅获取 MAC 转发表 (MAC → VLAN/BD → 端口)。

    二层交换机不做 IP 路由，没有 ARP 表。
    """
    print(f"扫描二层交换机: {ip} ...")

    fdb = await _get_fdb(slim, ip, community, mib_pref)

    results = []
    for mac, info in fdb.items():
        results.append({
            "交换机IP": ip,
            "IP地址": "",
            "MAC地址": mac,
            "VLAN/BD": info.get("vlan"),
            "VLAN类型": info.get("vlan_type", ""),
            "端口": info["port"],
            "交换机类型": "二层",
        })
    return results


# ============================================================
# 三层交换机扫描
# ============================================================

async def _scan_l3_switch(slim, ip, community, mib_pref='standard'):
    """扫描三层交换机：ARP 表 (IP→MAC) + MAC 转发表 (MAC→VLAN/BD/端口) 合并输出。"""
    print(f"扫描三层交换机: {ip} ...")

    # 1. ARP 表: MAC → IP 映射，同时获取接口索引
    # ipNetToMediaIfIndex (OID 1.3.6.1.2.1.4.22.1.1) 给出每个 ARP 条目的出接口
    OID_ARP_IFINDEX = '1.3.6.1.2.1.4.22.1.1'
    ifindex_names = await _build_ifindex_names(slim, ip, community)

    arp_table = {}     # MAC → IP
    arp_ifindex = {}   # MAC → 端口名 (来自 ARP 表自身的接口索引)
    arp_ifindex_raw = await _snmp_walk(slim, ip, community, OID_ARP_IFINDEX)

    arp_phys_raw = await _snmp_walk(slim, ip, community, OID_ARP_PHYS_ADDRESS)
    for oid_str, val in arp_phys_raw.items():
        ip_addr = parse_ip_from_arp_index(oid_str)
        if ip_addr is None:
            continue
        mac_bytes = val.asOctets()
        mac_str = ':'.join(f'{b:02x}' for b in mac_bytes)
        arp_table[mac_str] = ip_addr

        # 从 ARP 接口索引表中获取对应接口
        # arp_ifindex_raw 的 OID 格式与 arp_phys_raw 相同 (同一条目的不同列)
        # 通过替换列号来查找: ipNetToMediaIfIndex (.1) vs ipNetToMediaPhysAddress (.2)
        ifidx_oid_str = oid_str.replace(OID_ARP_PHYS_ADDRESS, OID_ARP_IFINDEX)
        ifidx_val = arp_ifindex_raw.get(ifidx_oid_str)
        if ifidx_val is not None:
            arp_ifindex[mac_str] = ifindex_names.get(str(ifidx_val), f"ifIndex{ifidx_val}")

    if not arp_table:
        print(f"  {ip}: ARP 表为空")
        return []

    # 2. FDB 表（按配置的 MIB 优先级）
    fdb = await _get_fdb(slim, ip, community, mib_pref)

    # 3. 合并: ARP 中的每个 IP-MAC 对 + FDB 补齐
    results = []
    for mac, ip_addr in arp_table.items():
        fdb_info = fdb.get(mac, {})
        # 端口优先用 FDB 的，没有则用 ARP 表自带的 ifIndex
        port = fdb_info.get("port") or arp_ifindex.get(mac, "")
        results.append({
            "交换机IP": ip,
            "IP地址": ip_addr,
            "MAC地址": mac,
            "VLAN/BD": fdb_info.get("vlan"),
            "VLAN类型": fdb_info.get("vlan_type", ""),
            "端口": port,
            "交换机类型": "三层",
        })

    # 补充 FDB 中 ARP 里没有的条目（被动设备、静默终端等）
    for mac, fdb_info in fdb.items():
        if mac not in arp_table:
            results.append({
                "交换机IP": ip,
                "IP地址": "",
                "MAC地址": mac,
                "VLAN/BD": fdb_info.get("vlan"),
                "VLAN类型": fdb_info.get("vlan_type", ""),
                "端口": fdb_info.get("port", ""),
                "交换机类型": "三层",
            })

    return results


# ============================================================
# 单交换机扫描入口
# ============================================================

async def _async_scan_switch(config):
    """单台交换机的完整异步扫描流程。"""
    ip = config['ip']
    community = config['community']
    mib_pref = config.get('mib', 'standard')  # 默认使用标准 MIB

    slim = Slim()
    try:
        switch_type = await _detect_switch_type(slim, ip, community)

        if switch_type == 'L3':
            return await _scan_l3_switch(slim, ip, community, mib_pref)
        else:
            return await _scan_l2_switch(slim, ip, community, mib_pref)
    finally:
        slim.close()


def scan_switch(config):
    """同步包装：每个线程内运行独立的 asyncio 事件循环。"""
    return asyncio.run(_async_scan_switch(config))


# ============================================================
# 主入口
# ============================================================

def main():
    all_data = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(scan_switch, sw): sw for sw in SWITCH_CONFIGS}
        for future in futures:
            sw = futures[future]
            try:
                all_data.extend(future.result())
            except Exception as e:
                print(f"扫描交换机 {sw['ip']} 失败: {e}")

    if all_data:
        df = pd.DataFrame(all_data)
        # 将 VLAN/BD 列转为可空整数，避免 Excel 中显示为 1.0 等浮点数
        df['VLAN/BD'] = df['VLAN/BD'].astype('Int64')
        df.to_excel("network_report.xlsx", index=False)
        print(f"\n扫描完成，共 {len(all_data)} 条记录，已保存至 network_report.xlsx")
    else:
        print("\n未获取到任何数据，请检查交换机配置和 SNMP community。")


if __name__ == "__main__":
    main()
