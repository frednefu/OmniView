"""变更检测：以 (IP, MAC, 物理端口) 为复合键比较新旧扫描结果，生成历史记录。"""
from app.models.history import History, ChangeType

TRACKED_FIELDS = ["vlan_bd", "vlan_type", "virtual_port", "switch_type"]


def _fields_differ(old_r, new_vlan_bd, new_vlan_type, new_virtual_port, new_switch_type):
    """比较旧记录与新的字段值是否有变化。"""
    return (
        str(old_r.vlan_bd or "") != str(new_vlan_bd or "") or
        str(old_r.vlan_type or "") != str(new_vlan_type or "") or
        str(old_r.virtual_port or "") != str(new_virtual_port or "") or
        str(old_r.switch_type or "") != str(new_switch_type or "")
    )


def _make_entry(change_type, switch_id, scan_log_id, old_r, new_r):
    """根据旧/新扫描结果构建 History 记录。"""
    entry = History(
        change_type=change_type,
        switch_id=switch_id,
        scan_log_id=scan_log_id,
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
    return entry


def detect_changes(db, switch_id: int, scan_log_id: int,
                   old_by_key: dict, new_by_key: dict, handled_old_keys: set):
    """
    以 (IP, MAC, physical_port) 为复合键进行 diff：
    - 新键不在旧键中 → added（仅当有历史基线时）
    - 旧键未被处理（已不在新数据中） → deleted
    - 旧键被处理但新旧行 ID 不同（字段变化导致新行插入） → modified
    """
    # 首次扫描无基线，不产生历史记录
    if not old_by_key:
        return 0

    count = 0

    for key, new_r in new_by_key.items():
        if key not in old_by_key:
            db.add(_make_entry(ChangeType.added, switch_id, scan_log_id, None, new_r))
            count += 1

    for key, old_r in old_by_key.items():
        if key not in handled_old_keys:
            db.add(_make_entry(ChangeType.deleted, switch_id, scan_log_id, old_r, None))
            count += 1

    for key in handled_old_keys:
        old_r = old_by_key.get(key)
        new_r = new_by_key.get(key)
        if old_r and new_r and old_r.id != new_r.id:
            db.add(_make_entry(ChangeType.modified, switch_id, scan_log_id, old_r, new_r))
            count += 1

    return count
