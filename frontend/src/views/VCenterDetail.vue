<template>
  <div class="vcenter-detail">
    <div class="page-header">
      <div class="header-left">
        <el-button text @click="$router.back()">
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
        <h2>{{ vcenter?.name || 'vCenter 详情' }}</h2>
      </div>
      <el-button v-if="authStore.isAdmin" type="primary" @click="handleScan" :loading="scanning">
        <el-icon><Refresh /></el-icon>立即扫描
      </el-button>
    </div>

    <el-descriptions v-if="vcenter" :column="3" border size="small" class="info-card">
      <el-descriptions-item label="主机地址">{{ vcenter.host }}</el-descriptions-item>
      <el-descriptions-item label="用户名">{{ vcenter.username }}</el-descriptions-item>
      <el-descriptions-item label="端口">{{ vcenter.port }}</el-descriptions-item>
      <el-descriptions-item label="扫描间隔">{{ vcenter.scan_interval > 0 ? vcenter.scan_interval + 's' : '手动' }}</el-descriptions-item>
      <el-descriptions-item label="状态">
        <el-tag :type="vcenter.is_active ? 'success' : 'info'" size="small">
          {{ vcenter.is_active ? '启用' : '禁用' }}
        </el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="扫描状态">
        <div style="display:flex;align-items:center;gap:6px;">
          <el-tag v-if="vcenter.last_scan_status === 'success'" type="success" size="small">成功</el-tag>
          <el-tag v-else-if="vcenter.last_scan_status === 'failed'" type="danger" size="small">失败</el-tag>
          <el-tag v-else-if="vcenter.last_scan_status === 'running'" type="warning" size="small">扫描中</el-tag>
          <span v-else style="color:#c0c4cc;">未扫描</span>
          <span v-if="vcenter.last_scan_duration" style="color:#909399;font-size:12px;">耗时 {{ vcenter.last_scan_duration }}s</span>
        </div>
      </el-descriptions-item>
    </el-descriptions>

    <div v-if="vcenter?.last_scan_error" style="margin-top:12px;">
      <el-alert :title="'扫描错误: ' + vcenter.last_scan_error" type="error" show-icon :closable="false" />
    </div>

    <el-tabs v-model="activeTab" style="margin-top:20px;" @tab-change="onTabChange">
      <el-tab-pane label="虚拟机清单" name="vms">
        <template #label>
          <span>虚拟机清单（{{ total }} 台）</span>
        </template>
        <div class="filter-bar">
          <el-input v-model="search" placeholder="搜索名称、IP、MAC、OS、集群、主机、网络、文件夹..." clearable style="width:300px"
            @keyup.enter="page=1;fetchVMs()" @clear="page=1;fetchVMs()" />
          <el-select v-model="filterPower" clearable placeholder="电源状态" style="width:110px" @change="page=1;fetchVMs()">
            <el-option v-for="s in filterOptions.power_states" :key="s" :label="s==='poweredOn'?'开机':s==='poweredOff'?'关机':s" :value="s" />
          </el-select>
          <el-select v-model="filterOS" clearable placeholder="操作系统" style="width:140px" filterable @change="page=1;fetchVMs()">
            <el-option v-for="s in filterOptions.os_names" :key="s" :label="s" :value="s" />
          </el-select>
          <el-select v-model="filterNetwork" clearable placeholder="网络" style="width:130px" filterable @change="page=1;fetchVMs()">
            <el-option v-for="s in filterOptions.networks" :key="s" :label="s" :value="s" />
          </el-select>
          <el-select v-model="filterFolder" clearable placeholder="文件夹" style="width:130px" filterable @change="page=1;fetchVMs()">
            <el-option v-for="s in filterOptions.folders" :key="s" :label="s" :value="s" />
          </el-select>
          <el-button type="primary" @click="page=1;fetchVMs()">查询</el-button>
          <el-button @click="exportExcel" :loading="exporting">
            <el-icon><Download /></el-icon>导出 Excel
          </el-button>
        </div>

        <el-table :data="vms" stripe v-loading="loading" style="width:100%" max-height="600">
          <template #empty>
            <el-empty description="暂无虚拟机数据，请先触发扫描" :image-size="60" />
          </template>
          <el-table-column prop="vm_name" label="虚拟机名称" min-width="180" fixed show-overflow-tooltip />
          <el-table-column prop="power_state" label="电源" width="90">
            <template #default="{ row }">
              <el-tag :type="row.power_state === 'poweredOn' ? 'success' : 'info'" size="small">
                {{ row.power_state === 'poweredOn' ? '开机' : row.power_state === 'poweredOff' ? '关机' : row.power_state }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="ip_address" label="IP 地址" min-width="140" show-overflow-tooltip />
          <el-table-column prop="mac_address" label="MAC 地址" min-width="140" show-overflow-tooltip />
          <el-table-column prop="os_name" label="操作系统" min-width="160" show-overflow-tooltip />
          <el-table-column prop="cpu_count" label="CPU" width="60" />
          <el-table-column prop="memory_gb" label="内存(GB)" width="90" />
          <el-table-column prop="datacenter" label="数据中心" min-width="120" show-overflow-tooltip />
          <el-table-column prop="cluster" label="集群" min-width="120" show-overflow-tooltip />
          <el-table-column prop="esxi_host" label="ESXi 主机" min-width="150" show-overflow-tooltip />
          <el-table-column prop="network_name" label="网络" min-width="120" show-overflow-tooltip />
          <el-table-column prop="vlan_id" label="VLAN" width="80" />
          <el-table-column prop="resource_pool" label="资源池" min-width="120" show-overflow-tooltip />
          <el-table-column prop="vm_folder" label="文件夹" min-width="120" show-overflow-tooltip />
          <el-table-column prop="remark" label="备注" width="100" show-overflow-tooltip />
        </el-table>

        <div class="pagination-wrap" v-if="total > 0">
          <el-pagination
            v-model:current-page="page" :page-size="size" :total="total"
            layout="total, prev, pager, next" @current-change="fetchVMs" />
        </div>
      </el-tab-pane>

      <el-tab-pane label="ESXi 主机" name="hosts">
        <template #label>
          <span>ESXi 主机（{{ hostTotal }} 台）</span>
        </template>
        <el-table :data="hosts" stripe v-loading="loadingHosts" style="width:100%" max-height="600">
          <template #empty>
            <el-empty description="暂无 ESXi 主机数据，请先触发扫描" :image-size="60" />
          </template>
          <el-table-column prop="host_name" label="主机名" min-width="200" fixed show-overflow-tooltip />
          <el-table-column prop="ip_address" label="管理 IP" min-width="140" show-overflow-tooltip />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.status === 'connected' ? 'success' : 'danger'" size="small">
                {{ row.status === 'connected' ? '在线' : row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="processor_type" label="处理器类型" min-width="240" show-overflow-tooltip />
          <el-table-column prop="logical_processors" label="逻辑处理器" width="100" align="center" />
          <el-table-column prop="memory_gb" label="内存(GB)" width="100" align="center" />
          <el-table-column prop="hypervisor_type" label="Hypervisor" min-width="200" show-overflow-tooltip />
          <el-table-column prop="nic_count" label="网卡数" width="80" align="center" />
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="存储器" name="datastores">
        <template #label>
          <span>存储器（{{ dsTotal }} 个）</span>
        </template>
        <el-table :data="datastores" stripe v-loading="loadingDS" style="width:100%" max-height="600">
          <template #empty>
            <el-empty description="暂无存储器数据，请先触发扫描" :image-size="60" />
          </template>
          <el-table-column prop="datastore_name" label="名称" min-width="220" fixed show-overflow-tooltip />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.status === 'accessible' ? 'success' : 'danger'" size="small">
                {{ row.status === 'accessible' ? '正常' : row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="ds_type" label="类型" width="90" />
          <el-table-column label="存储类别" width="110" align="center">
            <template #default="{ row }">
              <el-tag :type="storageTagType(row.storage_type)" size="small" effect="plain">
                {{ row.storage_type || '-' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="mounted_host_count" label="挂载主机数" width="105" align="center" />
          <el-table-column label="总容量(GB)" width="120" align="right">
            <template #default="{ row }">{{ row.capacity_gb?.toFixed(1) || '-' }}</template>
          </el-table-column>
          <el-table-column label="可用(GB)" width="120" align="right">
            <template #default="{ row }">{{ row.free_gb?.toFixed(1) || '-' }}</template>
          </el-table-column>
          <el-table-column label="使用率" min-width="200">
            <template #default="{ row }">
              <div style="display:flex;align-items:center;gap:8px;">
                <el-progress
                  :percentage="row.capacity_gb > 0 ? +((1 - row.free_gb / row.capacity_gb) * 100).toFixed(1) : 0"
                  :stroke-width="14"
                  :color="usageColor(row)"
                  style="flex:1;" />
                <span style="font-size:12px;color:#64748b;white-space:nowrap;">
                  {{ row.capacity_gb > 0 ? ((1 - row.free_gb / row.capacity_gb) * 100).toFixed(1) : 0 }}%
                </span>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/store/auth'
import { getVCenter, triggerVCenterScan, getVCenterVMs, exportVCenterVMs, getVCenterHosts, getVCenterDatastores } from '@/api/vcenters'
import api from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
const authStore = useAuthStore()
const vcenter = ref(null)
const vms = ref([])
const loading = ref(false)
const scanning = ref(false)
const page = ref(1)
const size = ref(20)
const total = ref(0)
const search = ref('')
const filterPower = ref('')
const filterOS = ref('')
const filterNetwork = ref('')
const filterFolder = ref('')
const filterOptions = ref({ power_states: [], os_names: [], networks: [], folders: [] })
const activeTab = ref('vms')
const hosts = ref([])
const datastores = ref([])
const hostTotal = ref(0)
const dsTotal = ref(0)
const loadingHosts = ref(false)
const loadingDS = ref(false)

function usageColor(row) {
  const pct = row.capacity_gb > 0 ? (1 - row.free_gb / row.capacity_gb) * 100 : 0
  if (pct > 80) return '#ef4444'
  if (pct > 60) return '#f59e0b'
  return '#10b981'
}

function storageTagType(type) {
  if (type === '共享NAS') return 'warning'
  if (type === '共享存储') return ''
  if (type === '本地存储') return 'success'
  return 'info'
}

async function fetchHosts() {
  loadingHosts.value = true
  try {
    const res = await getVCenterHosts(route.params.id)
    hosts.value = res.items || []
    hostTotal.value = res.total || 0
  } finally {
    loadingHosts.value = false
  }
}

async function fetchDatastores() {
  loadingDS.value = true
  try {
    const res = await getVCenterDatastores(route.params.id)
    datastores.value = res.items || []
    dsTotal.value = res.total || 0
  } finally {
    loadingDS.value = false
  }
}

function onTabChange(name) {
  if (name === 'hosts' && hosts.value.length === 0) fetchHosts()
  else if (name === 'datastores' && datastores.value.length === 0) fetchDatastores()
}

async function fetchVCenter() {
  vcenter.value = await getVCenter(route.params.id)
}

async function fetchVMs() {
  loading.value = true
  try {
    const res = await getVCenterVMs(route.params.id, {
      page: page.value, size: size.value, search: search.value,
      power_state: filterPower.value, os_name: filterOS.value,
      network_name: filterNetwork.value, vm_folder: filterFolder.value,
    })
    vms.value = res.items
    total.value = res.total
  } finally {
    loading.value = false
  }
}

async function handleScan() {
  try {
    await ElMessageBox.confirm('确认扫描此 vCenter？', '确认扫描')
    scanning.value = true
    await triggerVCenterScan(route.params.id)
    ElMessage.success('扫描已触发，请稍后刷新查看结果')
    setTimeout(() => { fetchVCenter(); fetchVMs() }, 3000)
  } catch { /* cancelled */ }
  finally { scanning.value = false }
}

const exporting = ref(false)
async function exportExcel() {
  exporting.value = true
  try {
    await exportVCenterVMs(route.params.id, {
      search: search.value, power_state: filterPower.value,
      os_name: filterOS.value, network_name: filterNetwork.value, vm_folder: filterFolder.value,
    })
  } finally {
    exporting.value = false
  }
}

async function fetchFilterOptions() {
  try {
    const { data } = await api.get(`/vcenters/${route.params.id}/vm-filter-options`)
    filterOptions.value = data
  } catch { /* handled */ }
}

onMounted(() => { fetchVCenter(); fetchVMs(); fetchFilterOptions() })
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 4px;
}
.header-left h2 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
}
.filter-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
}
.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
