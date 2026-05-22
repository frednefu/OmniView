"""vCenter 虚拟机清单采集引擎 — 基于 pyVmomi SDK。"""
import ssl
import asyncio
import logging
from datetime import datetime

from app.database import SessionLocal
from app.models.vcenter import VCenter
from app.models.vm_inventory import VMInventory

logger = logging.getLogger(__name__)

# 延迟导入，允许在未安装 pyVmomi 的环境下仍然能加载模块
try:
    from pyVim.connect import SmartConnect, Disconnect
    from pyVmomi import vim
    PYVMOMI_AVAILABLE = True
except ImportError:
    PYVMOMI_AVAILABLE = False
    logger.warning("pyVmomi 未安装，vCenter 扫描功能不可用")


def _connect(host: str, username: str, password: str, port: int = 443):
    """连接 vCenter，返回 ServiceInstance。"""
    context = ssl._create_unverified_context()
    si = SmartConnect(host=host, user=username, pwd=password, port=port, sslContext=context)
    return si


def _get_datacenter(obj):
    parent = obj.parent
    while parent:
        if isinstance(parent, vim.Datacenter):
            return parent
        parent = getattr(parent, "parent", None)
    return None


def _get_vm_folder_path(vm):
    dc = _get_datacenter(vm)
    names = []
    parent = vm.parent
    while parent:
        if isinstance(parent, vim.Folder):
            if dc and parent == dc.vmFolder:
                break
            names.append(parent.name)
        parent = getattr(parent, "parent", None)
        if isinstance(parent, vim.Datacenter):
            break
    names.reverse()
    return "-".join(names)


def _get_resource_pool_path(vm):
    rp = vm.resourcePool
    names = []
    while rp and isinstance(rp, vim.ResourcePool):
        parent = getattr(rp, "parent", None)
        if isinstance(parent, (vim.ClusterComputeResource, vim.ComputeResource)):
            break
        names.append(rp.name)
        rp = parent
    names.reverse()
    return "-".join(names)


def _get_vm_cluster(vm):
    try:
        host = vm.runtime.host
        if host:
            parent = host.parent
            if isinstance(parent, (vim.ClusterComputeResource, vim.ComputeResource)):
                return parent.name
    except Exception:
        pass
    return ""


def _get_vm_host(vm):
    try:
        if vm.runtime.host:
            return vm.runtime.host.name
    except Exception:
        pass
    return ""


def _get_vm_ips(vm):
    ips = []
    try:
        if vm.guest and vm.guest.ipAddress:
            ips.append(vm.guest.ipAddress)
    except Exception:
        pass
    try:
        if vm.guest and vm.guest.net:
            for net in vm.guest.net:
                if net.ipAddress:
                    for ip in net.ipAddress:
                        if ip and ip not in ips:
                            ips.append(ip)
    except Exception:
        pass
    return ", ".join(ips)


def _parse_vlan_spec(vlan_spec):
    if not vlan_spec:
        return ""
    try:
        if hasattr(vlan_spec, "inherited") and vlan_spec.inherited:
            return "继承"
    except Exception:
        pass
    if hasattr(vlan_spec, "vlanId"):
        vlan_id = vlan_spec.vlanId
        if isinstance(vlan_id, list):
            ranges = []
            for item in vlan_id:
                start = getattr(item, "start", None)
                end = getattr(item, "end", None)
                if start is not None and end is not None:
                    if start == end:
                        ranges.append(str(start))
                    else:
                        ranges.append(f"{start}-{end}")
            return ",".join(ranges)
        return str(vlan_id)
    if hasattr(vlan_spec, "pvlanId"):
        return f"PVLAN:{vlan_spec.pvlanId}"
    return type(vlan_spec).__name__


def _get_dvpg_vlan(dvpg):
    try:
        vlan_spec = dvpg.config.defaultPortConfig.vlan
        return _parse_vlan_spec(vlan_spec)
    except Exception:
        return ""


def _build_dvpg_map(content):
    dvpg_map = {}
    container = content.viewManager.CreateContainerView(
        content.rootFolder, [vim.dvs.DistributedVirtualPortgroup], True
    )
    for dvpg in container.view:
        try:
            dvpg_map[dvpg.key] = dvpg
        except Exception:
            pass
    container.Destroy()
    return dvpg_map


def _build_standard_pg_vlan_map(content):
    pg_vlan_map = {}
    container = content.viewManager.CreateContainerView(
        content.rootFolder, [vim.HostSystem], True
    )
    for host in container.view:
        try:
            if not host.config or not host.config.network:
                continue
            for pg in host.config.network.portgroup:
                pg_name = pg.spec.name
                vlan_id = str(pg.spec.vlanId)
                if pg_name not in pg_vlan_map:
                    pg_vlan_map[pg_name] = set()
                pg_vlan_map[pg_name].add(vlan_id)
        except Exception:
            pass
    container.Destroy()
    result = {}
    for pg_name, vlan_set in pg_vlan_map.items():
        result[pg_name] = ",".join(sorted(vlan_set))
    return result


def _get_vm_nic_info(vm, dvpg_map, standard_pg_vlan_map):
    mac_list = []
    network_list = []
    vlan_list = []
    try:
        devices = vm.config.hardware.device
    except Exception:
        return "", "", ""
    for device in devices:
        if not isinstance(device, vim.vm.device.VirtualEthernetCard):
            continue
        mac = getattr(device, "macAddress", "")
        if mac:
            mac_list.append(mac)
        network_name = ""
        vlan_id = ""
        backing = device.backing
        if isinstance(backing, vim.vm.device.VirtualEthernetCard.DistributedVirtualPortBackingInfo):
            try:
                pg_key = backing.port.portgroupKey
                dvpg = dvpg_map.get(pg_key)
                if dvpg:
                    network_name = dvpg.name
                    vlan_id = _get_dvpg_vlan(dvpg)
            except Exception:
                pass
        else:
            try:
                if hasattr(backing, "deviceName") and backing.deviceName:
                    network_name = backing.deviceName
                elif hasattr(backing, "network") and backing.network:
                    network_name = backing.network.name
                if network_name:
                    vlan_id = standard_pg_vlan_map.get(network_name, "")
            except Exception:
                pass
        if not network_name:
            try:
                network_name = device.deviceInfo.summary
            except Exception:
                network_name = ""
        if network_name:
            network_list.append(network_name)
        if vlan_id:
            vlan_list.append(vlan_id)
    mac_list = list(dict.fromkeys(mac_list))
    network_list = list(dict.fromkeys(network_list))
    vlan_list = list(dict.fromkeys(vlan_list))
    return ", ".join(mac_list), ", ".join(network_list), ", ".join(vlan_list)


def _get_vm_list(content, cluster_name=""):
    if cluster_name:
        from pyVmomi import vim as _vim
        container = content.viewManager.CreateContainerView(
            content.rootFolder, [_vim.ClusterComputeResource], True
        )
        cluster = None
        for c in container.view:
            if c.name == cluster_name:
                cluster = c
                break
        container.Destroy()
        if not cluster:
            return []
        container = content.viewManager.CreateContainerView(
            cluster, [vim.VirtualMachine], True
        )
    else:
        container = content.viewManager.CreateContainerView(
            content.rootFolder, [vim.VirtualMachine], True
        )
    vms = list(container.view)
    container.Destroy()
    return vms


def _do_vcenter_scan(host: str, username: str, password: str, port: int) -> list:
    """同步扫描 vCenter，返回 VM 数据行列表。"""
    if not PYVMOMI_AVAILABLE:
        raise RuntimeError("pyVmomi 未安装，无法执行 vCenter 扫描")

    si = _connect(host, username, password, port)
    try:
        content = si.RetrieveContent()
        dvpg_map = _build_dvpg_map(content)
        standard_pg_vlan_map = _build_standard_pg_vlan_map(content)
        vms = _get_vm_list(content)

        rows = []
        for vm in vms:
            try:
                dc = _get_datacenter(vm)
                datacenter_name = dc.name if dc else ""
                cluster_name = _get_vm_cluster(vm)
                host_name = _get_vm_host(vm)
                resource_pool_path = _get_resource_pool_path(vm)
                folder_path = _get_vm_folder_path(vm)
                vm_name = vm.name

                try:
                    power_state = str(vm.runtime.powerState)
                except Exception:
                    power_state = ""

                ip_address = _get_vm_ips(vm)
                mac_address, network_name, vlan_id = _get_vm_nic_info(vm, dvpg_map, standard_pg_vlan_map)

                try:
                    os_name = vm.config.guestFullName or ""
                except Exception:
                    os_name = ""

                try:
                    cpu_num = vm.config.hardware.numCPU
                except Exception:
                    cpu_num = None

                try:
                    memory_gb = round(vm.config.hardware.memoryMB / 1024, 2)
                except Exception:
                    memory_gb = None

                rows.append({
                    "datacenter": datacenter_name,
                    "cluster": cluster_name,
                    "esxi_host": host_name,
                    "resource_pool": resource_pool_path,
                    "vm_folder": folder_path,
                    "vm_name": vm_name,
                    "power_state": power_state,
                    "ip_address": ip_address,
                    "mac_address": mac_address,
                    "network_name": network_name,
                    "vlan_id": vlan_id,
                    "os_name": os_name,
                    "cpu_count": cpu_num,
                    "memory_gb": memory_gb,
                    "remark": "",
                })
            except Exception:
                logger.exception("处理 VM %s 失败", getattr(vm, "name", "未知"))
        return rows
    finally:
        Disconnect(si)


async def _run_vcenter_scan_async(vcenter_id: int):
    """异步扫描入口 — 在线程池中运行同步 pyVmomi 调用。"""
    db = SessionLocal()
    vc = None
    try:
        vc = db.query(VCenter).get(vcenter_id)
        if not vc or not vc.is_active:
            return

        vc.last_scan_status = "running"
        vc.last_scan_error = None
        db.commit()

        loop = asyncio.get_running_loop()
        rows = await loop.run_in_executor(None, _do_vcenter_scan, vc.host, vc.username, vc.password, vc.port)

        # 新 session 写数据
        write_db = SessionLocal()
        try:
            write_db.query(VMInventory).filter(VMInventory.vcenter_id == vcenter_id).delete()
            for r in rows:
                write_db.add(VMInventory(vcenter_id=vcenter_id, **r))
            write_db.commit()
            count = len(rows)
        except Exception:
            write_db.rollback()
            raise
        finally:
            write_db.close()

        db_vc = db.query(VCenter).get(vcenter_id)
        db_vc.last_scan_status = "success"
        db_vc.last_scan_time = datetime.now()
        db_vc.last_vm_count = count
        db_vc.last_scan_error = None
        db.commit()
        logger.info("vCenter %s 扫描完成，共 %s 台 VM", vc.host, count)
    except Exception as e:
        logger.exception("vCenter %s 扫描失败", vc.host if vc else vcenter_id)
        try:
            db_vc = db.query(VCenter).get(vcenter_id)
            if db_vc:
                db_vc.last_scan_status = "failed"
                db_vc.last_scan_error = str(e)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


async def trigger_vcenter_scan(vcenter: VCenter):
    """触发异步扫描，立即返回。"""
    db = SessionLocal()
    try:
        db_vc = db.query(VCenter).get(vcenter.id)
        db_vc.last_scan_status = "running"
        db_vc.last_scan_error = None
        db.commit()
    finally:
        db.close()
    asyncio.create_task(_run_vcenter_scan_async(vcenter.id))


async def test_vcenter_connection(host: str, username: str, password: str, port: int = 443) -> dict:
    """测试 vCenter 连接。"""
    if not PYVMOMI_AVAILABLE:
        return {"ok": False, "message": "pyVmomi 未安装"}
    loop = asyncio.get_running_loop()
    try:
        si = await loop.run_in_executor(None, _connect, host, username, password, port)
        content = si.RetrieveContent()
        name = content.about.fullName
        version = content.about.version
        Disconnect(si)
        return {"ok": True, "message": f"连接成功 ({name} {version})"}
    except Exception as e:
        return {"ok": False, "message": f"连接失败: {str(e)}"}
