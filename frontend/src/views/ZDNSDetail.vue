<template>
  <div class="zdns-detail">
    <div class="page-header">
      <div class="header-left">
        <el-button text @click="$router.back()">
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
        <h2>{{ device?.name || 'ZDNS 详情' }}</h2>
      </div>
      <div class="header-right" v-if="authStore.isAdmin">
        <el-button type="primary" @click="handleScan" :loading="scanning">
          <el-icon><Refresh /></el-icon>立即扫描
        </el-button>
        <el-button type="warning" @click="handleIPScan" :loading="ipScanning">
          <el-icon><Connection /></el-icon>IP扫描
        </el-button>
      </div>
    </div>

    <el-descriptions v-if="device" :column="3" border size="small" class="info-card">
      <el-descriptions-item label="主机地址">{{ device.host }}</el-descriptions-item>
      <el-descriptions-item label="用户名">{{ device.username }}</el-descriptions-item>
      <el-descriptions-item label="端口">{{ device.port }}</el-descriptions-item>
      <el-descriptions-item label="扫描间隔">{{ device.scan_interval > 0 ? device.scan_interval + 's' : '手动' }}</el-descriptions-item>
      <el-descriptions-item label="状态">
        <el-tag :type="device.is_active ? 'success' : 'info'" size="small">
          {{ device.is_active ? '启用' : '禁用' }}
        </el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="扫描状态">
        <div style="display:flex;align-items:center;gap:6px;">
          <el-tag v-if="device.last_scan_status === 'success'" type="success" size="small">成功</el-tag>
          <el-tag v-else-if="device.last_scan_status === 'failed'" type="danger" size="small">失败</el-tag>
          <el-tag v-else-if="device.last_scan_status === 'running'" type="warning" size="small">扫描中</el-tag>
          <span v-else style="color:#c0c4cc;">未扫描</span>
          <span v-if="device.last_scan_duration" style="color:#909399;font-size:12px;">耗时 {{ device.last_scan_duration }}s</span>
        </div>
      </el-descriptions-item>
      <el-descriptions-item label="IP扫描状态">
        <div style="display:flex;align-items:center;gap:6px;">
          <el-tag v-if="device.last_ip_scan_status === 'success'" type="success" size="small">成功</el-tag>
          <el-tag v-else-if="device.last_ip_scan_status === 'failed'" type="danger" size="small">失败</el-tag>
          <el-tag v-else-if="device.last_ip_scan_status === 'running'" type="warning" size="small">扫描中</el-tag>
          <span v-else style="color:#c0c4cc;">未扫描</span>
          <span v-if="device.last_ip_scan_duration" style="color:#909399;font-size:12px;">耗时 {{ device.last_ip_scan_duration }}s</span>
        </div>
      </el-descriptions-item>
    </el-descriptions>

    <div v-if="device?.last_scan_error" style="margin-top:12px;">
      <el-alert :title="'扫描错误: ' + device.last_scan_error" type="error" show-icon :closable="false" />
    </div>

    <el-card style="margin-top:20px;">
      <el-tabs v-model="activeTab" @tab-click="onTabClick">
        <!-- ═══════════ 域名清单（核心 Tab） ═══════════ -->
        <el-tab-pane label="域名清单" name="domainmap">
          <div class="filter-bar">
            <el-input v-model="searchMap" placeholder="搜索域名、IP、视图、区..." clearable style="width:280px"
              @keyup.enter="fetchDomainMap" @clear="fetchDomainMap" />
            <el-select v-model="filterRecordType" clearable placeholder="记录类型" style="width:100px" @change="fetchDomainMap">
              <el-option label="全部" value="" />
              <el-option label="A" value="A" />
              <el-option label="AAAA" value="AAAA" />
              <el-option label="CNAME" value="CNAME" />
            </el-select>
            <el-select v-model="filterIsEnabled" clearable placeholder="启用" style="width:90px" @change="fetchDomainMap">
              <el-option label="全部" value="" />
              <el-option label="是" value="yes" />
              <el-option label="否" value="no" />
            </el-select>
            <el-select v-model="filterIPStatus" clearable placeholder="IP状态" style="width:100px" @change="fetchDomainMap">
              <el-option label="全部" value="" />
              <el-option label="在线" value="在线" />
              <el-option label="离线" value="离线" />
              <el-option label="禁用" value="禁用" />
              <el-option label="待定" value="待定" />
            </el-select>
            <el-button type="primary" @click="fetchDomainMap">查询</el-button>
            <el-button @click="exportMap" :loading="exportingMap">
              <el-icon><Download /></el-icon>导出
            </el-button>
          </div>
          <el-table :data="domainMap" stripe v-loading="loadingMap" max-height="520" style="width:100%">
            <template #empty>
              <el-empty description="暂无映射数据，请先触发扫描" :image-size="60" />
            </template>
            <el-table-column prop="domain_name" label="域名" min-width="220" show-overflow-tooltip />
            <el-table-column prop="ip_address" label="IP/指向" width="180" show-overflow-tooltip />
            <el-table-column label="记录类型" width="80">
              <template #default="{ row }">
                <el-tag v-if="row.record_type === 'A'" type="primary" size="small">A</el-tag>
                <el-tag v-else-if="row.record_type === 'AAAA'" type="success" size="small">AAAA</el-tag>
                <el-tag v-else-if="row.record_type === 'CNAME'" type="warning" size="small">CNAME</el-tag>
                <span v-else>{{ row.record_type }}</span>
              </template>
            </el-table-column>
            <el-table-column label="IP 类别" width="80">
              <template #default="{ row }">
                <el-tag :type="row.ip_category === 'IPv4' ? '' : 'warning'" size="small">{{ row.ip_category }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="网络类型" width="90">
              <template #default="{ row }">
                <el-tag v-if="row.network_type === '内网'" type="info" size="small">内网</el-tag>
                <el-tag v-else-if="row.network_type === '外网'" type="danger" size="small">外网</el-tag>
                <span v-else style="color:#c0c4cc;">-</span>
              </template>
            </el-table-column>
            <el-table-column prop="ttl" label="TTL" width="70" />
            <el-table-column prop="view_name" label="视图" width="100" />
            <el-table-column prop="zone_name" label="区" min-width="160" show-overflow-tooltip />
            <el-table-column label="启用" width="70">
              <template #default="{ row }">
                <el-tag :type="row.is_enabled === 'yes' ? 'success' : 'info'" size="small">
                  {{ row.is_enabled === 'yes' ? '是' : '否' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="IP 状态" width="90">
              <template #default="{ row }">
                <span v-if="row.ip_status" class="status-badge" :class="ipStatusClass(row.ip_status)">{{ row.ip_status }}</span>
                <span v-else style="color:#c0c4cc;">待定</span>
              </template>
            </el-table-column>
          </el-table>
          <div class="pagination-wrap" v-if="totalMap > 0">
            <el-pagination
              v-model:current-page="pageMap" :page-size="sizeMap" :total="totalMap"
              layout="total, prev, pager, next" @current-change="fetchDomainMap" small />
          </div>
        </el-tab-pane>

        <!-- ═══════════ DNS 记录 Tab ═══════════ -->
        <el-tab-pane label="DNS 记录" name="records">
          <div class="filter-bar">
            <el-input v-model="searchRec" placeholder="搜索记录名称、域名、类型、值..." clearable style="width:380px"
              @keyup.enter="fetchRecords" @clear="fetchRecords" />
            <el-button type="primary" @click="fetchRecords">查询</el-button>
            <el-button @click="exportRec" :loading="exportingRec">
              <el-icon><Download /></el-icon>导出
            </el-button>
          </div>
          <el-table :data="records" stripe v-loading="loadingRec" max-height="520" style="width:100%">
            <template #empty>
              <el-empty description="暂无 DNS 记录数据" :image-size="60" />
            </template>
            <el-table-column prop="name" label="记录名称" min-width="120" show-overflow-tooltip />
            <el-table-column prop="full_domain" label="完整域名" min-width="200" show-overflow-tooltip />
            <el-table-column prop="record_type" label="类型" width="80">
              <template #default="{ row }">
                <el-tag size="small">{{ row.record_type }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="ttl" label="TTL" width="70" />
            <el-table-column prop="rdata" label="记录值" min-width="200" show-overflow-tooltip />
            <el-table-column prop="view_name" label="视图" width="100" />
            <el-table-column prop="zone_name" label="区" min-width="160" show-overflow-tooltip />
            <el-table-column label="启用" width="70">
              <template #default="{ row }">
                <el-tag :type="row.is_enabled === 'yes' ? 'success' : 'info'" size="small">
                  {{ row.is_enabled === 'yes' ? '是' : '否' }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
          <div class="pagination-wrap" v-if="totalRec > 0">
            <el-pagination
              v-model:current-page="pageRec" :page-size="sizeRec" :total="totalRec"
              layout="total, prev, pager, next" @current-change="fetchRecords" small />
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/store/auth'
import { getZDNSDevice, triggerZDNSScan, triggerZDNSIPScan, getZDNSDomainMap, getZDNSRecords, exportZDNSDomainMap, exportZDNSRecords } from '@/api/zdns'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
const authStore = useAuthStore()
const device = ref(null)
const activeTab = ref('domainmap')
const scanning = ref(false)
const ipScanning = ref(false)

// 域名清单
const domainMap = ref([])
const loadingMap = ref(false)
const pageMap = ref(1); const sizeMap = ref(50); const totalMap = ref(0)
const searchMap = ref('')
const filterRecordType = ref('')
const filterIsEnabled = ref('')
const filterIPStatus = ref('')

// DNS 记录
const records = ref([])
const loadingRec = ref(false)
const pageRec = ref(1); const sizeRec = ref(20); const totalRec = ref(0)
const searchRec = ref('')

async function fetchDevice() {
  device.value = await getZDNSDevice(route.params.id)
}

async function fetchDomainMap() {
  loadingMap.value = true
  try {
    const params = {
      page: pageMap.value, size: sizeMap.value, search: searchMap.value,
      record_type: filterRecordType.value,
      is_enabled: filterIsEnabled.value,
      ip_status: filterIPStatus.value,
    }
    const res = await getZDNSDomainMap(route.params.id, params)
    domainMap.value = res.items
    totalMap.value = res.total
  } finally { loadingMap.value = false }
}

async function fetchRecords() {
  loadingRec.value = true
  try {
    const res = await getZDNSRecords(route.params.id, { page: pageRec.value, size: sizeRec.value, search: searchRec.value })
    records.value = res.items
    totalRec.value = res.total
  } finally { loadingRec.value = false }
}

function ipStatusClass(status) {
  if (status === '在线') return 'dot-up'
  if (status === '离线') return 'dot-down'
  if (status === '禁用') return 'dot-user'
  return 'dot-unknown'
}

function onTabClick(tab) {
  const name = tab.props?.name || tab.paneName?.value
  if (name === 'domainmap') { if (domainMap.value.length === 0) fetchDomainMap() }
  else if (name === 'records') fetchRecords()
}

async function handleScan() {
  try {
    await ElMessageBox.confirm('确认扫描此 ZDNS 设备？', '确认扫描')
    scanning.value = true
    await triggerZDNSScan(route.params.id)
    ElMessage.success('扫描已触发，请稍后刷新查看结果')
    setTimeout(() => { fetchDevice(); fetchDomainMap() }, 3000)
  } catch { /* cancelled */ }
  finally { scanning.value = false }
}

async function handleIPScan() {
  try {
    await ElMessageBox.confirm('确认对此 ZDNS 设备执行 IP 可达性扫描？', '确认 IP 扫描')
    ipScanning.value = true
    await triggerZDNSIPScan(route.params.id)
    ElMessage.success('IP 扫描已触发，请稍后刷新查看结果')
    setTimeout(() => fetchDevice(), 3000)
  } catch { /* cancelled */ }
  finally { ipScanning.value = false }
}

// 导出
const exportingMap = ref(false)
const exportingRec = ref(false)
async function exportMap() {
  exportingMap.value = true
  try {
    await exportZDNSDomainMap(route.params.id, {
      search: searchMap.value, record_type: filterRecordType.value,
      is_enabled: filterIsEnabled.value, ip_status: filterIPStatus.value,
    })
  } finally { exportingMap.value = false }
}
async function exportRec() {
  exportingRec.value = true
  try { await exportZDNSRecords(route.params.id, { search: searchRec.value }) } finally { exportingRec.value = false }
}

onMounted(() => { fetchDevice(); fetchDomainMap() })
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
.header-right {
  display: flex;
  gap: 8px;
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

/* ── 状态指示器 ── */
.status-badge {
  display: inline-flex;
  align-items: center;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
}
.dot-up {
  color: #22c55e;
  background: rgba(34, 197, 94, 0.08);
}
.dot-down {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.08);
}
.dot-user {
  color: #909399;
  background: rgba(144, 147, 153, 0.08);
}
.dot-unknown {
  color: #c0c4cc;
}
</style>
