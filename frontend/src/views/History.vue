<template>
  <div class="history-page">
    <h2>历史记录</h2>

    <el-tabs v-model="activeTab" @tab-change="onTabChange">
      <!-- ═══════════ 交换机历史 Tab ═══════════ -->
      <el-tab-pane label="交换机历史" name="switch">
        <el-form :inline="true" class="filter-bar">
          <el-form-item label="IP 地址">
            <el-input v-model="filters.ip" placeholder="输入 IP" clearable style="width:150px" />
          </el-form-item>
          <el-form-item label="MAC 地址">
            <el-input v-model="filters.mac" placeholder="输入 MAC" clearable style="width:150px" />
          </el-form-item>
          <el-form-item label="变更类型">
            <el-select v-model="filters.change_type" placeholder="全部" clearable style="width:110px">
              <el-option label="新增" value="added" />
              <el-option label="删除" value="deleted" />
              <el-option label="变更" value="modified" />
            </el-select>
          </el-form-item>
          <el-form-item label="交换机">
            <el-select v-model="filters.switch_id" placeholder="全部" clearable style="width:180px">
              <el-option v-for="s in switchOptions" :key="s.id" :label="s.name" :value="s.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="时间范围">
            <el-date-picker
              v-model="dateRange"
              type="daterange"
              range-separator="至"
              start-placeholder="开始"
              end-placeholder="结束"
              value-format="YYYY-MM-DD"
              style="width:240px"
            />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="fetchData">查询</el-button>
            <el-button @click="resetFilters">重置</el-button>
          </el-form-item>
        </el-form>

        <el-table :data="items" v-loading="loading" stripe :row-class-name="rowClassName" style="width:100%">
          <template #empty><el-empty description="暂无历史记录" :image-size="80" /></template>
          <el-table-column label="时间" width="170">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column prop="source_name" label="交换机" width="160" show-overflow-tooltip />
          <el-table-column label="变更类型" width="90">
            <template #default="{ row }">
              <el-tag :type="changeTag(row.change_type)" size="small">{{ changeLabel(row.change_type) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="ip_address" label="IP 地址" width="140" />
          <el-table-column prop="mac_address" label="MAC 地址" width="150" />
          <el-table-column label="VLAN/BD" width="130">
            <template #default="{ row }">{{ changeDiff(row, 'vlan_bd') }}</template>
          </el-table-column>
          <el-table-column label="物理端口" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">{{ changeDiff(row, 'physical_port') }}</template>
          </el-table-column>
          <el-table-column label="虚拟端口" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">{{ changeDiff(row, 'virtual_port') }}</template>
          </el-table-column>
          <el-table-column label="类型" width="80">
            <template #default="{ row }">{{ changeDiff(row, 'switch_type') }}</template>
          </el-table-column>
          <el-table-column label="变更详情" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">{{ detailText(row) }}</template>
          </el-table-column>
        </el-table>

        <div class="pagination-wrap" v-if="isPaginated && total > 0">
          <el-pagination v-model:current-page="page" :page-size="size" :total="total"
            layout="total, prev, pager, next" @current-change="fetchData" />
        </div>
      </el-tab-pane>

      <!-- ═══════════ vCenter 历史 Tab ═══════════ -->
      <el-tab-pane label="vCenter 历史" name="vcenter">
        <el-form :inline="true" class="filter-bar">
          <el-form-item label="VM 名称">
            <el-input v-model="filters.vm_name" placeholder="输入 VM 名称" clearable style="width:180px" />
          </el-form-item>
          <el-form-item label="IP 地址">
            <el-input v-model="filters.ip" placeholder="输入 IP" clearable style="width:150px" />
          </el-form-item>
          <el-form-item label="变更类型">
            <el-select v-model="filters.change_type" placeholder="全部" clearable style="width:110px">
              <el-option label="新增" value="added" />
              <el-option label="删除" value="deleted" />
              <el-option label="变更" value="modified" />
            </el-select>
          </el-form-item>
          <el-form-item label="vCenter">
            <el-select v-model="filters.source_id" placeholder="全部" clearable style="width:180px">
              <el-option v-for="v in vcenterOptions" :key="v.id" :label="v.name" :value="v.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="时间范围">
            <el-date-picker v-model="dateRange" type="daterange" range-separator="至"
              start-placeholder="开始" end-placeholder="结束" value-format="YYYY-MM-DD" style="width:240px" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="fetchData">查询</el-button>
            <el-button @click="resetFilters">重置</el-button>
          </el-form-item>
        </el-form>

        <el-table :data="items" v-loading="loading" stripe :row-class-name="rowClassName" style="width:100%">
          <template #empty><el-empty description="暂无 vCenter 历史记录" :image-size="80" /></template>
          <el-table-column label="时间" width="170">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column prop="source_name" label="vCenter" width="160" show-overflow-tooltip />
          <el-table-column label="变更类型" width="90">
            <template #default="{ row }">
              <el-tag :type="changeTag(row.change_type)" size="small">{{ changeLabel(row.change_type) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="VM 名称" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">{{ row.dedup_key ? row.dedup_key.split('::')[0] : '-' }}</template>
          </el-table-column>
          <el-table-column prop="ip_address" label="IP 地址" min-width="160" show-overflow-tooltip />
          <el-table-column prop="mac_address" label="MAC 地址" min-width="160" show-overflow-tooltip />
          <el-table-column label="变更详情" min-width="300" show-overflow-tooltip>
            <template #default="{ row }">{{ detailText(row) }}</template>
          </el-table-column>
        </el-table>

        <div class="pagination-wrap" v-if="isPaginated && total > 0">
          <el-pagination v-model:current-page="page" :page-size="size" :total="total"
            layout="total, prev, pager, next" @current-change="fetchData" />
        </div>
      </el-tab-pane>

      <!-- ═══════════ F5 历史 Tab ═══════════ -->
      <el-tab-pane label="F5 历史" name="f5">
        <el-form :inline="true" class="filter-bar">
          <el-form-item label="IP 地址">
            <el-input v-model="filters.ip" placeholder="输入 VS IP" clearable style="width:150px" />
          </el-form-item>
          <el-form-item label="变更类型">
            <el-select v-model="filters.change_type" placeholder="全部" clearable style="width:110px">
              <el-option label="新增" value="added" />
              <el-option label="删除" value="deleted" />
              <el-option label="变更" value="modified" />
            </el-select>
          </el-form-item>
          <el-form-item label="F5 设备">
            <el-select v-model="filters.source_id" placeholder="全部" clearable style="width:180px">
              <el-option v-for="d in f5Options" :key="d.id" :label="d.name" :value="d.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="时间范围">
            <el-date-picker v-model="dateRange" type="daterange" range-separator="至"
              start-placeholder="开始" end-placeholder="结束" value-format="YYYY-MM-DD" style="width:240px" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="fetchData">查询</el-button>
            <el-button @click="resetFilters">重置</el-button>
          </el-form-item>
        </el-form>

        <el-table :data="items" v-loading="loading" stripe :row-class-name="rowClassName" style="width:100%">
          <template #empty><el-empty description="暂无 F5 历史记录" :image-size="80" /></template>
          <el-table-column label="时间" width="170">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column prop="source_name" label="F5 设备" width="160" show-overflow-tooltip />
          <el-table-column label="变更类型" width="90">
            <template #default="{ row }">
              <el-tag :type="changeTag(row.change_type)" size="small">{{ changeLabel(row.change_type) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="ip_address" label="VS IP" width="140" />
          <el-table-column label="VS 名称" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">{{ parseDedup(row, 0) }}</template>
          </el-table-column>
          <el-table-column label="域名" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">{{ parseDedup(row, 1) }}</template>
          </el-table-column>
          <el-table-column label="变更详情" min-width="300" show-overflow-tooltip>
            <template #default="{ row }">{{ detailText(row) }}</template>
          </el-table-column>
        </el-table>

        <div class="pagination-wrap" v-if="isPaginated && total > 0">
          <el-pagination v-model:current-page="page" :page-size="size" :total="total"
            layout="total, prev, pager, next" @current-change="fetchData" />
        </div>
      </el-tab-pane>

      <!-- ═══════════ ZDNS 历史 Tab ═══════════ -->
      <el-tab-pane label="ZDNS 历史" name="zdns">
        <el-form :inline="true" class="filter-bar">
          <el-form-item label="IP 地址">
            <el-input v-model="filters.ip" placeholder="输入 IP" clearable style="width:150px" />
          </el-form-item>
          <el-form-item label="变更类型">
            <el-select v-model="filters.change_type" placeholder="全部" clearable style="width:110px">
              <el-option label="新增" value="added" />
              <el-option label="删除" value="deleted" />
              <el-option label="变更" value="modified" />
            </el-select>
          </el-form-item>
          <el-form-item label="ZDNS 设备">
            <el-select v-model="filters.source_id" placeholder="全部" clearable style="width:180px">
              <el-option v-for="d in zdnsOptions" :key="d.id" :label="d.name" :value="d.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="时间范围">
            <el-date-picker v-model="dateRange" type="daterange" range-separator="至"
              start-placeholder="开始" end-placeholder="结束" value-format="YYYY-MM-DD" style="width:240px" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="fetchData">查询</el-button>
            <el-button @click="resetFilters">重置</el-button>
          </el-form-item>
        </el-form>

        <el-table :data="items" v-loading="loading" stripe :row-class-name="rowClassName" style="width:100%">
          <template #empty><el-empty description="暂无 ZDNS 历史记录" :image-size="80" /></template>
          <el-table-column label="时间" width="170">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column prop="source_name" label="ZDNS 设备" width="160" show-overflow-tooltip />
          <el-table-column label="变更类型" width="90">
            <template #default="{ row }">
              <el-tag :type="changeTag(row.change_type)" size="small">{{ changeLabel(row.change_type) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="ip_address" label="IP 地址" width="140" />
          <el-table-column label="域名" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">{{ parseDedup(row, 0) }}</template>
          </el-table-column>
          <el-table-column label="记录类型" width="90">
            <template #default="{ row }">{{ parseDedup(row, 1) }}</template>
          </el-table-column>
          <el-table-column label="变更详情" min-width="300" show-overflow-tooltip>
            <template #default="{ row }">{{ detailText(row) }}</template>
          </el-table-column>
        </el-table>

        <div class="pagination-wrap" v-if="isPaginated && total > 0">
          <el-pagination v-model:current-page="page" :page-size="size" :total="total"
            layout="total, prev, pager, next" @current-change="fetchData" />
        </div>
      </el-tab-pane>

      <!-- 椒图历史 -->
      <el-tab-pane label="椒图历史" name="qax">
        <div class="filter-bar">
          <el-row :gutter="12">
            <el-col :span="5">
              <el-input v-model="filters.ip" placeholder="IP 地址" clearable @change="resetAndFetch" />
            </el-col>
            <el-col :span="5">
              <el-select v-model="filters.source_id" placeholder="全部设备" clearable style="width:100%">
                <el-option v-for="d in qaxOptions" :key="d.id" :label="d.name" :value="d.id" />
              </el-select>
            </el-col>
            <el-col :span="4">
              <el-select v-model="filters.change_type" placeholder="全部类型" clearable style="width:100%">
                <el-option label="新增" value="added" />
                <el-option label="删除" value="deleted" />
                <el-option label="修改" value="modified" />
              </el-select>
            </el-col>
            <el-col :span="8">
              <el-date-picker v-model="dateRange" type="datetimerange" range-separator="至"
                start-placeholder="开始" end-placeholder="结束" format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DDTHH:mm" style="width:100%" @change="fetchData" />
            </el-col>
            <el-col :span="2">
              <el-button @click="resetFilters" :icon="'Refresh'" size="small">重置</el-button>
            </el-col>
          </el-row>
        </div>

        <el-table :data="items" v-loading="loading" stripe :row-class-name="rowClassName" style="width:100%">
          <el-table-column label="时间" width="170">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column prop="source_name" label="椒图设备" width="160" show-overflow-tooltip />
          <el-table-column label="变更类型" width="90">
            <template #default="{ row }">
              <el-tag :type="{ added:'success', deleted:'danger', modified:'warning' }[row.change_type]" size="small">
                {{ { added:'新增', deleted:'删除', modified:'修改' }[row.change_type] }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="主机名" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">{{ parseDedup(row, 0) }}</template>
          </el-table-column>
          <el-table-column prop="ip_address" label="IP 地址" width="140" />
          <el-table-column label="变更详情" min-width="300" show-overflow-tooltip>
            <template #default="{ row }">{{ detailText(row) }}</template>
          </el-table-column>
        </el-table>

        <div class="pagination-wrap" v-if="isPaginated && total > 0">
          <el-pagination v-model:current-page="page" :page-size="size" :total="total"
            layout="total, prev, pager, next" @current-change="fetchData" />
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { getHistory, getHistoryByIp, getHistoryByMac } from '@/api/history'
import api from '@/api'

const activeTab = ref('switch')
const items = ref([])
const loading = ref(false)
const page = ref(1)
const size = ref(50)
const total = ref(0)
const switchOptions = ref([])
const vcenterOptions = ref([])
const f5Options = ref([])
const zdnsOptions = ref([])
const qaxOptions = ref([])
const dateRange = ref(null)
const filters = reactive({ ip: '', mac: '', change_type: '', switch_id: null, source_id: null, vm_name: '' })

const isPaginated = computed(() => !filters.ip && !filters.mac && !filters.vm_name)

function formatTime(t) {
  if (!t) return ''
  const d = new Date(t)
  if (isNaN(d.getTime())) return t
  return d.toLocaleString('zh-CN', { hour12: false })
}

function changeTag(type) {
  return type === 'added' ? 'success' : type === 'deleted' ? 'danger' : 'warning'
}

function changeLabel(type) {
  return type === 'added' ? '新增' : type === 'deleted' ? '删除' : '变更'
}

function rowClassName({ row }) {
  return 'row-' + row.change_type
}

function changeDiff(row, field) {
  const ov = row['old_' + field]
  const nv = row['new_' + field]
  const fmt = (v) => v === null || v === undefined || v === '' ? '-' : v
  if (row.change_type === 'added') return fmt(nv)
  if (row.change_type === 'deleted') return fmt(ov)
  const ofv = fmt(ov)
  const nfv = fmt(nv)
  if (ofv === nfv) return ofv
  return ofv + ' → ' + nfv
}

function parseDedup(row, index) {
  if (!row.dedup_key) return '-'
  const parts = row.dedup_key.split('::')
  return parts[index] || '-'
}

function detailText(row) {
  if (row.change_detail && typeof row.change_detail === 'object') {
    const parts = []
    for (const [field, vals] of Object.entries(row.change_detail)) {
      const label = fieldLabels[field] || field
      const ov = vals.old !== null && vals.old !== undefined && vals.old !== '' ? vals.old : '-'
      const nv = vals.new !== null && vals.new !== undefined && vals.new !== '' ? vals.new : '-'
      parts.push(`${label}: ${ov} → ${nv}`)
    }
    return parts.join(' | ')
  }
  if (activeTab.value === 'switch') {
    const parts = []
    if (row.old_vlan_bd !== row.new_vlan_bd) parts.push(`VLAN: ${row.old_vlan_bd || '-'} → ${row.new_vlan_bd || '-'}`)
    if (row.old_physical_port !== row.new_physical_port) parts.push(`端口: ${row.old_physical_port || '-'} → ${row.new_physical_port || '-'}`)
    if (row.old_virtual_port !== row.new_virtual_port) parts.push(`虚拟端口: ${row.old_virtual_port || '-'} → ${row.new_virtual_port || '-'}`)
    return parts.join(' | ') || '-'
  }
  return '-'
}

const fieldLabels = {
  vlan_bd: 'VLAN/BD', vlan_type: 'VLAN类型', physical_port: '物理端口',
  virtual_port: '虚拟端口', switch_type: '交换机类型', ip_address: 'IP',
  network_name: '网络', resource_pool: '资源池', vm_folder: '文件夹',
  power_state: '电源', esxi_host: 'ESXi', cluster: '集群',
  cpu_count: 'CPU', memory_gb: '内存',
  vs_ip: 'VS IP', vs_port: 'VS 端口', pool_name: 'Pool',
  rule_name: 'iRule', member_ip: '成员 IP', member_port: '成员端口',
  member_state: '成员状态', domain_name: '域名',
  ip_category: 'IP类别', network_type: '网络类型', ttl: 'TTL',
  view_name: '视图', zone_name: '区', is_enabled: '启用',
  ipv4: 'IP', intranet_ip: '内网IP', operation_system: '操作系统',
  cpu: 'CPU', memory: '内存', disk_size_str: '磁盘',
  online_status: '在线状态', run_status: '运行状态', machine_group: '分组',
}

function resetFilters() {
  filters.ip = ''; filters.mac = ''; filters.vm_name = ''
  filters.change_type = ''; filters.switch_id = null; filters.source_id = null
  dateRange.value = null
  page.value = 1
  fetchData()
}

function onTabChange() {
  resetFilters()
}

async function fetchData() {
  loading.value = true
  try {
    if (filters.ip && !filters.vm_name) {
      const data = await getHistoryByIp(filters.ip, { source_type: activeTab.value })
      items.value = data; total.value = 0
    } else if (filters.mac && !filters.vm_name) {
      const data = await getHistoryByMac(filters.mac, { source_type: activeTab.value })
      items.value = data; total.value = 0
    } else {
      const params = { page: page.value, size: size.value, source_type: activeTab.value }
      if (filters.change_type) params.change_type = filters.change_type
      if (filters.vm_name) params.vm_name = filters.vm_name
      if (filters.switch_id && activeTab.value === 'switch') params.switch_id = filters.switch_id
      if (filters.source_id && ['vcenter', 'f5', 'zdns', 'qax'].includes(activeTab.value))
        params.source_id = filters.source_id
      if (dateRange.value) {
        params.start_date = dateRange.value[0]
        params.end_date = dateRange.value[1] + ' 23:59:59'
      }
      const data = await getHistory(params)
      items.value = data.items; total.value = data.total
    }
  } catch { /* handled by interceptor */ }
  finally { loading.value = false }
}

async function fetchDevices() {
  try {
    const { data } = await api.get('/switches', { params: { size: 100 } })
    switchOptions.value = data.items || []
  } catch { /* handled */ }
  try {
    const { data } = await api.get('/vcenters', { params: { size: 100 } })
    vcenterOptions.value = data.items || []
  } catch { /* handled */ }
  try {
    const { data } = await api.get('/f5', { params: { size: 100 } })
    f5Options.value = data.items || []
  } catch { /* handled */ }
  try {
    const { data } = await api.get('/zdns', { params: { size: 100 } })
    zdnsOptions.value = data.items || []
  } catch { /* handled */ }
  try {
    const { data } = await api.get('/qax', { params: { size: 100 } })
    qaxOptions.value = data.items || []
  } catch { /* handled */ }
}

onMounted(() => {
  fetchDevices()
  fetchData()
})
</script>

<style scoped>
.history-page h2 {
  margin: 0 0 20px;
  font-size: 22px;
  font-weight: 700;
}
.filter-bar {
  margin-bottom: 16px;
  background: var(--color-bg-card);
  padding: 16px 16px 0;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
}
.pagination-wrap {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
:deep(.row-added) { background-color: var(--color-success-bg) !important; }
:deep(.row-deleted) { background-color: var(--color-danger-bg) !important; }
:deep(.row-modified) { background-color: var(--color-warning-bg) !important; }
:deep(.row-added:hover td) { background-color: #d1fae5 !important; }
:deep(.row-deleted:hover td) { background-color: #fee2e2 !important; }
:deep(.row-modified:hover td) { background-color: #fef3c7 !important; }
</style>
