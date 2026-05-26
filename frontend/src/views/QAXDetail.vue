<template>
  <div class="qax-detail">
    <div class="page-header">
      <div class="header-left">
        <el-button text @click="$router.back()">
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
        <h2>{{ device?.name || '椒图详情' }}</h2>
      </div>
      <el-button v-if="authStore.isAdmin" type="primary" @click="handleScan" :loading="scanning">
        <el-icon><Refresh /></el-icon>立即扫描
      </el-button>
    </div>

    <el-descriptions v-if="device" :column="3" border size="small" class="info-card">
      <el-descriptions-item label="API 地址">{{ device.host }}</el-descriptions-item>
      <el-descriptions-item label="账号 UUID">{{ device.uuid }}</el-descriptions-item>
      <el-descriptions-item label="扫描间隔">{{ device.scan_interval > 0 ? device.scan_interval + 's' : '手动' }}</el-descriptions-item>
      <el-descriptions-item label="状态">
        <el-tag :type="device.enabled ? 'success' : 'info'" size="small">
          {{ device.enabled ? '启用' : '禁用' }}
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
      <el-descriptions-item label="服务器数">{{ device.last_server_count || 0 }}</el-descriptions-item>
    </el-descriptions>

    <div v-if="device?.last_scan_error" style="margin-top:12px;">
      <el-alert :title="'扫描错误: ' + device.last_scan_error" type="error" show-icon :closable="false" />
    </div>

    <el-card style="margin-top:20px;">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="服务器清单" name="servers">
          <div class="filter-bar">
            <el-input v-model="search" placeholder="搜索名称、IP、操作系统、分组..." clearable style="width:380px"
              @keyup.enter="fetchServers" @clear="fetchServers" />
            <el-button type="primary" @click="fetchServers">查询</el-button>
          </div>
          <el-table ref="serversTable" :data="servers" stripe v-loading="loading" style="width:100%;"
            :row-key="(r) => r.id" @expand-change="onExpandChange">
            <template #empty>
              <el-empty description="暂无服务器数据，请先触发扫描" :image-size="60" />
            </template>
            <el-table-column type="expand">
              <template #default="{ row }">
                <div class="sub-data" @click.stop @mousedown.stop>
                  <el-tabs v-model="row._subTab" @tab-click="(t) => loadSubData(row, t.paneName)">
                    <el-tab-pane label="端口" name="ports">
                      <el-table :data="row._ports" stripe size="small" max-height="300" v-loading="row._loadingPorts">
                        <template #empty><el-empty description="暂无端口数据" :image-size="40" /></template>
                        <el-table-column prop="port" label="端口" width="80" />
                        <el-table-column prop="protocol" label="协议" width="60" />
                        <el-table-column prop="process_name" label="进程名" min-width="160" show-overflow-tooltip />
                        <el-table-column prop="start_user" label="启动用户" width="120" show-overflow-tooltip />
                        <el-table-column prop="process_version" label="进程版本" width="120" show-overflow-tooltip />
                      </el-table>
                      <div class="sub-pagination" v-if="row._portTotal > 50">
                        <el-pagination small background layout="total, prev, pager, next"
                          v-model:current-page="row._portPage" :total="row._portTotal" :page-size="50"
                          @current-change="(p) => loadSubData(row, 'ports', p)" />
                      </div>
                    </el-tab-pane>
                    <el-tab-pane label="进程" name="processes">
                      <el-table :data="row._processes" stripe size="small" max-height="300" v-loading="row._loadingProcs">
                        <template #empty><el-empty description="暂无进程数据" :image-size="40" /></template>
                        <el-table-column prop="process_name" label="进程名" min-width="180" show-overflow-tooltip />
                        <el-table-column prop="pid" label="PID" width="70" />
                        <el-table-column prop="start_user" label="启动用户" width="120" show-overflow-tooltip />
                        <el-table-column prop="cpu_percent" label="CPU%" width="70" />
                        <el-table-column prop="mem_percent" label="内存%" width="70" />
                      </el-table>
                      <div class="sub-pagination" v-if="row._procTotal > 50">
                        <el-pagination small background layout="total, prev, pager, next"
                          v-model:current-page="row._procPage" :total="row._procTotal" :page-size="50"
                          @current-change="(p) => loadSubData(row, 'processes', p)" />
                      </div>
                    </el-tab-pane>
                    <el-tab-pane label="软件" name="software">
                      <el-table :data="row._software" stripe size="small" max-height="300" v-loading="row._loadingSw">
                        <template #empty><el-empty description="暂无软件数据" :image-size="40" /></template>
                        <el-table-column prop="software_name" label="软件名" min-width="160" show-overflow-tooltip />
                        <el-table-column prop="version" label="版本" width="120" show-overflow-tooltip />
                        <el-table-column prop="install_path" label="安装路径" min-width="240" show-overflow-tooltip />
                      </el-table>
                      <div class="sub-pagination" v-if="row._swTotal > 50">
                        <el-pagination small background layout="total, prev, pager, next"
                          v-model:current-page="row._swPage" :total="row._swTotal" :page-size="50"
                          @current-change="(p) => loadSubData(row, 'software', p)" />
                      </div>
                    </el-tab-pane>
                  </el-tabs>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="machine_name" label="名称" min-width="140" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="server-name-link" @click="toggleExpand(row)">{{ row.machine_name }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="ipv4" label="IPv4" width="130" />
            <el-table-column prop="intranet_ip" label="内网 IP" width="130" />
            <el-table-column prop="operation_system" label="操作系统" min-width="160" show-overflow-tooltip />
            <el-table-column prop="cpu" label="CPU" min-width="160" show-overflow-tooltip />
            <el-table-column prop="memory" label="内存" width="70" />
            <el-table-column prop="disk_size_str" label="磁盘" width="80" />
            <el-table-column label="在线" width="70">
              <template #default="{ row }">
                <el-tag :type="row.online_status === 1 && row.run_status === 1 ? 'success' : row.online_status === 1 ? 'warning' : 'danger'" size="small">
                  {{ row.online_status === 1 && row.run_status === 1 ? '在线' : row.online_status === 1 ? 'Agent停' : '离线' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="machine_group" label="分组" width="90" show-overflow-tooltip />
            <el-table-column label="资产" width="160">
              <template #default="{ row }">
                <span style="font-size:12px;color:#606266;">
                  端口:{{ row.port_count }} 进程:{{ row.process_count }} 软件:{{ row.software_count }}
                </span>
              </template>
            </el-table-column>
          </el-table>
          <div class="pagination-wrap" v-if="totalServers > 0">
            <el-pagination
              v-model:current-page="page" :page-size="size" :total="totalServers"
              layout="total, prev, pager, next" @current-change="fetchServers" />
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
import { getQAXDevice, triggerQAXScan, getQAXServers, getQAXPorts, getQAXProcesses, getQAXSoftware } from '@/api/qax'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
const authStore = useAuthStore()
const deviceId = Number(route.params.id)
const device = ref(null)
const scanning = ref(false)
const activeTab = ref('servers')

const serversTable = ref(null)
const servers = ref([])
const loading = ref(false)
const page = ref(1)
const size = ref(20)
const totalServers = ref(0)
const search = ref('')

onMounted(async () => {
  try { device.value = await getQAXDevice(deviceId) } catch { /* 404 */ }
  fetchServers()
})

function toggleExpand(row) {
  if (!serversTable.value) return
  serversTable.value.toggleRowExpansion(row)
}

async function fetchServers() {
  loading.value = true
  try {
    const res = await getQAXServers(deviceId, { page: page.value, size: size.value, search: search.value })
    servers.value = res.items.map(s => ({
      ...s,
      _subTab: 'ports',
      _ports: null, _processes: null, _software: null,
      _loadingPorts: false, _loadingProcs: false, _loadingSw: false,
      _portTotal: 0, _procTotal: 0, _swTotal: 0,
      _portPage: 1, _procPage: 1, _swPage: 1,
    }))
    totalServers.value = res.total
  } finally {
    loading.value = false
  }
}

function onExpandChange(row, expandedRows) {
  // 展开行时自动加载当前激活子标签的数据
  if (expandedRows && expandedRows.includes(row)) {
    const tab = row._subTab || 'ports'
    loadSubData(row, tab)
  }
}

async function loadSubData(row, tab, p = 1) {
  const size = 50
  if (tab === 'ports') {
    row._loadingPorts = true
    try {
      const res = await getQAXPorts(deviceId, row.id, { page: p, size })
      row._ports = res.items
      row._portTotal = res.total
    } finally { row._loadingPorts = false }
  } else if (tab === 'processes') {
    row._loadingProcs = true
    try {
      const res = await getQAXProcesses(deviceId, row.id, { page: p, size })
      row._processes = res.items
      row._procTotal = res.total
    } finally { row._loadingProcs = false }
  } else if (tab === 'software') {
    row._loadingSw = true
    try {
      const res = await getQAXSoftware(deviceId, row.id, { page: p, size })
      row._software = res.items
      row._swTotal = res.total
    } finally { row._loadingSw = false }
  }
}

async function handleScan() {
  try {
    await ElMessageBox.confirm(`确认扫描椒图 ${device.value?.name}？`, '确认扫描')
    scanning.value = true
    await triggerQAXScan(deviceId)
    ElMessage.success('扫描已触发')
    setTimeout(() => { fetchServers(); fetchDevice() }, 3000)
  } catch { /* cancelled */ }
  finally { scanning.value = false }
}

async function fetchDevice() {
  try { device.value = await getQAXDevice(deviceId) } catch { /* */ }
}
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
  gap: 8px;
}
.header-left h2 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
}
.info-card {
  margin-bottom: 0;
}
.filter-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
}
.sub-data {
  padding: 8px 24px 16px 24px;
  background: #fafafa;
}
.sub-pagination {
  display: flex;
  justify-content: center;
  margin-top: 8px;
}
.server-name-link {
  color: var(--color-primary);
  cursor: pointer;
}
.pagination-wrap {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}
</style>
