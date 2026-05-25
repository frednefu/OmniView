"""vCenter 虚拟机清单采集引擎 — 基于 pyVmomi SDK。"""
import ssl
import asyncio
import logging
from datetime import datetime

from app.database import SessionLocal
from app.models.vcenter import VCenter
from app.models.vm_inventory import VMInventory
from app.models.esxi_host import EsxiHost
from app.models.datastore import Datastore

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


def _collect_vm_storage(vm):
    """采集 VM 存储使用情况（置备空间、已用空间），单位 GB。"""
    provisioned = None
    used = None
    try:
        storage = vm.summary.storage
        if storage:
            if storage.committed is not None:
                provisioned = round(storage.committed / (1024 ** 3), 2)
            if storage.uncommitted is not None:
                uncommitted = round(storage.uncommitted / (1024 ** 3), 2)
            if provisioned is not None and storage.uncommitted is not None:
                used = round(provisioned - round(storage.uncommitted / (1024 ** 3), 2), 2)
    except Exception:
        pass
    return provisioned, used


def _collect_esxi_hosts(content):
    """采集所有 ESXi 主机信息。"""
    hosts = []
    try:
        container = content.viewManager.CreateContainerView(
            content.rootFolder, [vim.HostSystem], True
        )
        for host in container.view:
            try:
                summary = host.summary
                hardware = summary.hardware if summary else None
                config = host.config

                host_name = host.name or ""
                # 管理 IP
                ip_addr = ""
                try:
                    if config and config.network and config.network.vnic:
                        for vnic in config.network.vnic:
                            if vnic.spec and vnic.spec.ip and vnic.spec.ip.ipAddress:
                                ip_addr = vnic.spec.ip.ipAddress
                                break
                except Exception:
                    pass

                processor_type = hardware.cpuModel if hardware else ""
                logical_processors = hardware.numCpuThreads if hardware else 0
                memory_gb = round(hardware.memorySize / (1024 ** 3), 1) if hardware and hardware.memorySize else 0.0
                hypervisor_type = config.product.fullName if config and config.product else ""

                nic_count = 0
                try:
                    if config and config.network and config.network.pnic:
                        nic_count = len(config.network.pnic)
                except Exception:
                    pass

                status = "connected" if summary.runtime.connectionState == "connected" else str(summary.runtime.connectionState) if summary and summary.runtime else ""

                hosts.append({
                    "host_name": host_name,
                    "ip_address": ip_addr,
                    "processor_type": processor_type,
                    "logical_processors": logical_processors,
                    "memory_gb": memory_gb,
                    "hypervisor_type": hypervisor_type,
                    "nic_count": nic_count,
                    "status": status,
                })
            except Exception:
                logger.exception("采集 ESXi 主机 %s 失败", getattr(host, "name", "未知"))
        container.Destroy()
    except Exception:
        logger.exception("创建 HostSystem ContainerView 失败")
    return hosts


def _collect_datastores(content):
    """采集所有 Datastore 信息。"""
    datastores = []
    try:
        container = content.viewManager.CreateContainerView(
            content.rootFolder, [vim.Datastore], True
        )
        for ds in container.view:
            try:
                summary = ds.summary
                ds_name = ds.name or ""
                ds_status = "accessible" if summary.accessible else "inaccessible" if summary else ""
                ds_type = summary.type if summary else ""
                capacity_gb = round(summary.capacity / (1024 ** 3), 1) if summary and summary.capacity else 0.0
                free_gb = round(summary.freeSpace / (1024 ** 3), 1) if summary and summary.freeSpace else 0.0

                host_count = 0
                try:
                    host_count = len(ds.host) if ds.host else 0
                except Exception:
                    pass
                if host_count > 1:
                    if ds_type and "NFS" in ds_type.upper():
                        storage_type = "共享NAS"
                    else:
                        storage_type = "共享存储"
                else:
                    storage_type = "本地存储"

                datastores.append({
                    "datastore_name": ds_name,
                    "status": ds_status,
                    "ds_type": ds_type,
                    "capacity_gb": capacity_gb,
                    "free_gb": free_gb,
                    "mounted_host_count": host_count,
                    "storage_type": storage_type,
                })
            except Exception:
                logger.exception("采集 Datastore %s 失败", getattr(ds, "name", "未知"))
        container.Destroy()
    except Exception:
        logger.exception("创建 Datastore ContainerView 失败")
    return datastores


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


def _do_vcenter_scan(host: str, username: str, password: str, port: int) -> dict:
    """同步扫描 vCenter，返回 {"vms": [...], "hosts": [...], "datastores": [...]}。"""
    if not PYVMOMI_AVAILABLE:
        raise RuntimeError("pyVmomi 未安装，无法执行 vCenter 扫描")

    si = _connect(host, username, password, port)
    try:
        content = si.RetrieveContent()
        dvpg_map = _build_dvpg_map(content)
        standard_pg_vlan_map = _build_standard_pg_vlan_map(content)
        vms = _get_vm_list(content)

        # 采集 ESXi 主机和 Datastore
        esxi_hosts = _collect_esxi_hosts(content)
        datastores = _collect_datastores(content)

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

                # 读取 VM 注解（备注）
                try:
                    remark = str(vm.config.annotation or "") if vm.config else ""
                except Exception:
                    remark = ""

                # VM 存储
                provisioned_gb, used_gb = _collect_vm_storage(vm)

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
                    "provisioned_gb": provisioned_gb,
                    "used_gb": used_gb,
                    "remark": remark,
                })
            except Exception:
                logger.exception("处理 VM %s 失败", getattr(vm, "name", "未知"))
        return {"vms": rows, "hosts": esxi_hosts, "datastores": datastores}
    finally:
        Disconnect(si)


def _normalize_mac(mac: str) -> str:
    """去掉 MAC 地址中的分隔符，统一小写用于比较。"""
    for sep in (":", "-", "."):
        mac = mac.replace(sep, "")
    return mac.lower()


def _fill_ips_from_mac(db, vcenter_id: int):
    """扫描后处理：对 IP 为空的 VM，通过 MAC 从交换机 scan_results 补充 IP。"""
    from app.models.scan_result import ScanResult

    vms = db.query(VMInventory).filter(
        VMInventory.vcenter_id == vcenter_id,
        (VMInventory.ip_address == "") | (VMInventory.ip_address.is_(None)),
        VMInventory.mac_address != "",
        VMInventory.mac_address.isnot(None),
    ).all()

    if not vms:
        return

    rows = db.query(ScanResult.ip_address, ScanResult.mac_address).filter(
        ScanResult.ip_address != "",
        ScanResult.mac_address != "",
    ).all()

    # 构建归一化 MAC → IP 列表 映射
    mac_to_ips: dict[str, list[str]] = {}
    for ip, mac in rows:
        norm = _normalize_mac(mac)
        if norm not in mac_to_ips:
            mac_to_ips[norm] = []
        if ip not in mac_to_ips[norm]:
            mac_to_ips[norm].append(ip)

    updated = 0
    for vm in vms:
        vm_macs = [m.strip() for m in vm.mac_address.split(",") if m.strip()]
        found_ips = set()
        for m in vm_macs:
            norm = _normalize_mac(m)
            for ip in mac_to_ips.get(norm, []):
                found_ips.add(ip)
        if found_ips:
            vm.ip_address = ", ".join(sorted(found_ips))
            updated += 1

    if updated:
        logger.info("vCenter %s: 通过 MAC 补充了 %s 台 VM 的 IP", vcenter_id, updated)


async def _run_vcenter_scan_async(vcenter_id: int, scan_log_id: int | None = None):
    """异步扫描入口 — 在线程池中运行同步 pyVmomi 调用。"""
    from app.services.history_service import detect_vcenter_changes
    from app.models.scan_log import ScanLog, ScanStatus

    start_time = datetime.now()

    db = SessionLocal()
    vc = None
    count = 0
    host_count = 0
    ds_count = 0
    try:
        vc = db.query(VCenter).get(vcenter_id)
        if not vc or not vc.is_active:
            return

        vc.last_scan_status = "running"
        vc.last_scan_error = None
        db.commit()

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, _do_vcenter_scan, vc.host, vc.username, vc.password, vc.port)
        rows = result["vms"]
        esxi_hosts = result["hosts"]
        datastores = result["datastores"]

        # 新 session 写数据（快照 → DELETE → INSERT → diff → 历史）
        write_db = SessionLocal()
        try:
            # 快照旧 VM 数据
            old_rows = write_db.query(VMInventory).filter(
                VMInventory.vcenter_id == vcenter_id
            ).all()
            old_by_key = {}
            for r in old_rows:
                old_by_key[(r.vm_name, r.vcenter_id)] = r

            # DELETE + INSERT VMs
            write_db.query(VMInventory).filter(VMInventory.vcenter_id == vcenter_id).delete()
            for r in rows:
                write_db.add(VMInventory(vcenter_id=vcenter_id, **r))

            # ESXi 主机：DELETE + INSERT
            write_db.query(EsxiHost).filter(EsxiHost.vcenter_id == vcenter_id).delete()
            for h in esxi_hosts:
                write_db.add(EsxiHost(vcenter_id=vcenter_id, **h))
            host_count = len(esxi_hosts)

            # Datastore：DELETE + INSERT
            write_db.query(Datastore).filter(Datastore.vcenter_id == vcenter_id).delete()
            for ds in datastores:
                write_db.add(Datastore(vcenter_id=vcenter_id, **ds))
            ds_count = len(datastores)

            # 扫描后处理：通过 MAC 从交换机 scan_results 补充缺失 IP
            _fill_ips_from_mac(write_db, vcenter_id)

            # 构建新数据映射用于 diff
            new_rows = write_db.query(VMInventory).filter(
                VMInventory.vcenter_id == vcenter_id
            ).all()
            new_by_key = {}
            for r in new_rows:
                new_by_key[(r.vm_name, r.vcenter_id)] = r

            # 写入历史
            detect_vcenter_changes(write_db, vcenter_id, vc.name, old_by_key, new_by_key)

            write_db.commit()
            count = len(rows)
        except Exception:
            write_db.rollback()
            raise
        finally:
            write_db.close()

        duration = round((datetime.now() - start_time).total_seconds(), 1)
        db_vc = db.query(VCenter).get(vcenter_id)
        if db_vc:
            db_vc.last_scan_status = "success"
            db_vc.last_scan_time = datetime.now()
            db_vc.last_scan_duration = duration
            db_vc.last_vm_count = count
            db_vc.last_scan_error = None
            db.commit()
        logger.info("vCenter %s 扫描完成，VM=%s 主机=%s 存储=%s，耗时 %ss", vc.host, count, host_count, ds_count, duration)
    except Exception as e:
        duration = round((datetime.now() - start_time).total_seconds(), 1)
        logger.exception("vCenter %s 扫描失败", vc.host if vc else vcenter_id)
        try:
            db_vc = db.query(VCenter).get(vcenter_id)
            if db_vc:
                db_vc.last_scan_status = "failed"
                db_vc.last_scan_error = str(e)
                db_vc.last_scan_duration = duration
                db.commit()
        except Exception:
            pass
    finally:
        db.close()

    # 更新扫描日志
    if scan_log_id:
        _db = SessionLocal()
        try:
            log = _db.query(ScanLog).get(scan_log_id)
            if log:
                log.status = ScanStatus.success if count > 0 else ScanStatus.success
                log.hosts_found = count
                log.completed_at = datetime.now()
                if log.started_at:
                    log.duration_seconds = round((datetime.now() - log.started_at).total_seconds(), 1)
                _db.commit()
        except Exception:
            pass
        finally:
            _db.close()


async def trigger_vcenter_scan(vcenter: VCenter, triggered_by: str = "manual") -> int:
    """触发异步扫描，立即返回。返回 scan_log_id。"""
    from app.models.scan_log import ScanLog, ScanStatus, TriggerType

    db = SessionLocal()
    try:
        db_vc = db.query(VCenter).get(vcenter.id)
        db_vc.last_scan_status = "running"
        db_vc.last_scan_error = None

        trigger = TriggerType.manual if triggered_by == "manual" else TriggerType.scheduled
        scan_log = ScanLog(
            source_type="vcenter",
            source_id=vcenter.id,
            source_name=vcenter.name,
            status=ScanStatus.running,
            triggered_by=trigger,
            started_at=datetime.now(),
        )
        db.add(scan_log)
        db.commit()
        db.refresh(scan_log)
        scan_log_id = scan_log.id
    finally:
        db.close()
    asyncio.create_task(_run_vcenter_scan_async(vcenter.id, scan_log_id))
    return scan_log_id


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
