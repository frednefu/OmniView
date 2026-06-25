"""IP availability calculation using Python ipaddress stdlib."""
import ipaddress
from sqlalchemy.orm import Session
from sqlalchemy import func, select

from app.models.scan_result import ScanResult
from app.models.switch import Switch


def _ip_to_int(ip: str) -> int:
    """Convert IPv4 string to 32-bit integer."""
    try:
        return int(ipaddress.IPv4Address(ip))
    except ValueError:
        return 0


def _used_ips_in_subnet(db: Session, net_int: int, broad_int: int) -> set:
    """Return set of IPs from scan_results that fall within the given network range."""
    used = set()
    rows = db.query(ScanResult.ip_address).filter(
        ScanResult.ip_address != "",
        ScanResult.ip_address.isnot(None),
    ).all()
    for (ip,) in rows:
        ip_int = _ip_to_int(ip)
        if net_int < ip_int < broad_int:
            used.add(ip)
    return used


def get_subnet_utilization(db: Session, user_id: int = None, admin: bool = False) -> list[dict]:
    """For each managed subnet, calculate total/used/free IPs."""
    from app.models.subnet import Subnet

    q = db.query(Subnet)
    if user_id:
        if admin:
            q = q.filter((Subnet.created_by == user_id) | (Subnet.created_by == None))
        else:
            q = q.filter(Subnet.created_by == user_id)
    subnets = q.all()
    if not subnets:
        return []

    # Batch-collect all used IPs to avoid repeated scans
    all_used_ips = set()
    all_ip_rows = db.query(ScanResult.ip_address).filter(
        ScanResult.ip_address != "",
        ScanResult.ip_address.isnot(None),
    ).all()
    for (ip,) in all_ip_rows:
        all_used_ips.add(ip)

    result = []
    for sn in subnets:
        try:
            net = ipaddress.IPv4Network(sn.subnet_cidr, strict=False)
        except ValueError:
            continue

        total = net.num_addresses - 2  # exclude network + broadcast
        if total < 0:
            total = 0

        net_int = int(net.network_address)
        broad_int = int(net.broadcast_address)

        used = 0
        for ip_str in all_used_ips:
            ip_int = _ip_to_int(ip_str)
            if net_int < ip_int < broad_int:
                used += 1

        free = max(0, total - used)
        pct = round(used / total * 100, 1) if total > 0 else 0

        result.append({
            "subnet_id": sn.id,
            "subnet_cidr": sn.subnet_cidr,
            "name": sn.name,
            "total_ips": total,
            "used_ips": used,
            "free_ips": free,
            "utilization_pct": pct,
        })

    result.sort(key=lambda x: x["utilization_pct"], reverse=True)
    return result


def get_available_ips(db: Session, subnet_id: int, limit: int = 50) -> dict:
    """Get a list of free IPs in a subnet."""
    from app.models.subnet import Subnet

    sn = db.query(Subnet).get(subnet_id)
    if not sn:
        return {"subnet_cidr": "", "available_ips": [], "total_free": 0}

    try:
        net = ipaddress.IPv4Network(sn.subnet_cidr, strict=False)
    except ValueError:
        return {"subnet_cidr": sn.subnet_cidr, "available_ips": [], "total_free": 0}

    # Collect all used IPs in this subnet
    net_int = int(net.network_address)
    broad_int = int(net.broadcast_address)
    used = _used_ips_in_subnet(db, net_int, broad_int)

    # Exclude network, broadcast, and gateway
    excluded = {str(net.network_address), str(net.broadcast_address)}
    if sn.gateway:
        excluded.add(sn.gateway)

    free = []
    for host in net.hosts():
        ip_str = str(host)
        if ip_str not in used and ip_str not in excluded:
            free.append(ip_str)
            if len(free) >= limit:
                break

    usable = net.num_addresses - 2
    total_free = max(0, usable - len(used - excluded))

    return {
        "subnet_cidr": sn.subnet_cidr,
        "available_ips": free,
        "total_free": total_free,
    }


def get_occupied_ips(
    db: Session, subnet_id: int, page: int = 1, size: int = 50, search: str = "",
) -> dict:
    """返回子网内已占用的 IP 清单，IP+MAC去重，富化 VM 名和域名，带分页和搜索。"""
    from app.models.subnet import Subnet
    from app.models.vm_inventory import VMInventory
    from app.models.zdns import ZDNSDomainMap

    sn = db.query(Subnet).get(subnet_id)
    if not sn:
        return {"subnet_cidr": "", "subnet_name": "", "occupied": [], "total": 0}

    try:
        net = ipaddress.IPv4Network(sn.subnet_cidr, strict=False)
    except ValueError:
        return {"subnet_cidr": sn.subnet_cidr, "subnet_name": sn.name, "occupied": [], "total": 0}

    net_int = int(net.network_address)
    broad_int = int(net.broadcast_address)

    rows = (
        db.query(ScanResult.ip_address, ScanResult.mac_address)
        .filter(
            ScanResult.ip_address != "",
            ScanResult.ip_address.isnot(None),
        )
        .all()
    )

    # IP+MAC 去重
    seen = set()
    ip_mac_list: list[tuple[str, str]] = []
    ip_set: set[str] = set()
    for ip, mac in rows:
        ip_int = _ip_to_int(ip)
        if not (net_int < ip_int < broad_int):
            continue
        key = (ip, (mac or "").lower())
        if key not in seen:
            seen.add(key)
            ip_mac_list.append((ip, mac or ""))
            ip_set.add(ip)

    # 批量查询 VM 名（MAC → vm_name）
    all_macs = list({m.lower() for _, m in ip_mac_list if m})
    mac_to_vm: dict[str, str] = {}
    if all_macs:
        vm_rows = db.query(VMInventory.mac_address, VMInventory.vm_name).all()
        for mac_csv, vm_name in vm_rows:
            if mac_csv and vm_name:
                for m in mac_csv.split(","):
                    m = m.strip().lower()
                    if m and m in all_macs:
                        existing = mac_to_vm.get(m, "")
                        mac_to_vm[m] = vm_name if not existing else existing + "," + vm_name

    # 批量查询域名（IP → domain_name）
    ip_to_domain: dict[str, str] = {}
    dm_rows = db.query(ZDNSDomainMap.ip_address, ZDNSDomainMap.domain_name).filter(
        ZDNSDomainMap.ip_address.in_(ip_set),
        ZDNSDomainMap.domain_name != "",
    ).distinct().all()
    for ip, domain in dm_rows:
        existing = ip_to_domain.get(ip, "")
        ip_to_domain[ip] = domain if not existing else existing + "," + domain

    occupied = []
    for ip, mac in ip_mac_list:
        vm_name = mac_to_vm.get(mac.lower(), "")
        domain = ip_to_domain.get(ip, "")
        occupied.append({
            "ip": ip,
            "mac": mac,
            "vm_name": vm_name,
            "domain": domain,
        })

    # 搜索过滤
    if search:
        q = search.lower()
        occupied = [r for r in occupied if (
            q in r["ip"].lower() or q in r["mac"].lower()
            or q in r["vm_name"].lower() or q in r["domain"].lower()
        )]

    total = len(occupied)
    start = (page - 1) * size
    paged = sorted(occupied, key=lambda x: _ip_to_int(x["ip"]))[start:start + size]

    return {
        "subnet_cidr": sn.subnet_cidr,
        "subnet_name": sn.name,
        "occupied": paged,
        "total": total,
    }
