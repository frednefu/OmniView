"""IP availability calculation using Python ipaddress stdlib."""
import ipaddress
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.scan_result import ScanResult


def _ip_to_int(ip: str) -> int:
    """Convert IPv4 string to 32-bit integer."""
    try:
        return int(ipaddress.IPv4Address(ip))
    except ValueError:
        return 0


def get_subnet_utilization(db: Session) -> list[dict]:
    """For each managed subnet, calculate total/used/free IPs."""
    from app.models.subnet import Subnet

    subnets = db.query(Subnet).filter(Subnet.is_managed == True).all()
    result = []
    for sn in subnets:
        try:
            net = ipaddress.IPv4Network(sn.subnet_cidr, strict=False)
        except ValueError:
            continue

        total = net.num_addresses - 2  # exclude network + broadcast
        if total < 0:
            total = 0

        # Count used IPs within this subnet
        net_int = int(net.network_address)
        broad_int = int(net.broadcast_address)
        used = db.query(func.count(ScanResult.id)).filter(
            ScanResult.ip_address != "",
            ScanResult.ip_address.isnot(None),
        ).all()[0][0]

        # We can't easily do range check in pure SQL without INET_ATON,
        # so count from Python side for accuracy
        used = 0
        rows = db.query(ScanResult.ip_address).filter(
            ScanResult.ip_address != "",
        ).all()
        for (ip,) in rows:
            ip_int = _ip_to_int(ip)
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
    used_ips = set()
    net_int = int(net.network_address)
    broad_int = int(net.broadcast_address)
    rows = db.query(ScanResult.ip_address).filter(ScanResult.ip_address != "").all()
    for (ip,) in rows:
        ip_int = _ip_to_int(ip)
        if net_int < ip_int < broad_int:
            used_ips.add(ip)

    # Exclude network, broadcast, and gateway
    excluded = {str(net.network_address), str(net.broadcast_address)}
    if sn.gateway:
        excluded.add(sn.gateway)

    free = []
    for host in net.hosts():
        ip_str = str(host)
        if ip_str not in used_ips and ip_str not in excluded:
            free.append(ip_str)
            if len(free) >= limit:
                break

    return {
        "subnet_cidr": sn.subnet_cidr,
        "available_ips": free,
        "total_free": max(0, net.num_addresses - 2 - len(used_ips) - len(excluded & used_ips)),
    }
