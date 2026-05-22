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
      <el-descriptions-item label="扫描状态">
        <div style="display:flex;align-items:center;gap:6px;">
          <el-tag v-if="sw.last_scan_status === 'success'" type="success" size="small">成功</el-tag>
          <el-tag v-else-if="sw.last_scan_status === 'failed'" type="danger" size="small">失败</el-tag>
          <span v-else style="color:#c0c4cc;">未扫描</span>
          <span v-if="sw.last_scan_duration" style="color:#909399;font-size:12px;">耗时 {{ sw.last_scan_duration }}s</span>
        </div>
      </el-descriptions-item>
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
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/store/auth'
import { getSwitch, triggerScan } from '@/api/switches'
import { getResults, getRoutes } from '@/api/results'
import { ElMessage } from 'element-plus'

const route = useRoute()
const authStore = useAuthStore()
const sw = ref(null)
const activeTab = ref('hosts')
const scanning = ref(false)

const results = ref([])
const routes = ref([])
const loadingResults = ref(false)
const loadingRoutes = ref(false)
const rPage = ref(1); const rSize = ref(50); const resultsTotal = ref(0)
const rtPage = ref(1); const rtSize = ref(50); const routesTotal = ref(0)

const switchId = () => route.params.id

function formatTime(t) { if (!t) return ''; const d = new Date(t); if (isNaN(d.getTime())) return t; return d.toLocaleString('zh-CN', { hour12: false }) }

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

async function handleScan() {
  scanning.value = true
  try {
    await triggerScan(switchId())
    ElMessage.success('扫描已触发，请到"扫描日志"页面查看进度')
  } finally { scanning.value = false }
}

watch(activeTab, (tab) => {
  if (tab === 'hosts') fetchResults()
  if (tab === 'routes') fetchRoutes()
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
