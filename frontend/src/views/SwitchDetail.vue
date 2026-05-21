<template>
  <div class="switch-detail">
    <el-page-header @back="$router.push('/switches')" :title="sw?.name || '交换机详情'">
      <template #content>
        <span v-if="sw">{{ sw.name }} ({{ sw.ip_address }})</span>
      </template>
      <template #extra>
        <el-button v-if="authStore.isAdmin" type="primary" @click="handleScan" :loading="scanning">
          <el-icon><Refresh /></el-icon>立即扫描
        </el-button>
      </template>
    </el-page-header>

    <el-descriptions v-if="sw" :column="3" border class="info-card" size="small">
      <el-descriptions-item label="IP 地址">{{ sw.ip_address }}</el-descriptions-item>
      <el-descriptions-item label="MIB 类型">
        <el-tag :type="sw.mib_type === 'huawei' ? 'warning' : ''" size="small">
          {{ sw.mib_type === 'huawei' ? '华为' : '标准' }}
        </el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="状态">
        <el-tag :type="sw.is_active ? 'success' : 'info'" size="small">{{ sw.is_active ? '启用' : '禁用' }}</el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="扫描间隔">{{ sw.scan_interval > 0 ? sw.scan_interval + 's' : '手动' }}</el-descriptions-item>
      <el-descriptions-item label="SNMP 端口">{{ sw.snmp_port }}</el-descriptions-item>
      <el-descriptions-item label="最后更新">{{ formatTime(sw.updated_at) }}</el-descriptions-item>
    </el-descriptions>

    <el-card class="tabs-card">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="主机信息" name="hosts">
          <el-table :data="results" stripe v-loading="loadingResults" size="small" max-height="500">
            <el-table-column prop="ip_address" label="IP 地址" width="140" />
            <el-table-column prop="mac_address" label="MAC 地址" width="140" />
            <el-table-column prop="vlan_bd" label="VLAN/BD" width="80" />
            <el-table-column prop="vlan_type" label="VLAN类型" width="90" />
            <el-table-column prop="physical_port" label="物理端口" min-width="130" />
            <el-table-column prop="virtual_port" label="虚拟端口" min-width="130" />
            <el-table-column prop="switch_type" label="类型" width="60" />
          </el-table>
          <div class="pagination-wrap" v-if="resultsTotal > 0">
            <el-pagination v-model:current-page="rPage" :page-size="rSize" :total="resultsTotal"
              layout="total, prev, pager, next" @current-change="fetchResults" size="small" />
          </div>
        </el-tab-pane>

        <el-tab-pane label="路由表" name="routes">
          <el-table :data="routes" stripe v-loading="loadingRoutes" size="small" max-height="500">
            <el-table-column prop="cidr" label="CIDR" width="160" />
            <el-table-column prop="gateway" label="网关" width="140" />
            <el-table-column prop="interface_name" label="接口" min-width="140" />
            <el-table-column prop="route_type" label="类型" width="70" />
            <el-table-column prop="protocol" label="协议" width="70" />
            <el-table-column prop="target_network" label="目标网络" width="130" />
            <el-table-column prop="subnet_mask" label="掩码" width="130" />
          </el-table>
          <div class="pagination-wrap" v-if="routesTotal > 0">
            <el-pagination v-model:current-page="rtPage" :page-size="rtSize" :total="routesTotal"
              layout="total, prev, pager, next" @current-change="fetchRoutes" size="small" />
          </div>
        </el-tab-pane>

        <el-tab-pane label="扫描日志" name="logs">
          <el-table :data="logs" stripe v-loading="loadingLogs" size="small">
            <el-table-column prop="id" label="ID" width="60" />
            <el-table-column prop="status" label="状态" width="80">
              <template #default="{ row }">
                <el-tag :type="statusTag(row.status)" size="small">{{ statusText(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="triggered_by" label="触发" width="80">
              <template #default="{ row }">{{ row.triggered_by === 'manual' ? '手动' : '定时' }}</template>
            </el-table-column>
            <el-table-column prop="hosts_found" label="主机数" width="80" />
            <el-table-column prop="routes_found" label="路由数" width="80" />
            <el-table-column prop="started_at" label="开始时间" width="160">
              <template #default="{ row }">{{ formatTime(row.started_at) }}</template>
            </el-table-column>
            <el-table-column prop="completed_at" label="完成时间" width="160">
              <template #default="{ row }">{{ formatTime(row.completed_at) }}</template>
            </el-table-column>
            <el-table-column prop="error_message" label="错误" min-width="200" show-overflow-tooltip />
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/store/auth'
import { getSwitch, triggerScan } from '@/api/switches'
import { getResults, getRoutes, getScanLogs } from '@/api/results'
import { ElMessage } from 'element-plus'

const route = useRoute()
const authStore = useAuthStore()
const sw = ref(null)
const activeTab = ref('hosts')
const scanning = ref(false)

const results = ref([])
const routes = ref([])
const logs = ref([])
const loadingResults = ref(false)
const loadingRoutes = ref(false)
const loadingLogs = ref(false)
const rPage = ref(1); const rSize = ref(50); const resultsTotal = ref(0)
const rtPage = ref(1); const rtSize = ref(50); const routesTotal = ref(0)

const switchId = () => route.params.id

function formatTime(t) { if (!t) return ''; const d = new Date(t); if (isNaN(d.getTime())) return t; return d.toLocaleString('zh-CN', { hour12: false }) }
function statusTag(s) { return s === 'success' ? 'success' : s === 'failed' ? 'danger' : 'warning' }
function statusText(s) { return s === 'success' ? '成功' : s === 'failed' ? '失败' : '扫描中' }

async function fetchSwitch() {
  sw.value = await getSwitch(switchId())
}

async function fetchResults() {
  loadingResults.value = true
  try {
    const res = await getResults({ switch_id: switchId(), page: rPage.value, size: rSize.value })
    results.value = res.items
    resultsTotal.value = res.total
  } finally { loadingResults.value = false }
}

async function fetchRoutes() {
  loadingRoutes.value = true
  try {
    const res = await getRoutes({ switch_id: switchId(), page: rtPage.value, size: rtSize.value })
    routes.value = res.items
    routesTotal.value = res.total
  } finally { loadingRoutes.value = false }
}

async function fetchLogs() {
  loadingLogs.value = true
  try {
    const res = await getScanLogs({ switch_id: switchId(), size: 50 })
    logs.value = res.items
  } finally { loadingLogs.value = false }
}

let pollTimer = null

async function handleScan() {
  scanning.value = true
  try {
    const log = await triggerScan(switchId())
    ElMessage.success('扫描已触发')
    activeTab.value = 'logs'
    await fetchLogs()
    startPolling()
  } finally { scanning.value = false }
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    await fetchLogs()
    const running = logs.value.some(l => l.status === 'running')
    if (!running) {
      stopPolling()
      await fetchResults()
      await fetchRoutes()
      const latest = logs.value[0]
      if (latest && latest.status === 'success') {
        ElMessage.success(`扫描完成，发现 ${latest.hosts_found} 台主机、${latest.routes_found} 条路由`)
      } else if (latest && latest.status === 'failed') {
        ElMessage.error(`扫描失败: ${latest.error_message || '未知错误'}`)
      }
    }
  }, 1500)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

watch(activeTab, (tab) => {
  if (tab === 'hosts') fetchResults()
  if (tab === 'routes') fetchRoutes()
  if (tab === 'logs') fetchLogs()
})

onMounted(async () => {
  await fetchSwitch()
  fetchResults()
})
</script>

<style scoped>
.info-card {
  margin: 20px 0;
  border-radius: var(--radius-md);
}

.tabs-card {
  margin-top: 20px;
}

.tabs-card :deep(.el-tabs__header) {
  margin-bottom: 16px;
}

.tabs-card :deep(.el-tabs__item) {
  font-weight: 500;
  font-size: 14px;
}

.pagination-wrap {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}
</style>
