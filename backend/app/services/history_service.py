"""变更检测：以 (IP, MAC) 为复合键比较新旧扫描结果，生成历史记录。

vCenter 以 (vm_name, vcenter_id) 为复合键。
F5 以 (vs_name, domain_name) 为复合键。
"""
import json
from app.models.history import History, ChangeType, SourceType


TRACKED_FIELDS = ["vlan_bd", "vlan_type", "physical_port", "virtual_port", "switch_type"]

VCENTER_TRACKED_FIELDS = [
    "ip_address", "network_name", "resource_pool", "vm_folder",
    "power_state", "esxi_host", "cluster", "cpu_count", "memory_gb",
]


def _fields_differ(old_r, new_vlan_bd, new_vlan_type, new_physical_port,
                   new_virtual_port, new_switch_type):
    """比较旧记录与新的字段值是否有变化（5 个追踪字段）。"""
    return (
        str(old_r.vlan_bd or "") != str(new_vlan_bd or "") or
        str(old_r.vlan_type or "") != str(new_vlan_type or "") or
        str(old_r.physical_port or "") != str(new_physical_port or "") or
        str(old_r.virtual_port or "") != str(new_virtual_port or "") or
        str(old_r.switch_type or "") != str(new_switch_type or "")
    )


def _build_change_detail(old_r, new_r, fields):
    """根据旧/新对象构建 change_detail JSON。"""
    detail = {}
    for f in fields:
        ov = str(getattr(old_r, f, None) or "")
        nv = str(getattr(new_r, f, None) or "")
        if ov != nv:
            detail[f] = {"old": getattr(old_r, f, None), "new": getattr(new_r, f, None)}
    return json.dumps(detail, ensure_ascii=False) if detail else None


def _make_entry(change_type, switch_id, scan_log_id, old_r, new_r,
                source_type="switch", source_name="", dedup_key=""):
    """根据旧/新扫描结果构建 History 记录（交换机）。"""
    entry = History(
        change_type=change_type,
        switch_id=switch_id,
        scan_log_id=scan_log_id,
        source_type=source_type,
        source_id=switch_id,
        source_name=source_name,
        dedup_key=dedup_key,
    )
    if new_r is not None:
        entry.ip_address = new_r.ip_address
        entry.mac_address = new_r.mac_address
        entry.new_vlan_bd = new_r.vlan_bd
        entry.new_vlan_type = new_r.vlan_type or ""
        entry.new_physical_port = new_r.physical_port or ""
        entry.new_virtual_port = new_r.virtual_port or ""
        entry.new_switch_type = new_r.switch_type or ""
    if old_r is not None:
        if new_r is None:
            entry.ip_address = old_r.ip_address
            entry.mac_address = old_r.mac_address
        entry.old_vlan_bd = old_r.vlan_bd
        entry.old_vlan_type = old_r.vlan_type or ""
        entry.old_physical_port = old_r.physical_port or ""
        entry.old_virtual_port = old_r.virtual_port or ""
        entry.old_switch_type = old_r.switch_type or ""
    if old_r is not None and new_r is not None:
        entry.change_detail = _build_change_detail(old_r, new_r, TRACKED_FIELDS)
    return entry


def detect_changes(db, switch_id: int, scan_log_id: int,
                   old_by_key: dict, new_by_key: dict, handled_old_keys: set,
                   source_name: str = ""):
    """
    以 (IP, MAC) 为复合键进行 diff：
    - 新键不在旧键中 → added
    - 旧键未被处理（已不在新数据中） → deleted
    - 旧键被处理但新旧行 ID 不同（字段变化导致新行插入） → modified
    """
    if not old_by_key:
        return 0

    count = 0

    for key, new_r in new_by_key.items():
        if key not in old_by_key:
            dedup = f"{new_r.ip_address}|{new_r.mac_address}"
            db.add(_make_entry(ChangeType.added, switch_id, scan_log_id, None, new_r,
                              source_type=SourceType.switch, source_name=source_name,
                              dedup_key=dedup))
            count += 1

    for key, old_r in old_by_key.items():
        if key not in handled_old_keys:
            dedup = f"{old_r.ip_address}|{old_r.mac_address}"
            db.add(_make_entry(ChangeType.deleted, switch_id, scan_log_id, old_r, None,
                              source_type=SourceType.switch, source_name=source_name,
                              dedup_key=dedup))
            count += 1

    for key in handled_old_keys:
        old_r = old_by_key.get(key)
        new_r = new_by_key.get(key)
        if old_r and new_r and old_r.id != new_r.id:
            dedup = f"{new_r.ip_address}|{new_r.mac_address}"
            db.add(_make_entry(ChangeType.modified, switch_id, scan_log_id, old_r, new_r,
                              source_type=SourceType.switch, source_name=source_name,
                              dedup_key=dedup))
            count += 1

    return count


def _vcenter_fields_differ(old_row, new_row):
    """比较旧 VM 记录与新的字段值是否有变化。"""
    for f in VCENTER_TRACKED_FIELDS:
        ov = str(getattr(old_row, f, None) or "")
        nv = str(getattr(new_row, f, None) or "")
        if ov != nv:
            return True
    return False


def _make_vcenter_entry(change_type, new_row, old_row, vcenter_id, vcenter_name):
    """构建 vCenter 历史记录。"""
    row = new_row if new_row is not None else old_row
    dedup_key = f"{row.vm_name}::{vcenter_id}"

    entry = History(
        change_type=change_type,
        source_type=SourceType.vcenter,
        source_id=vcenter_id,
        source_name=vcenter_name,
        dedup_key=dedup_key,
        ip_address=row.ip_address or "",
        mac_address=row.mac_address or "",
    )

    if old_row is not None and new_row is not None:
        entry.change_detail = _build_change_detail(old_row, new_row, VCENTER_TRACKED_FIELDS)

    return entry


def detect_vcenter_changes(db, vcenter_id: int, vcenter_name: str,
                           old_by_key: dict, new_by_key: dict):
    """以 (vm_name, vcenter_id) 为键 diff，写入 History。"""
    if not old_by_key:
        return 0

    count = 0

    for key, new_row in new_by_key.items():
        if key not in old_by_key:
            db.add(_make_vcenter_entry(ChangeType.added, new_row, None,
                                       vcenter_id, vcenter_name))
            count += 1

    for key, old_row in old_by_key.items():
        if key not in new_by_key:
            db.add(_make_vcenter_entry(ChangeType.deleted, None, old_row,
                                       vcenter_id, vcenter_name))
            count += 1

    for key, new_row in new_by_key.items():
        old_row = old_by_key.get(key)
        if old_row is not None and _vcenter_fields_differ(old_row, new_row):
            db.add(_make_vcenter_entry(ChangeType.modified, new_row, old_row,
                                       vcenter_id, vcenter_name))
            count += 1

    return count


F5_TRACKED_FIELDS = [
    "vs_ip", "vs_port", "pool_name", "rule_name",
    "member_ip", "member_port", "member_state", "domain_name",
]


def _f5_fields_differ(old_row, new_row):
    """比较旧 F5 应用映射与新的是否有变化。"""
    for f in F5_TRACKED_FIELDS:
        ov = str(getattr(old_row, f, None) or "")
        nv = str(getattr(new_row, f, None) or "")
        if ov != nv:
            return True
    return False


def _make_f5_entry(change_type, new_row, old_row, f5_device_id, f5_device_name):
    """构建 F5 历史记录。"""
    row = new_row if new_row is not None else old_row
    dedup_key = f"{row.vs_name}::{row.domain_name}::{row.pool_name}::{f5_device_id}"

    entry = History(
        change_type=change_type,
        source_type=SourceType.f5,
        source_id=f5_device_id,
        source_name=f5_device_name,
        dedup_key=dedup_key,
        ip_address=row.vs_ip or "",
        mac_address="",
    )

    if old_row is not None and new_row is not None:
        entry.change_detail = _build_change_detail(old_row, new_row, F5_TRACKED_FIELDS)

    return entry


def detect_f5_changes(db, f5_device_id: int, f5_device_name: str,
                      old_by_key: dict, new_by_key: dict):
    """以 (vs_name, domain_name, pool_name) 为键 diff，写入 F5 History。"""
    if not old_by_key:
        return 0

    count = 0

    for key, new_row in new_by_key.items():
        if key not in old_by_key:
            db.add(_make_f5_entry(ChangeType.added, new_row, None,
                                   f5_device_id, f5_device_name))
            count += 1

    for key, old_row in old_by_key.items():
        if key not in new_by_key:
            db.add(_make_f5_entry(ChangeType.deleted, None, old_row,
                                   f5_device_id, f5_device_name))
            count += 1

    for key, new_row in new_by_key.items():
        old_row = old_by_key.get(key)
        if old_row is not None and _f5_fields_differ(old_row, new_row):
            db.add(_make_f5_entry(ChangeType.modified, new_row, old_row,
                                   f5_device_id, f5_device_name))
            count += 1

    return count


ZDNS_TRACKED_FIELDS = [
    "ip_address", "ip_category", "network_type",
    "ttl", "view_name", "zone_name", "is_enabled",
]


def _zdns_fields_differ(old_row, new_row):
    """比较旧 ZDNS DomainMap 行与新的是否有变化。"""
    for f in ZDNS_TRACKED_FIELDS:
        ov = str(getattr(old_row, f, None) or "")
        nv = str(getattr(new_row, f, None) or "")
        if ov != nv:
            return True
    return False


def _make_zdns_entry(change_type, new_row, old_row, zdns_device_id, zdns_device_name):
    """构建 ZDNS 历史记录。"""
    row = new_row if new_row is not None else old_row
    dedup_key = f"{row.domain_name}::{row.record_type}::{zdns_device_id}"

    entry = History(
        change_type=change_type,
        source_type=SourceType.zdns,
        source_id=zdns_device_id,
        source_name=zdns_device_name,
        dedup_key=dedup_key,
        ip_address=row.ip_address or "",
        mac_address="",
    )

    if old_row is not None and new_row is not None:
        entry.change_detail = _build_change_detail(old_row, new_row, ZDNS_TRACKED_FIELDS)

    return entry


def detect_zdns_changes(db, zdns_device_id: int, zdns_device_name: str,
                         old_by_key: dict, new_by_key: dict):
    """以 (domain_name, record_type) 为键 diff，写入 ZDNS History。"""
    if not old_by_key:
        return 0

    count = 0

    for key, new_row in new_by_key.items():
        if key not in old_by_key:
            db.add(_make_zdns_entry(ChangeType.added, new_row, None,
                                     zdns_device_id, zdns_device_name))
            count += 1

    for key, old_row in old_by_key.items():
        if key not in new_by_key:
            db.add(_make_zdns_entry(ChangeType.deleted, None, old_row,
                                     zdns_device_id, zdns_device_name))
            count += 1

    for key, new_row in new_by_key.items():
        old_row = old_by_key.get(key)
        if old_row is not None and _zdns_fields_differ(old_row, new_row):
            db.add(_make_zdns_entry(ChangeType.modified, new_row, old_row,
                                     zdns_device_id, zdns_device_name))
            count += 1

    return count


QAX_TRACKED_FIELDS = [
    "ipv4", "intranet_ip", "operation_system",
    "cpu", "memory", "disk_size_str", "online_status",
    "run_status", "machine_group",
]


def _qax_fields_differ(old_row, new_row):
    for f in QAX_TRACKED_FIELDS:
        ov = str(getattr(old_row, f, None) or "")
        nv = str(getattr(new_row, f, None) or "")
        if ov != nv:
            return True
    return False


def _make_qax_entry(change_type, new_row, old_row, device_id, device_name):
    row = new_row if new_row is not None else old_row
    # dedup_key 格式: machine_name::machine_uuid::device_id（方便前端展示）
    dedup_key = f"{row.machine_name}::{row.machine_uuid}::{device_id}"

    entry = History(
        change_type=change_type,
        source_type=SourceType.qax,
        source_id=device_id,
        source_name=device_name,
        dedup_key=dedup_key,
        ip_address=row.ipv4 or "",
        mac_address="",
    )

    if old_row is not None and new_row is not None:
        entry.change_detail = _build_change_detail(old_row, new_row, QAX_TRACKED_FIELDS)

    return entry


def detect_qax_changes(db, device_id: int, device_name: str,
                        old_by_key: dict, new_by_key: dict):
    """以 (machine_uuid, device_id) 为键 diff，写入椒图 History。"""
    if not old_by_key:
        return 0

    count = 0

    for key, new_row in new_by_key.items():
        if key not in old_by_key:
            db.add(_make_qax_entry(ChangeType.added, new_row, None,
                                    device_id, device_name))
            count += 1

    for key, old_row in old_by_key.items():
        if key not in new_by_key:
            db.add(_make_qax_entry(ChangeType.deleted, None, old_row,
                                    device_id, device_name))
            count += 1

    for key, new_row in new_by_key.items():
        old_row = old_by_key.get(key)
        if old_row is not None and _qax_fields_differ(old_row, new_row):
            db.add(_make_qax_entry(ChangeType.modified, new_row, old_row,
                                    device_id, device_name))
            count += 1

    return count
