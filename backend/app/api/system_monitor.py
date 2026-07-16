"""系统监控 — API 端点"""
from __future__ import annotations
from datetime import datetime
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func

from app.database import get_db
from app.api.deps import get_current_user
from app.models.info_system import InfoSystem
from app.models.system_asset_link import SystemAssetLink
from app.models.domain_inventory import DomainInventory
from app.models.vm_inventory import VMInventory
from app.models.f5 import F5VirtualServer, F5PoolMember, F5ApplicationMap
from app.models.qax import QianXinServer
from app.models.dingjia import DingJiaBackupRecord
from app.models.zdns import ZDNSDomainMap
from app.schemas.system_monitor import (
    AssetLinkCreate, AssetLinkBatch, AssetLinkOut, AssetWithStatus,
    SystemSummary, TopologyData, TopoNode, TopoLink, MonitorOverview,
    AssetSearchResult,
)

router = APIRouter(prefix="/monitor", tags=["系统监控"])

_ASSET_LABELS = ["前端", "中间件", "数据库", "负载均衡", "存储", "安全", "备份", "监控", "其他"]

_ROLE_KEYWORDS = {
    "数据库": ["数据库", "db", "DB", "mysql", "MySQL", "oracle", "Oracle", "sql", "SQL", "mssql", "postgres", "redis", "Redis", "mongodb", "MongoDB"],
    "前端": ["前端", "web", "Web", "WEB", "nginx", "Nginx", "apache", "Apache", "tomcat", "Tomcat", "IIS", "iis", "node", "Node"],
    "中间件": ["中间件", "mq", "MQ", "kafka", "Kafka", "rabbit", "Rabbit", "elastic", "ES", "es", "etcd", "zookeeper"],
    "负载均衡": ["负载", "均衡", "haproxy", "HaProxy", "lvs", "LVS", "f5", "F5"],
    "存储": ["存储", "nas", "NAS", "san", "SAN", "oss", "OSS", "s3", "ceph", "nfs", "NFS", "gluster", "minio"],
    "安全": ["安全", "防火墙", "waf", "WAF", "ids", "ips", "审计", "堡垒", "vpn", "VPN"],
    "备份": ["备份", "backup", "容灾", "灾备"],
    "监控": ["监控", "zabbix", "Zabbix", "prometheus", "Prometheus", "grafana", "Grafana", "nagios", "Nagios", "cacti", "Cacti"],
}


def _guess_role(remark: str) -> str:
    """根据 VM 备注文本猜测组件角色"""
    if not remark:
        return ""
    for role, keywords in _ROLE_KEYWORDS.items():
        for kw in keywords:
            if kw in remark:
                return role
    return ""


def _get_user_dept_ids(user, db: Session) -> set[int] | None:
    """获取用户可见的部门ID集合。admin返回None表示全可见"""
    from app.api.assets import _get_visible_dept_ids
    return _get_visible_dept_ids(db, user)


def _filter_systems_by_user(query, user, db: Session):
    """按用户权限过滤信息系统查询"""
    role = getattr(user, 'role', 'user') if hasattr(user, 'role') else 'user'
    if role == 'admin':
        return query  # 全可见
    if role == 'dept_admin':
        # 部门管理员：本部门及子部门 + 自己认领的
        dept_ids = _get_user_dept_ids(user, db)
        if dept_ids:
            return query.filter(
                (InfoSystem.dept_id.in_(dept_ids)) |
                (InfoSystem.manager_gh == str(user.gh or user.id))
            )
    # 普通用户：仅自己认领的
    user_gh = str(user.gh or user.id)
    return query.filter(InfoSystem.manager_gh == user_gh)


# ══════════════════════════════════════════════════════════════════
# 端点 1: 信息系统列表（含资产统计）
# ══════════════════════════════════════════════════════════════════

@router.get("/systems", response_model=dict)
def list_systems(
    search: str = Query("", max_length=255),
    manager: str = Query("", max_length=64, description="按管理员筛选"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    base = db.query(InfoSystem).filter(
        InfoSystem.system_name != "",
        ~InfoSystem.fill_type.in_(["注销", "申请注销"])
    )
    base = _filter_systems_by_user(base, current_user, db)
    if search:
        base = base.filter(InfoSystem.system_name.contains(search))
    if manager:
        base = base.filter(InfoSystem.manager_name.contains(manager))

    systems = base.order_by(InfoSystem.system_name).all()
    items = []
    for s in systems:
        asset_count = db.query(sa_func.count(SystemAssetLink.id)).filter(
            SystemAssetLink.info_system_id == s.id
        ).scalar() or 0
        items.append({
            "id": s.id,
            "system_name": s.system_name,
            "dept_name": s.dept_name or "",
            "manager_name": s.manager_name or "",
            "asset_count": asset_count,
            "abnormal_count": 0,
            "status": "normal",
        })
    return {"items": items, "total": len(items)}


# ══════════════════════════════════════════════════════════════════
# 端点 2: 系统关联的资产列表（含实时状态）
# ══════════════════════════════════════════════════════════════════

@router.get("/systems/{system_id}/assets", response_model=dict)
def list_system_assets(
    system_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # 验证权限
    sys = db.query(InfoSystem).filter(InfoSystem.id == system_id).first()
    if not sys:
        raise HTTPException(404, "信息系统不存在")
    role = getattr(current_user, 'role', 'user') if hasattr(current_user, 'role') else 'user'
    if role != 'admin':
        user_gh = str(current_user.gh or current_user.id)
        if role == 'dept_admin':
            dept_ids = _get_user_dept_ids(current_user, db)
            allowed = (sys.dept_id and dept_ids and sys.dept_id in dept_ids) or (sys.manager_gh == user_gh)
        else:
            allowed = (sys.manager_gh == user_gh)
        if not allowed:
            raise HTTPException(403, "无权访问该系统")

    links = db.query(SystemAssetLink).filter(
        SystemAssetLink.info_system_id == system_id
    ).order_by(SystemAssetLink.asset_type, SystemAssetLink.asset_label).all()

    items = []
    for link in links:
        item = {
            "id": link.id,
            "info_system_id": link.info_system_id,
            "asset_type": link.asset_type,
            "asset_key": link.asset_key,
            "asset_label": link.asset_label or "",
            "notes": link.notes or "",
            "created_by": link.created_by,
            "created_at": link.created_at.isoformat() if link.created_at else None,
            "status": "unknown",
            "status_label": "",
            "status_detail": "",
        }
        # 查询实时状态
        _fill_status(item, db)
        items.append(item)

    return {"items": items, "asset_labels": _ASSET_LABELS}


def _fill_status(item: dict, db: Session):
    """根据资产类型和标识查询实时运行状态"""
    at = item["asset_type"]
    key = item["asset_key"]

    if at == "domain":
        z = db.query(ZDNSDomainMap).filter(ZDNSDomainMap.domain_name == key).first()
        item["status"] = "up" if z else "unknown"
        item["status_label"] = "解析正常" if z else "未找到记录"
        item["asset_ip"] = z.ip_address if z else ""
        item["status_detail"] = ""

    elif at == "vm":
        vm = db.query(VMInventory).filter(VMInventory.vm_name == key).first()
        if vm:
            on = vm.power_state == "poweredOn"
            item["status"] = "up" if on else "down"
            item["status_label"] = "运行中" if on else "已关机"
            item["asset_ip"] = (vm.ip_address or "").split(",")[0]
            # 备份状态（所有VM都显示，按天数分级）
            rec = db.query(DingJiaBackupRecord).filter(
                DingJiaBackupRecord.vm_name == key
            ).order_by(DingJiaBackupRecord.last_run_time.desc()).first()
            if rec and rec.last_run_time:
                days = (datetime.now().date() - rec.last_run_time.date()).days
                ts = rec.last_run_time.strftime('%Y/%-m/%-d %H:%M')
                if days <= 7:
                    item["backup_status"] = "up"
                    item["backup_label"] = f"备份正常 {ts}"
                elif days <= 15:
                    item["backup_status"] = "warning"
                    item["backup_label"] = f"备份正常 {ts}"
                else:
                    item["backup_status"] = "remind"
                    item["backup_label"] = f"备份提醒 {ts}"
            elif rec:
                item["backup_status"] = "unknown"
                item["backup_label"] = "备份无时间"
            else:
                item["backup_status"] = "down"
                item["backup_label"] = "备份异常"
            # 椒图状态（所有VM都显示）
            qax_found = False
            if vm.ip_address:
                for ip in vm.ip_address.split(","):
                    ip = ip.strip()
                    if ip:
                        srv = db.query(QianXinServer).filter(
                            (QianXinServer.ipv4 == ip) | (QianXinServer.intranet_ip == ip)
                        ).first()
                        if srv:
                            online = srv.online_status == 1
                            item["qax_status"] = "up" if online else "down"
                            item["qax_label"] = "椒图在线" if online else "椒图离线"
                            item["qax_name"] = srv.machine_name or srv.ipv4 or ""
                            qax_found = True
                            break
            if not qax_found:
                item["qax_status"] = "unknown"
                item["qax_label"] = "无椒图"
            item["status_detail"] = f"{item.get('backup_label','')} | {item.get('qax_label','')}"
        else:
            item["asset_ip"] = ""
            item["status_label"] = "未找到"
            item["backup_status"] = "unknown"
            item["backup_label"] = ""
            item["qax_status"] = "unknown"
            item["qax_label"] = ""

    elif at == "f5_vs":
        vs = db.query(F5VirtualServer).filter(F5VirtualServer.name == key).first()
        item["status"] = "up" if vs else "unknown"
        item["status_label"] = f"VS {vs.vs_ip}:{vs.vs_port}" if vs else "未找到"
        item["asset_ip"] = vs.vs_ip if vs else ""

    elif at == "f5_member":
        # key 格式: "pool_name:member_ip:member_port"
        parts = key.split(":", 2)
        member = None
        if len(parts) >= 2:
            member = db.query(F5PoolMember).filter(
                F5PoolMember.pool_name.contains(parts[0]),
                F5PoolMember.member_ip == parts[1],
            ).first()
        if member:
            up = "up" in (member.member_state or "").lower()
            item["status"] = "up" if up else "down"
            item["status_label"] = member.member_state
            item["asset_ip"] = member.member_ip or ""
        else:
            item["asset_ip"] = parts[1] if len(parts) >= 2 else ""

    elif at == "backup":
        item["asset_ip"] = ""
        rec = db.query(DingJiaBackupRecord).filter(
            DingJiaBackupRecord.vm_name == key
        ).order_by(DingJiaBackupRecord.last_run_time.desc()).first()
        if rec and rec.last_run_time:
            days = (datetime.now().date() - rec.last_run_time.date()).days
            ts = rec.last_run_time.strftime('%Y/%-m/%-d %H:%M')
            if days <= 7:
                item["status"] = "up"
                item["status_label"] = "正常"
            elif days <= 15:
                item["status"] = "warning"
                item["status_label"] = "正常"
            else:
                item["status"] = "remind"
                item["status_label"] = "提醒"
            item["status_detail"] = ts
        elif rec:
            item["status"] = "unknown"
            item["status_label"] = "无时间"
        else:
            item["status"] = "down"
            item["status_label"] = "异常"

    elif at == "qax":
        srv = db.query(QianXinServer).filter(
            (QianXinServer.machine_name == key) | (QianXinServer.ipv4 == key)
        ).first()
        if srv:
            online = srv.online_status == 1
            item["status"] = "up" if online else "down"
            item["status_label"] = "在线" if online else "离线"
            item["asset_ip"] = srv.ipv4 or ""
        else:
            item["asset_ip"] = ""


# ══════════════════════════════════════════════════════════════════
# 端点 3: 批量关联资产
# ══════════════════════════════════════════════════════════════════

@router.post("/systems/{system_id}/assets")
def link_assets(
    system_id: int,
    body: AssetLinkBatch,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    added = 0
    vm_names = set()
    for a in body.assets:
        exists = db.query(SystemAssetLink).filter(
            SystemAssetLink.info_system_id == system_id,
            SystemAssetLink.asset_type == a.asset_type,
            SystemAssetLink.asset_key == a.asset_key,
        ).first()
        if exists:
            continue
        link = SystemAssetLink(
            info_system_id=system_id,
            asset_type=a.asset_type,
            asset_key=a.asset_key,
            asset_label=a.asset_label,
            notes=a.notes,
            created_by=current_user.id,
        )
        db.add(link)
        added += 1
        if a.asset_type == "vm":
            vm_names.add(a.asset_key)

    # VM 自动关联备用和椒图
    for vm_name in vm_names:
        vm = db.query(VMInventory).filter(VMInventory.vm_name == vm_name).first()
        if not vm:
            continue
        # 备份
        for b in db.query(DingJiaBackupRecord).filter(DingJiaBackupRecord.vm_name == vm_name).all():
            ek = (system_id, "backup", vm_name)
            exists = db.query(SystemAssetLink).filter(
                SystemAssetLink.info_system_id == system_id,
                SystemAssetLink.asset_type == "backup",
                SystemAssetLink.asset_key == vm_name,
            ).first()
            if not exists:
                db.add(SystemAssetLink(
                    info_system_id=system_id, asset_type="backup", asset_key=vm_name,
                    asset_label="备份", created_by=current_user.id,
                ))
                added += 1
            break  # 一个VM只加一条备份
        # 椒图
        if vm.ip_address:
            for ip in vm.ip_address.split(","):
                ip = ip.strip()
                if not ip:
                    continue
                for q in db.query(QianXinServer).filter(
                    (QianXinServer.ipv4 == ip) | (QianXinServer.intranet_ip == ip)
                ).all():
                    qk = q.machine_name or q.ipv4 or ""
                    exists = db.query(SystemAssetLink).filter(
                        SystemAssetLink.info_system_id == system_id,
                        SystemAssetLink.asset_type == "qax",
                        SystemAssetLink.asset_key == qk,
                    ).first()
                    if not exists:
                        db.add(SystemAssetLink(
                            info_system_id=system_id, asset_type="qax", asset_key=qk,
                            asset_label="安全", created_by=current_user.id,
                        ))
                        added += 1
                    break  # 一台VM只加一条椒图

    db.commit()
    return {"added": added, "message": f"成功关联 {added} 个资产"}


# ══════════════════════════════════════════════════════════════════
# 端点 4: 取消关联
# ══════════════════════════════════════════════════════════════════

@router.put("/assets/{link_id}")
def update_asset_link(
    link_id: int,
    body: dict,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    link = db.query(SystemAssetLink).filter(SystemAssetLink.id == link_id).first()
    if not link:
        raise HTTPException(404, "关联记录不存在")
    if "asset_label" in body:
        link.asset_label = body["asset_label"]
    if "notes" in body:
        link.notes = body["notes"]
    db.commit()
    return {"message": "已更新"}


@router.delete("/systems/{system_id}/assets")
def clear_all_assets(
    system_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    count = db.query(SystemAssetLink).filter(
        SystemAssetLink.info_system_id == system_id
    ).delete()
    db.commit()
    return {"message": f"已清除 {count} 个关联资产", "count": count}


@router.delete("/assets/{link_id}")
def unlink_asset(
    link_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    link = db.query(SystemAssetLink).filter(SystemAssetLink.id == link_id).first()
    if not link:
        raise HTTPException(404, "关联记录不存在")
    db.delete(link)
    db.commit()
    return {"message": "已取消关联"}


# ══════════════════════════════════════════════════════════════════
# 端点 5: 拓扑数据
# ══════════════════════════════════════════════════════════════════

@router.get("/systems/{system_id}/topology", response_model=TopologyData)
def get_topology(
    system_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """拓扑数据：按实际数据链路分层展示。
    链路：系统 → 域名 → IP → {F5 VS → 成员, VM} → {备份, 椒图}"""
    sys = db.query(InfoSystem).filter(InfoSystem.id == system_id).first()
    if not sys:
        raise HTTPException(404, "信息系统不存在")

    sys_name = sys.system_name

    nodes: list[TopoNode] = []
    edges: list[TopoLink] = []
    node_seen: set[str] = set()
    edge_seen: set[tuple] = set()

    def _add_node(name: str, cat: str, label: str, status="unknown", status_label=""):
        if name in node_seen:
            return
        node_seen.add(name)
        nodes.append(TopoNode(name=name, category=cat, label=label[:40], status=status, status_label=status_label))

    def _add_edge(src: str, tgt: str, lbl: str):
        key = (src, tgt, lbl)
        if key in edge_seen:
            return
        edge_seen.add(key)
        edges.append(TopoLink(source=src, target=tgt, label=lbl))

    # ── 中心节点 ──
    _add_node(sys_name, "system", sys_name, "normal", "")

    # ── 收集已关联资产（也包含通过 auto-link 逻辑发现的） ──
    links = db.query(SystemAssetLink).filter(
        SystemAssetLink.info_system_id == system_id
    ).all()

    linked_domains = set()
    linked_vs = {}
    linked_members = {}
    linked_vms = set()
    linked_backups = {}
    linked_qax = {}

    for l in links:
        if l.asset_type == "domain":
            linked_domains.add(l.asset_key)
        elif l.asset_type == "f5_vs":
            linked_vs[l.asset_key] = l.asset_label
        elif l.asset_type == "f5_member":
            # key format: pool:ip:port
            parts = l.asset_key.split(":", 2)
            if len(parts) >= 2:
                linked_members[parts[1]] = l.asset_key  # ip -> key
        elif l.asset_type == "vm":
            linked_vms.add(l.asset_key)
        elif l.asset_type == "backup":
            linked_backups[l.asset_key] = l.asset_label
        elif l.asset_type == "qax":
            linked_qax[l.asset_key] = l.asset_label

    # 系统域名（未显式关联但系统自带）
    if sys.domain:
        for d in sys.domain.replace(",", " ").replace(";", " ").split():
            d = d.strip()
            if d:
                linked_domains.add(d)

    # ── 第1层：域名 ──
    for domain in linked_domains:
        dn = f"domain:{domain}"
        item = {"asset_type": "domain", "asset_key": domain}
        _fill_status(item, db)
        _add_node(dn, "domain", domain, item["status"], item["status_label"])
        _add_edge(sys_name, dn, "域名")

        # ── 第2层：域名 → IP (ZDNS) ──
        zdns_ips = db.query(ZDNSDomainMap.ip_address).filter(
            ZDNSDomainMap.domain_name == domain,
            ZDNSDomainMap.ip_address != "",
        ).distinct().all()

        for (ip,) in zdns_ips:
            ipn = f"ip:{ip}"
            _add_node(ipn, "ip", ip, "up", ip)

            # ── 第3层A：IP → F5 VS → 成员 ──
            vs_list = db.query(F5VirtualServer).filter(F5VirtualServer.vs_ip == ip).all()
            for vs in vs_list:
                vsn = f"f5_vs:{vs.name}"
                item_vs = {"asset_type": "f5_vs", "asset_key": vs.name}
                _fill_status(item_vs, db)
                _add_node(vsn, "f5_vs", vs.name, item_vs["status"], item_vs["status_label"])
                _add_edge(dn, vsn, f"VS {ip}:{vs.vs_port or ''}")

                # 成员
                members = db.query(F5PoolMember).filter(
                    F5PoolMember.f5_device_id == vs.f5_device_id,
                    F5PoolMember.pool_name == vs.pool_name,
                    F5PoolMember.member_ip != "",
                ).all()
                for m in members:
                    mkey = f"f5_member:{vs.pool_name}:{m.member_ip}"
                    item_m = {"asset_type": "f5_member", "asset_key": f"{vs.pool_name}:{m.member_ip}:{m.member_port or ''}"}
                    _fill_status(item_m, db)
                    _add_node(mkey, "f5_member", f"{m.member_ip}:{m.member_port or ''}", item_m["status"], item_m["status_label"])
                    _add_edge(vsn, mkey, "成员")

                    # ── 第4层：成员IP → VM ──
                    if m.member_ip:
                        _link_ip_to_vm(m.member_ip, mkey, db, _add_node, _add_edge)

            # ── 第3层B：IP → VM (直接匹配，非F5) ──
            _link_ip_to_vm(ip, dn, db, _add_node, _add_edge)

    # ── 已绑定的 VM → 备份 + 椒图 ──
    for vm_name in linked_vms:
        vmn = f"vm:{vm_name}"
        if vmn not in node_seen:
            item_v = {"asset_type": "vm", "asset_key": vm_name}
            _fill_status(item_v, db)
            _add_node(vmn, "vm", vm_name, item_v["status"], item_v["status_label"])

        # 备份
        for b in db.query(DingJiaBackupRecord).filter(DingJiaBackupRecord.vm_name == vm_name).all():
            bn = f"backup:{vm_name}"
            item_b = {"asset_type": "backup", "asset_key": vm_name}
            _fill_status(item_b, db)
            _add_node(bn, "backup", vm_name, item_b["status"], item_b["status_label"])
            _add_edge(vmn, bn, "备份")

    # ── 兜底：孤立节点（无父连接的）统一挂到系统节点 ──
    all_linked_nodes = {e.target for e in edges}
    all_linked_nodes.add(sys_name)
    for node in nodes:
        if node.name not in all_linked_nodes and node.category != "system":
            _add_edge(sys_name, node.name, node.category)

    return TopologyData(nodes=nodes, links=edges)


def _link_ip_to_vm(ip: str, parent_node: str, db: Session,
                    _add_node, _add_edge):
    """辅助：IP → VM 匹配（VM清单IP + 交换机扫描结果MAC反查兜底）"""
    vm_found = set()
    # 方式1：直接IP匹配
    for vm in db.query(VMInventory).filter(VMInventory.ip_address.contains(ip)).all():
        ips = [x.strip() for x in (vm.ip_address or "").split(",")]
        if ip in ips and vm.vm_name not in vm_found:
            vm_found.add(vm.vm_name)
            _emit_vm_node(vm.vm_name, ip, parent_node, db, _add_node, _add_edge)

    # 方式2：交换机扫描结果 IP→MAC→VM 兜底（VM清单IP未补全时）
    if not vm_found:
        from app.models.scan_result import ScanResult
        macs = db.query(ScanResult.mac_address).filter(
            ScanResult.ip_address == ip,
            ScanResult.mac_address != "",
            ScanResult.mac_address.isnot(None),
        ).distinct().all()
        for (mac,) in macs:
            for vm in db.query(VMInventory).filter(VMInventory.mac_address.contains(mac)).all():
                if vm.vm_name not in vm_found:
                    vm_found.add(vm.vm_name)
                    _emit_vm_node(vm.vm_name, ip, parent_node, db, _add_node, _add_edge)


def _emit_vm_node(vm_name: str, ip: str, parent_node: str, db: Session,
                  _add_node, _add_edge):
    """辅助：生成 VM 节点及下属备份/椒图节点"""
    vmn = f"vm:{vm_name}"
    item = {"asset_type": "vm", "asset_key": vm_name}
    _fill_status(item, db)
    _add_node(vmn, "vm", vm_name, item["status"], item["status_label"])
    _add_edge(parent_node, vmn, "VM")

    # VM → 备份
    for b in db.query(DingJiaBackupRecord).filter(DingJiaBackupRecord.vm_name == vm_name).all():
        bn = f"backup:{vm_name}"
        item_b = {"asset_type": "backup", "asset_key": vm_name}
        _fill_status(item_b, db)
        _add_node(bn, "backup", vm_name, item_b["status"], item_b["status_label"])
        _add_edge(vmn, bn, "备份")

    # VM → 椒图(通过IP)
    for q in db.query(QianXinServer).filter(
        (QianXinServer.ipv4 == ip) | (QianXinServer.intranet_ip == ip)
    ).all():
        qn = f"qax:{q.machine_name or q.ipv4 or ip}"
        item_q = {"asset_type": "qax", "asset_key": q.machine_name or q.ipv4 or ip}
        _fill_status(item_q, db)
        _add_node(qn, "qax", q.machine_name or q.ipv4 or "", item_q["status"], item_q["status_label"])
        _add_edge(vmn, qn, "椒图")


# ══════════════════════════════════════════════════════════════════
# 端点 6: 全局总览
# ══════════════════════════════════════════════════════════════════

@router.get("/overview", response_model=MonitorOverview)
def get_overview(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    base = db.query(InfoSystem).filter(
        InfoSystem.system_name != "",
        ~InfoSystem.fill_type.in_(["注销", "申请注销"])
    )
    base = _filter_systems_by_user(base, current_user, db)
    systems = base.order_by(InfoSystem.system_name).all()
    items: list[SystemSummary] = []
    normal = warning = critical = 0

    for s in systems:
        links_list = db.query(SystemAssetLink).filter(
            SystemAssetLink.info_system_id == s.id
        ).all()
        if not links_list:
            continue  # 仅显示有关联资产的系统

        abnormal = 0
        for link in links_list:
            item = {"asset_type": link.asset_type, "asset_key": link.asset_key}
            _fill_status(item, db)
            if item["status"] == "down":
                abnormal += 1

        if abnormal == 0:
            status = "normal"
            normal += 1
        elif abnormal < len(links_list):
            status = "warning"
            warning += 1
        else:
            status = "critical"
            critical += 1

        items.append(SystemSummary(
            id=s.id,
            system_name=s.system_name,
            dept_name=s.dept_name or "",
            asset_count=len(links_list),
            abnormal_count=abnormal,
            status=status,
        ))

    return MonitorOverview(
        total_systems=len(items),
        normal_count=normal,
        warning_count=warning,
        critical_count=critical,
        systems=items,
    )


# ══════════════════════════════════════════════════════════════════
# 端点 7: 资产搜索（用于添加关联时搜索）
# ══════════════════════════════════════════════════════════════════

@router.post("/systems/{system_id}/auto-link")
def auto_link_assets(
    system_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """自动关联：从系统域名出发，递归关联下游全部资产。
    链路：域名 → ZDNS IP → F5 VS/ApplicationMap → Pool成员IP → VM → 备份/椒图"""
    sys = db.query(InfoSystem).filter(InfoSystem.id == system_id).first()
    if not sys:
        raise HTTPException(404, "信息系统不存在")

    added = 0
    seen = set()

    def _link(at: str, ak: str, label: str = "", notes: str = ""):
        nonlocal added
        if not ak:
            return
        key = (at, ak)
        if key in seen:
            return
        seen.add(key)
        exists = db.query(SystemAssetLink).filter(
            SystemAssetLink.info_system_id == system_id,
            SystemAssetLink.asset_type == at,
            SystemAssetLink.asset_key == ak,
        ).first()
        if exists:
            return
        db.add(SystemAssetLink(
            info_system_id=system_id, asset_type=at, asset_key=ak,
            asset_label=label, notes=notes, created_by=current_user.id,
        ))
        added += 1

    # ── 1. 系统域名 ──
    domains = set()
    if sys.domain:
        for d in sys.domain.replace(",", " ").replace(";", " ").split():
            d = d.strip()
            if d:
                domains.add(d)
                _link("domain", d, "域名")
    # 已绑定域名也纳入
    for l in db.query(SystemAssetLink).filter(
        SystemAssetLink.info_system_id == system_id,
        SystemAssetLink.asset_type == "domain",
    ).all():
        if l.asset_key:
            domains.add(l.asset_key)

    # ── 2. 域名 → ZDNS IP → F5 ApplicationMap (完整映射链路) ──
    all_member_ips = set()  # 收集所有成员IP用于VM匹配
    f5_app_rows = []
    if domains:
        f5_app_rows = db.query(F5ApplicationMap).filter(
            F5ApplicationMap.domain_name.in_(domains),
            F5ApplicationMap.source == "irule",
        ).all()
    if not f5_app_rows and domains:
        # 域名无irule映射，尝试通过域名IP找VS
        for domain in domains:
            zdns_ips = db.query(ZDNSDomainMap.ip_address).filter(
                ZDNSDomainMap.domain_name == domain, ZDNSDomainMap.ip_address != "",
            ).distinct().all()
            for (ip,) in zdns_ips:
                f5_app_rows += db.query(F5ApplicationMap).filter(
                    F5ApplicationMap.vs_ip == ip,
                ).all()

    # 从 ApplicationMap 提取 VS 和成员
    for am in f5_app_rows:
        if am.vs_name:
            _link("f5_vs", am.vs_name, "负载均衡")
        if am.member_ip:
            mk = f"{am.pool_name or ''}:{am.member_ip}:{am.member_port or ''}"
            _link("f5_member", mk, "负载均衡")
            all_member_ips.add(am.member_ip)

    # ── 3. 域名IP → VS(无ApplicationMap兜底) + 直接F5PoolMember ──
    for domain in domains:
        zdns_ips = db.query(ZDNSDomainMap.ip_address).filter(
            ZDNSDomainMap.domain_name == domain, ZDNSDomainMap.ip_address != "",
        ).distinct().all()
        for (ip,) in zdns_ips:
            # VS 直接匹配IP
            for vs in db.query(F5VirtualServer).filter(F5VirtualServer.vs_ip == ip).all():
                _link("f5_vs", vs.name, "负载均衡")
                # Pool成员
                for m in db.query(F5PoolMember).filter(
                    F5PoolMember.f5_device_id == vs.f5_device_id,
                    F5PoolMember.pool_name == vs.pool_name,
                    F5PoolMember.member_ip != "",
                ).all():
                    mk = f"{vs.pool_name}:{m.member_ip}:{m.member_port or ''}"
                    _link("f5_member", mk, "负载均衡")
                    all_member_ips.add(m.member_ip)

    # ── 3b. 域名IP → VM (直接匹配 + 交换机MAC兜底) ──
    def _find_vms_by_ip(ip: str) -> set[str]:
        found = set()
        for vm in db.query(VMInventory).filter(VMInventory.ip_address.contains(ip)).all():
            ips = [x.strip() for x in (vm.ip_address or "").split(",")]
            if ip in ips:
                found.add(vm.vm_name)
        # 交换机扫描结果 MAC→VM 兜底
        if not found:
            from app.models.scan_result import ScanResult
            macs = db.query(ScanResult.mac_address).filter(
                ScanResult.ip_address == ip, ScanResult.mac_address != "",
                ScanResult.mac_address.isnot(None),
            ).distinct().all()
            for (mac,) in macs:
                for vm in db.query(VMInventory).filter(VMInventory.mac_address.contains(mac)).all():
                    found.add(vm.vm_name)
        return found

    vm_names_found = set()
    for domain in domains:
        zdns_ips = db.query(ZDNSDomainMap.ip_address).filter(
            ZDNSDomainMap.domain_name == domain, ZDNSDomainMap.ip_address != "",
        ).distinct().all()
        for (ip,) in zdns_ips:
            for vm_name in _find_vms_by_ip(ip):
                if vm_name not in vm_names_found:
                    vm = db.query(VMInventory).filter(VMInventory.vm_name == vm_name).first()
                    _link("vm", vm_name, "", vm.remark if vm else "")
                    vm_names_found.add(vm_name)

            # 成员IP也走同样的双路匹配
            for vm_name in _find_vms_by_ip(ip):
                if vm_name not in vm_names_found:
                    vm = db.query(VMInventory).filter(VMInventory.vm_name == vm_name).first()
                    _link("vm", vm_name, "", vm.remark if vm else "")
                    vm_names_found.add(vm_name)

    # ── 4. 成员IP → 虚拟机（精确匹配 + 逗号分隔多IP）─
    for ip in all_member_ips:
        # 精确匹配单IP
        for vm in db.query(VMInventory).filter(VMInventory.ip_address == ip).all():
            _link("vm", vm.vm_name, "", vm.remark or "")
            vm_names_found.add(vm.vm_name)
        # 逗号分隔多IP
        for vm in db.query(VMInventory).filter(VMInventory.ip_address.contains(ip)).all():
            if vm.vm_name not in vm_names_found:
                ips = [x.strip() for x in (vm.ip_address or "").split(",")]
                if ip in ips:
                    _link("vm", vm.vm_name, "", vm.remark or "")
                    vm_names_found.add(vm.vm_name)

    # ── 5. VM → 备份 + IP收集 → 椒图 ──
    all_ips_for_qax = set(all_member_ips)
    for vm_name in vm_names_found:
        vm = db.query(VMInventory).filter(VMInventory.vm_name == vm_name).first()
        if vm:
            # 备份
            for b in db.query(DingJiaBackupRecord).filter(
                DingJiaBackupRecord.vm_name == vm_name
            ).all():
                _link("backup", vm_name, "备份")
            # VM的IP也加入椒图匹配
            if vm.ip_address:
                for ip in vm.ip_address.split(","):
                    ip = ip.strip()
                    if ip:
                        all_ips_for_qax.add(ip)

    # ── 6. IP → 椒图 ──
    for ip in all_ips_for_qax:
        for q in db.query(QianXinServer).filter(
            (QianXinServer.ipv4 == ip) | (QianXinServer.intranet_ip == ip)
        ).all():
            _link("qax", q.machine_name or q.ipv4 or "", "安全")

    # ── 7. 已绑定VM补充（无成员IP兜底）─
    for l in db.query(SystemAssetLink).filter(
        SystemAssetLink.info_system_id == system_id,
        SystemAssetLink.asset_type == "vm",
    ).all():
        vm_name = l.asset_key
        vm = db.query(VMInventory).filter(VMInventory.vm_name == vm_name).first()
        if vm:
            # 备份
            for b in db.query(DingJiaBackupRecord).filter(
                DingJiaBackupRecord.vm_name == vm_name
            ).all():
                _link("backup", vm_name, "备份")
            # 椒图
            if vm.ip_address:
                for ip in vm.ip_address.split(","):
                    ip = ip.strip()
                    if ip:
                        for q in db.query(QianXinServer).filter(
                            (QianXinServer.ipv4 == ip) | (QianXinServer.intranet_ip == ip)
                        ).all():
                            _link("qax", q.machine_name or q.ipv4 or "", "安全")

    db.commit()
    return {"added": added, "message": f"自动关联完成，新增 {added} 个资产"}


@router.get("/vm-folders")
def get_vm_folders(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """获取VM文件夹树形结构（层级树，按权限）"""
    from app.api.assets import _get_visible_dept_ids, _get_sub_dept_ids

    base = db.query(VMInventory.vm_folder, sa_func.count(VMInventory.id))
    # 权限过滤
    dept_ids = _get_visible_dept_ids(db, current_user)
    if dept_ids is not None:
        base = base.filter(VMInventory.department_id.in_(dept_ids))
    base = base.filter(VMInventory.vm_folder != "").group_by(VMInventory.vm_folder)
    rows = base.all()

    # 构建树：把 /a/b/c 拆成层级
    tree_map: dict[str, dict] = {}
    for fname, cnt in rows:
        parts = [p for p in fname.split("/") if p]
        path = ""
        for i, part in enumerate(parts):
            parent_path = path
            path = f"{path}/{part}" if path else part
            if path not in tree_map:
                tree_map[path] = {"id": path, "label": part, "path": path, "count": 0, "children": []}
            if parent_path and parent_path in tree_map:
                node = tree_map[path]
                parent = tree_map[parent_path]
                if not any(c["id"] == path for c in parent["children"]):
                    parent["children"].append(node)
        # 叶子节点计数
        if path in tree_map:
            tree_map[path]["count"] += cnt

    # 排序并返回根节点
    def sort_tree(nodes):
        nodes.sort(key=lambda x: x["label"])
        for n in nodes:
            if n["children"]:
                sort_tree(n["children"])

    roots = [v for v in tree_map.values() if "/" not in v["path"]]
    sort_tree(roots)
    for root in roots:
        root["count"] = _sum_tree_count(root)
    return {"folders": roots}


def _sum_tree_count(node: dict) -> int:
    total = node.get("count", 0)
    for child in node.get("children", []):
        total += _sum_tree_count(child)
    return total


@router.get("/search-assets", response_model=AssetSearchResult)
def search_assets(
    asset_type: str = Query(..., description="domain/vm/f5_vs/f5_member/backup/qax"),
    search: str = Query("", max_length=255),
    folder: str = Query("", max_length=255, description="VM文件夹过滤"),
    page: int = Query(1, ge=1),
    size: int = Query(30, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    items = []
    q = search.lower()

    if asset_type == "domain":
        base = db.query(DomainInventory).filter(DomainInventory.domain_name != "")
        if q:
            base = base.filter(DomainInventory.domain_name.contains(q))
        rows = base.order_by(DomainInventory.domain_name).offset((page-1)*size).limit(size).all()
        total = base.count()
        for r in rows:
            items.append({"key": r.domain_name, "name": r.domain_name, "ip": r.ip_address or "", "extra": r.record_type or ""})

    elif asset_type == "vm":
        base = db.query(VMInventory)
        # 权限过滤
        from app.api.assets import _get_visible_dept_ids
        dept_ids = _get_visible_dept_ids(db, current_user)
        if dept_ids is not None:
            base = base.filter(VMInventory.department_id.in_(dept_ids))
        if folder:
            base = base.filter(
                (VMInventory.vm_folder == folder) |
                (VMInventory.vm_folder.like(f"{folder}/%"))
            )
        if q:
            base = base.filter(
                VMInventory.vm_name.contains(q) |
                VMInventory.ip_address.contains(q) |
                VMInventory.remark.contains(q)
            )
        rows = base.order_by(VMInventory.vm_name).offset((page-1)*size).limit(size).all()
        total = base.count()
        for r in rows:
            items.append({
                "key": r.vm_name,
                "name": r.vm_name,
                "ip": (r.ip_address or "").split(",")[0],
                "extra": r.power_state or "",
                "folder": r.vm_folder or "",
                "remark": r.remark or "",
                "os": r.os_name or "",
                "role_hint": _guess_role(r.remark or ""),
            })

    elif asset_type == "f5_vs":
        base = db.query(F5VirtualServer)
        if q:
            base = base.filter(F5VirtualServer.name.contains(q))
        rows = base.order_by(F5VirtualServer.name).offset((page-1)*size).limit(size).all()
        total = base.count()
        for r in rows:
            items.append({"key": r.name, "name": r.name, "ip": r.vs_ip or "", "extra": f"port {r.vs_port}" if r.vs_port else ""})

    elif asset_type == "f5_member":
        base = db.query(F5PoolMember)
        if q:
            base = base.filter(F5PoolMember.member_ip.contains(q) | F5PoolMember.pool_name.contains(q))
        rows = base.order_by(F5PoolMember.pool_name, F5PoolMember.member_ip).offset((page-1)*size).limit(size).all()
        total = base.count()
        for r in rows:
            key = f"{r.pool_name}:{r.member_ip}:{r.member_port or ''}"
            items.append({"key": key, "name": f"{r.member_ip}:{r.member_port or ''}", "ip": r.member_ip, "extra": f"Pool: {r.pool_name}"})

    elif asset_type == "backup":
        base = db.query(DingJiaBackupRecord).filter(DingJiaBackupRecord.vm_name != "")
        if q:
            base = base.filter(DingJiaBackupRecord.vm_name.contains(q) | DingJiaBackupRecord.host_ip.contains(q))
        rows = base.order_by(DingJiaBackupRecord.vm_name).offset((page-1)*size).limit(size).all()
        total = base.count()
        seen = set()
        for r in rows:
            if r.vm_name in seen:
                continue
            seen.add(r.vm_name)
            items.append({"key": r.vm_name, "name": r.vm_name, "ip": r.host_ip or "", "extra": r.job_name or ""})

    elif asset_type == "qax":
        base = db.query(QianXinServer)
        if q:
            base = base.filter(QianXinServer.machine_name.contains(q) | QianXinServer.ipv4.contains(q))
        rows = base.order_by(QianXinServer.machine_name).offset((page-1)*size).limit(size).all()
        total = base.count()
        for r in rows:
            items.append({"key": r.machine_name or r.ipv4 or "", "name": r.machine_name or "", "ip": r.ipv4 or "", "extra": r.operation_system or ""})

    else:
        total = 0

    return AssetSearchResult(items=items, total=total)
