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
OID_SYS_SERVICES = '1.3.6.1.2.1.1.7.0'

# -- 标准 ARP 表 (IP-MIB) --
OID_ARP_IFINDEX     = '1.3.6.1.2.1.4.22.1.1'  # ipNetToMediaIfIndex
OID_ARP_PHYS_ADDRESS = '1.3.6.1.2.1.4.22.1.2'  # ipNetToMediaPhysAddress

# -- 接口名称 --
OID_IF_NAME  = '1.3.6.1.2.1.31.1.1.1.1'  # ifName
OID_IF_DESCR = '1.3.6.1.2.1.2.2.1.2'     # ifDescr（fallback）

# -- 桥端口号 → ifIndex 映射 --
OID_BRIDGE_PORT_IFINDEX = '1.3.6.1.2.1.17.1.4.1.2'  # dot1dBasePortIfIndex

# -- 标准 MIB: MAC 转发表 --
OID_QBRIDGE_FDB_PORT = '1.3.6.1.2.1.17.7.1.2.2.1.2'  # dot1qTpFdbPort（VLAN 感知）
OID_BRIDGE_FDB_PORT  = '1.3.6.1.2.1.17.4.3.1.2'       # dot1dTpFdbPort（无 VLAN，回退）

# -- 华为私有 MIB: MAC 转发表 (HUAWEI-L2MAM-MIB) --
OID_HW_L2MAC_ENTRY      = '1.3.6.1.4.1.2011.5.25.42.2.1'      # hwL2MacDynamicEntry
OID_HW_L2MAC_IFINDEX    = '1.3.6.1.4.1.2011.5.25.42.2.1.3'    # hwL2MacIfIndex
OID_HW_L2MAC_VLAN_TYPE  = '1.3.6.1.4.1.2011.5.25.42.2.1.5'    # hwL2MacVlanType

# -- 华为私有 MIB: ARP 表 (HUAWEI-ARP-MIB) --
OID_HW_ARP_ENTRY   = '1.3.6.1.4.1.2011.5.25.38.2'            # hwARPDynEntry
OID_HW_ARP_IPADDR  = '1.3.6.1.4.1.2011.5.25.38.2.1.2'        # hwARPDynIPAddr
OID_HW_ARP_MACADDR = '1.3.6.1.4.1.2011.5.25.38.2.1.4'        # hwARPDynMACAddr

# -- 路由表 (IP-MIB) --
OID_ROUTE_DEST    = '1.3.6.1.2.1.4.21.1.1'   # ipRouteDest
OID_ROUTE_MASK    = '1.3.6.1.2.1.4.21.1.11'  # ipRouteMask
OID_ROUTE_NEXTHOP = '1.3.6.1.2.1.4.21.1.7'   # ipRouteNextHop
OID_ROUTE_IFINDEX = '1.3.6.1.2.1.4.21.1.2'   # ipRouteIfIndex
OID_ROUTE_TYPE    = '1.3.6.1.2.1.4.21.1.8'   # ipRouteType
OID_ROUTE_PROTO   = '1.3.6.1.2.1.4.21.1.9'   # ipRouteProto

# 路由协议常量
_ROUTE_TYPE = {3: '直连', 4: '非直连'}
_ROUTE_PROTO = {
    2: '本地', 8: 'RIP', 9: 'IS-IS', 13: 'OSPF', 14: 'BGP',
}
_ROUTE_TYPE_DEFAULT = '其他'
_ROUTE_PROTO_DEFAULT = '其他'

# ============================================================
# SNMP 工具 (pysnmp 7.x 异步, 使用 Slim API)
# ============================================================

async def _snmp_get_scalar(slim, ip, community, oid):
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
                return data
            data[oid_str] = vb[1]
            next_vb = ObjectType(ObjectIdentity(oid_str))

    return data


# ============================================================
# 工具
# ============================================================

import re

_CTRL_CHAR_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')

def _safe_str(value):
    """将 SNMP 返回值转为安全字符串，移除 Excel 不接受的非法字符。
    - pysnmp 的 IpAddress/OctetString 会正确转字符串
    - 但如果出现裸 bytes，则转为十六进制表示
    """
    if value is None:
        return ''
    if isinstance(value, bytes):
        # 裸字节：尝试解码，失败则转十六进制
        try:
            s = value.decode('ascii')
        except UnicodeDecodeError:
            return ':'.join(f'{b:02x}' for b in value)
    else:
        s = str(value)
    return _CTRL_CHAR_RE.sub('', s)


# ============================================================
# 索引 / 值解析
# ============================================================

def parse_ip_from_arp_index(oid_str):
    """从 ipNetToMediaEntry 索引中提取 IP 地址。
    索引格式: <base>.ifIndex.a.b.c.d，取末尾 4 段。"""
    parts = oid_str.split('.')
    if len(parts) >= 4:
        return '.'.join(parts[-4:])
    return None


def _bytes_to_ip(val):
    """Convert 4-byte SNMP value to dotted decimal IP string.
    Handles pysnmp OctetString, raw bytes, and already-formatted strings.
    """
    if val is None:
        return ''
    # pysnmp OctetString / IpAddress — try .asOctets() first
    if hasattr(val, 'asOctets'):
        raw = val.asOctets()
        if len(raw) == 4:
            return '.'.join(str(b) for b in raw)
        try:
            return raw.decode('ascii')
        except UnicodeDecodeError:
            return ':'.join(f'{b:02x}' for b in raw)
    if isinstance(val, bytes):
        if len(val) == 4:
            return '.'.join(str(b) for b in val)
        try:
            return val.decode('ascii')
        except UnicodeDecodeError:
            return ':'.join(f'{b:02x}' for b in val)
    s = str(val)
    return s


def _format_mac(octet_parts):
    """十进制数字列表 → 'xx:xx:xx:xx:xx:xx'"""
    return ':'.join(f'{int(p):02x}' for p in octet_parts)


def _parse_standard_fdb_index(oid_str, base_oid):
    """从标准 MIB FDB 表索引中提取 VLAN 和 MAC。
    Q-BRIDGE: <base>.VLAN.m1...m6 (7段)
    BRIDGE:   <base>.m1...m6 (6段)
    返回: (vlan, mac_str) — VLAN 在 BRIDGE-MIB 下为 None"""
    suffix = oid_str[len(base_oid) + 1:]
    parts = suffix.split('.')
    if len(parts) == 7:
        return int(parts[0]), _format_mac(parts[1:7])
    elif len(parts) == 6:
        return None, _format_mac(parts)
    return None, None


def _parse_hw_fdb_index(oid_str, column_oid):
    """从华为 hwL2MacDynamicEntry 索引中提取 VLAN/BD ID 和 MAC。
    索引格式: <column_oid>.VlanIndex.m1...m6[.x.y.z]
    返回: (vlan_or_bd_id, mac_str) 或 (None, None)"""
    suffix = oid_str[len(column_oid) + 1:]
    parts = suffix.split('.')
    if len(parts) >= 7:
        return int(parts[0]), _format_mac(parts[1:7])
    return None, None


def _hw_vlan_type_label(vlan_type_value):
    """华为 hwL2MacVlanType 数值 → 中文标签。"""
    mapping = {1: 'VLAN', 2: 'BD', 3: 'Super-VLAN', 4: 'Super-BD'}
    return mapping.get(int(vlan_type_value), f'Type{vlan_type_value}')


def _parse_hw_arp_index(oid_str, column_oid):
    """从华为 hwARPDynEntry 索引中提取 IP 地址。
    索引格式: <column_oid>.ifIndex.a.b.c.d[vpn_len.vpn_chars...]
    返回: ip_str 或 None"""
    suffix = oid_str[len(column_oid) + 1:]
    parts = suffix.split('.')
    if len(parts) >= 5:
        return '.'.join(parts[1:5])
    return None


def _route_oid_index_to_net(oid_str, column_oid):
    """从路由表 OID 索引中提取目标网络地址。
    索引格式: <column_oid>.a.b.c.d
    返回: "a.b.c.d" 或 None"""
    suffix = oid_str[len(column_oid) + 1:]
    parts = suffix.split('.')
    if len(parts) == 4:
        return suffix
    return None


def _subnet_mask_to_cidr(mask_str):
    """子网掩码 → CIDR 前缀长度，例如 '255.255.255.0' → 24"""
    try:
        parts = [int(x) for x in mask_str.split('.')]
        binary = ''.join(f'{p:08b}' for p in parts)
        return binary.count('1')
    except (ValueError, AttributeError):
        return None


# ============================================================
# 接口名称映射
# ============================================================

async def _build_ifindex_names(slim, ip, community):
    """构建 ifIndex → 接口名称 映射（ifName 优先，不可用时回退到 ifDescr）。"""
    ifindex_to_name = {}
    for oid_str, val in (await _snmp_walk(slim, ip, community, OID_IF_NAME)).items():
        ifidx = oid_str.rsplit('.', 1)[-1]
        ifindex_to_name[ifidx] = _safe_str(val)
    if not ifindex_to_name:
        for oid_str, val in (await _snmp_walk(slim, ip, community, OID_IF_DESCR)).items():
            ifidx = oid_str.rsplit('.', 1)[-1]
            ifindex_to_name[ifidx] = _safe_str(val)
    return ifindex_to_name


async def _build_bridge_port_map(slim, ip, community, ifindex_names):
    """构建 bridgePort → 端口名称 映射。
    链路: bridgePort → ifIndex(dot1dBasePortIfIndex) → ifName"""
    bridge_to_ifindex = {}
    for oid_str, val in (await _snmp_walk(slim, ip, community, OID_BRIDGE_PORT_IFINDEX)).items():
        bridge_port = oid_str.rsplit('.', 1)[-1]
        bridge_to_ifindex[bridge_port] = _safe_str(val)

    port_map = {}
    for bp, ifidx in bridge_to_ifindex.items():
        port_map[bp] = ifindex_names.get(ifidx, f"ifIndex{ifidx}")
    return port_map


# ============================================================
# FDB 合并获取：标准 MIB + 华为 MIB 合并，以 MAC 为键
# ============================================================

async def _get_fdb_standard(slim, ip, community):
    """读取标准 MIB FDB（Q-BRIDGE → BRIDGE 回退），返回 {mac: {vlan, 物理端口}}。"""
    ifindex_names = await _build_ifindex_names(slim, ip, community)
    bridge_port_map = await _build_bridge_port_map(slim, ip, community, ifindex_names)

    fdb_raw = await _snmp_walk(slim, ip, community, OID_QBRIDGE_FDB_PORT)
    fdb_oid = OID_QBRIDGE_FDB_PORT
    if not fdb_raw:
        fdb_raw = await _snmp_walk(slim, ip, community, OID_BRIDGE_FDB_PORT)
        fdb_oid = OID_BRIDGE_FDB_PORT

    if not fdb_raw:
        return None

    fdb = {}
    for oid_str, val in fdb_raw.items():
        vlan, mac = _parse_standard_fdb_index(oid_str, fdb_oid)
        if mac is None:
            continue
        bridge_port = _safe_str(val)
        port_name = bridge_port_map.get(bridge_port, f"Port{bridge_port}")
        fdb[mac] = {"vlan": vlan, "物理端口": port_name}
    return fdb


async def _get_fdb_huawei(slim, ip, community):
    """读取华为私有 MIB FDB（HUAWEI-L2MAM），返回 {mac: {vlan, 虚拟端口, vlan_type}}。"""
    ifindex_data = await _snmp_walk(slim, ip, community, OID_HW_L2MAC_IFINDEX)
    if not ifindex_data:
        return None

    vlan_type_data = await _snmp_walk(slim, ip, community, OID_HW_L2MAC_VLAN_TYPE)
    ifindex_names = await _build_ifindex_names(slim, ip, community)

    fdb = {}
    for oid_str, val in ifindex_data.items():
        vlan_id, mac = _parse_hw_fdb_index(oid_str, OID_HW_L2MAC_IFINDEX)
        if mac is None:
            continue
        ifidx = _safe_str(val)

        vlan_type_tag = ''
        for vt_oid, vt_val in vlan_type_data.items():
            vt_vlan, vt_mac = _parse_hw_fdb_index(vt_oid, OID_HW_L2MAC_VLAN_TYPE)
            if vt_vlan == vlan_id and vt_mac == mac:
                vlan_type_tag = _hw_vlan_type_label(vt_val)
                break

        port_name = ifindex_names.get(ifidx, f"ifIndex{ifidx}")
        fdb[mac] = {"vlan": vlan_id, "虚拟端口": port_name, "vlan_type": vlan_type_tag}
    return fdb


async def _get_fdb_merged(slim, ip, community, mib_pref='standard'):
    """合并标准 MIB 与华为 MIB 的 FDB 数据。

    - 标准 MIB 提供：物理端口 + VLAN
    - 华为 MIB 提供：虚拟端口 + VLAN/BD + vlan_type
    - 以 MAC 地址为键合并，两端信息互补
    """
    # 并行获取两份 FDB
    std_future = _get_fdb_standard(slim, ip, community)
    hw_future = _get_fdb_huawei(slim, ip, community) if mib_pref == 'huawei' else None

    fdb_std = await std_future
    fdb_hw = await hw_future if hw_future else None

    sources = []
    if fdb_std:
        sources.append("标准MIB")
    if fdb_hw:
        sources.append("华为MIB")
    print(f"  {ip}: FDB 合并 ({'+'.join(sources) if sources else '无数据'})")

    # 收集所有 MAC
    all_macs = set()
    if fdb_std:
        all_macs.update(fdb_std)
    if fdb_hw:
        all_macs.update(fdb_hw)

    merged = {}
    for mac in all_macs:
        std = fdb_std.get(mac, {}) if fdb_std else {}
        hw = fdb_hw.get(mac, {}) if fdb_hw else {}

        # VLAN: 标准 MIB 优先，华为 MIB 补充
        vlan = std.get("vlan") if std.get("vlan") is not None else hw.get("vlan")

        merged[mac] = {
            "VLAN/BD": vlan,
            "VLAN类型": hw.get("vlan_type", ""),
            "物理端口": std.get("物理端口", ""),
            "虚拟端口": hw.get("虚拟端口", ""),
        }

    return merged


# ============================================================
# ARP 合并获取：标准 IP-MIB + 华为 ARP MIB
# ============================================================

async def _get_arp_standard(slim, ip, community):
    """标准 ARP 表 (ipNetToMediaTable)，返回 {mac: ip}。"""
    arp_phys_raw = await _snmp_walk(slim, ip, community, OID_ARP_PHYS_ADDRESS)
    if not arp_phys_raw:
        return {}

    arp = {}
    for oid_str, val in arp_phys_raw.items():
        ip_addr = parse_ip_from_arp_index(oid_str)
        if ip_addr is None:
            continue
        mac_bytes = val.asOctets()
        mac_str = ':'.join(f'{b:02x}' for b in mac_bytes)
        arp[mac_str] = ip_addr
    return arp


async def _get_arp_huawei(slim, ip, community):
    """华为私有 ARP 表 (hwARPDynTable)，返回 {mac: ip}。"""
    arp_ip_raw = await _snmp_walk(slim, ip, community, OID_HW_ARP_IPADDR)
    arp_mac_raw = await _snmp_walk(slim, ip, community, OID_HW_ARP_MACADDR)
    if not arp_ip_raw or not arp_mac_raw:
        return {}

    arp = {}
    for oid_str, val in arp_ip_raw.items():
        ip_addr = _parse_hw_arp_index(oid_str, OID_HW_ARP_IPADDR)
        if ip_addr is None:
            continue
        # 用相同索引查找 MAC
        mac_oid = oid_str.replace(OID_HW_ARP_IPADDR, OID_HW_ARP_MACADDR)
        mac_val = arp_mac_raw.get(mac_oid)
        if mac_val is None:
            continue
        mac_str = ':'.join(f'{b:02x}' for b in mac_val.asOctets())
        arp[mac_str] = ip_addr
    return arp


async def _get_arp_merged(slim, ip, community):
    """合并标准 ARP 与华为 ARP。

    - 优先标准 ARP（IP 更准确）
    - 华为 ARP 补充 VPN 实例等场景下的缺失条目
    - 以 MAC 去重：同一 MAC 出现多次时保留最先出现的 IP
    """
    arp_std = await _get_arp_standard(slim, ip, community)
    arp_hw = await _get_arp_huawei(slim, ip, community)

    # 合并：标准优先，华为补充
    merged = dict(arp_hw)  # 先放华为的
    merged.update(arp_std)  # 标准覆盖（更可靠）

    src_std = len(arp_std)
    src_hw = len(arp_hw)
    if src_std or src_hw:
        print(f"  {ip}: ARP 合并 (标准={src_std}, 华为={src_hw}, 去重后={len(merged)})")
    return merged


# ============================================================
# 路由表获取
# ============================================================

async def _get_route_table(slim, ip, community):
    """读取路由表 (ipRouteTable) 并返回结构化数据。

    返回: [{目标网络, 子网掩码, CIDR, 网关, 接口, 路由类型, 协议}, ...]
    """
    dest_raw = await _snmp_walk(slim, ip, community, OID_ROUTE_DEST)
    if not dest_raw:
        return []

    mask_raw = await _snmp_walk(slim, ip, community, OID_ROUTE_MASK)
    nexthop_raw = await _snmp_walk(slim, ip, community, OID_ROUTE_NEXTHOP)
    ifindex_raw = await _snmp_walk(slim, ip, community, OID_ROUTE_IFINDEX)
    type_raw = await _snmp_walk(slim, ip, community, OID_ROUTE_TYPE)
    proto_raw = await _snmp_walk(slim, ip, community, OID_ROUTE_PROTO)

    ifindex_names = await _build_ifindex_names(slim, ip, community)

    routes = []
    for oid_str, dest_val in dest_raw.items():
        net = _bytes_to_ip(dest_val)
        idx = _route_oid_index_to_net(oid_str, OID_ROUTE_DEST)
        if idx is None:
            continue

        mask_oid = f'{OID_ROUTE_MASK}.{idx}'
        mask_val = mask_raw.get(mask_oid)
        mask_str = _bytes_to_ip(mask_val) if mask_val is not None else ''
        cidr = _subnet_mask_to_cidr(mask_str) if mask_str else None

        nexthop_oid = f'{OID_ROUTE_NEXTHOP}.{idx}'
        nexthop_val = nexthop_raw.get(nexthop_oid)
        nexthop_str = _bytes_to_ip(nexthop_val) if nexthop_val is not None else ''

        ifindex_oid = f'{OID_ROUTE_IFINDEX}.{idx}'
        ifidx_val = ifindex_raw.get(ifindex_oid)
        iface = ifindex_names.get(_safe_str(ifidx_val), '') if ifidx_val is not None else ''

        type_oid = f'{OID_ROUTE_TYPE}.{idx}'
        type_val = type_raw.get(type_oid)
        route_type = _ROUTE_TYPE.get(int(type_val), _ROUTE_TYPE_DEFAULT) if type_val is not None else ''

        proto_oid = f'{OID_ROUTE_PROTO}.{idx}'
        proto_val = proto_raw.get(proto_oid)
        protocol = _ROUTE_PROTO.get(int(proto_val), _ROUTE_PROTO_DEFAULT) if proto_val is not None else ''

        cidr_str = f'{net}/{cidr}' if cidr is not None else net

        routes.append({
            "交换机IP": ip,
            "目标网络": net,
            "子网掩码": mask_str,
            "CIDR": cidr_str,
            "网关": nexthop_str,
            "接口": iface,
            "路由类型": route_type,
            "协议": protocol,
        })

    if routes:
        print(f"  {ip}: 路由表 {len(routes)} 条")

    return routes


# ============================================================
# 交换机类型检测
# ============================================================

async def _detect_switch_type(slim, ip, community):
    """检测交换机是二层还是三层。
    - 尝试遍历标准 ARP 表：有数据 → L3，无数据 → L2
    - 同时尝试华为 ARP 表辅助判断
    """
    svc = await _snmp_get_scalar(slim, ip, community, OID_SYS_SERVICES)
    arp_std = await _snmp_walk(slim, ip, community, OID_ARP_PHYS_ADDRESS)

    if arp_std:
        print(f"  {ip} -> 三层交换机 (ARP 表可用)")
        return 'L3'

    # 标准 ARP 无数据，尝试华为 ARP
    arp_hw = await _snmp_walk(slim, ip, community, OID_HW_ARP_IPADDR)
    if arp_hw:
        svc_str = f", sysServices={svc}" if svc is not None else ""
        print(f"  {ip} -> 三层交换机 (华为 ARP 表可用{svc_str})")
        return 'L3'

    svc_str = f", sysServices={svc}" if svc is not None else ""
    print(f"  {ip} -> 二层交换机 (无 ARP 表{svc_str})")
    return 'L2'


# ============================================================
# 二层交换机扫描
# ============================================================

async def _scan_l2_switch(slim, ip, community, mib_pref='standard'):
    """扫描二层交换机：FDB 合并 (标准 MIB + 可选华为 MIB)。"""
    print(f"扫描二层交换机: {ip} ...")

    fdb = await _get_fdb_merged(slim, ip, community, mib_pref)

    results = []
    for mac, info in fdb.items():
        results.append({
            "交换机IP": ip,
            "IP地址": "",
            "MAC地址": mac,
            "VLAN/BD": info.get("VLAN/BD"),
            "VLAN类型": info.get("VLAN类型", ""),
            "物理端口": info.get("物理端口", ""),
            "虚拟端口": info.get("虚拟端口", ""),
            "交换机类型": "二层",
        })
    return results


# ============================================================
# 三层交换机扫描
# ============================================================

async def _scan_l3_switch(slim, ip, community, mib_pref='standard'):
    """扫描三层交换机：ARP 合并 + FDB 合并 + 路由表。"""
    print(f"扫描三层交换机: {ip} ...")

    # 1. ARP 表：MAC → IP（标准 + 华为合并）
    arp_table = await _get_arp_merged(slim, ip, community)
    if not arp_table:
        print(f"  {ip}: ARP 表为空")
        # 即使无 ARP，FDB 仍然有价值（纯 MAC 条目）
        arp_table = {}

    # 2. FDB 表：标准 + 华为合并
    fdb = await _get_fdb_merged(slim, ip, community, mib_pref)

    # 3. 合并: ARP (IP→MAC) + FDB (MAC→端口/VLAN)
    results = []
    for mac, ip_addr in arp_table.items():
        fdb_info = fdb.get(mac, {})
        results.append({
            "交换机IP": ip,
            "IP地址": ip_addr,
            "MAC地址": mac,
            "VLAN/BD": fdb_info.get("VLAN/BD"),
            "VLAN类型": fdb_info.get("VLAN类型", ""),
            "物理端口": fdb_info.get("物理端口", ""),
            "虚拟端口": fdb_info.get("虚拟端口", ""),
            "交换机类型": "三层",
        })

    # 补充 FDB 中 ARP 没有的条目（被动设备、静默终端等）
    for mac, fdb_info in fdb.items():
        if mac not in arp_table:
            results.append({
                "交换机IP": ip,
                "IP地址": "",
                "MAC地址": mac,
                "VLAN/BD": fdb_info.get("VLAN/BD"),
                "VLAN类型": fdb_info.get("VLAN类型", ""),
                "物理端口": fdb_info.get("物理端口", ""),
                "虚拟端口": fdb_info.get("虚拟端口", ""),
                "交换机类型": "三层",
            })

    return results


# ============================================================
# 单交换机扫描入口
# ============================================================

async def _async_scan_switch(config):
    """单台交换机的完整异步扫描流程，返回 (host_data, route_data)。"""
    ip = config['ip']
    community = config['community']
    mib_pref = config.get('mib', 'standard')

    slim = Slim()
    try:
        switch_type = await _detect_switch_type(slim, ip, community)

        if switch_type == 'L3':
            host_data = await _scan_l3_switch(slim, ip, community, mib_pref)
            route_data = await _get_route_table(slim, ip, community)
        else:
            host_data = await _scan_l2_switch(slim, ip, community, mib_pref)
            route_data = []

        return host_data, route_data
    finally:
        slim.close()


def scan_switch(config):
    """同步包装：每个线程内运行独立的 asyncio 事件循环。"""
    return asyncio.run(_async_scan_switch(config))


# ============================================================
# 主入口
# ============================================================

def main():
    all_hosts = []
    all_routes = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(scan_switch, sw): sw for sw in SWITCH_CONFIGS}
        for future in futures:
            sw = futures[future]
            try:
                host_data, route_data = future.result()
                all_hosts.extend(host_data)
                all_routes.extend(route_data)
            except Exception as e:
                print(f"扫描交换机 {sw['ip']} 失败: {e}")

    with pd.ExcelWriter("network_report.xlsx") as writer:
        if all_hosts:
            df_hosts = pd.DataFrame(all_hosts)
            df_hosts['VLAN/BD'] = df_hosts['VLAN/BD'].astype('Int64')
            df_hosts.to_excel(writer, sheet_name='主机信息', index=False)
            print(f"\n主机信息: {len(all_hosts)} 条记录")

        if all_routes:
            df_routes = pd.DataFrame(all_routes)
            df_routes.to_excel(writer, sheet_name='路由表', index=False)
            print(f"路由表: {len(all_routes)} 条记录")

        if not all_hosts and not all_routes:
            print("\n未获取到任何数据，请检查交换机配置和 SNMP community。")
            return

    print("已保存至 network_report.xlsx")


if __name__ == "__main__":
    main()
