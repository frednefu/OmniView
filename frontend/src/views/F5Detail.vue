<template>
  <div class="f5-detail">
    <div class="page-header">
      <div class="header-left">
        <el-button text @click="$router.back()">
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
        <h2>{{ device?.name || 'F5 详情' }}</h2>
      </div>
      <el-button v-if="authStore.isAdmin" type="primary" @click="handleScan" :loading="scanning">
        <el-icon><Refresh /></el-icon>立即扫描
      </el-button>
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
    </el-descriptions>

    <div v-if="device?.last_scan_error" style="margin-top:12px;">
      <el-alert :title="'扫描错误: ' + device.last_scan_error" type="error" show-icon :closable="false" />
    </div>

    <el-card style="margin-top:20px;">
      <el-tabs v-model="activeTab" @tab-click="onTabClick">
        <!-- ═══════════ 应用映射（核心 Tab） ═══════════ -->
        <el-tab-pane label="应用映射" name="appmap">
          <div class="filter-bar">
            <el-input v-model="searchApp" placeholder="搜索域名、VS名称/IP/端口、Pool、成员IP、iRule..." clearable style="width:420px"
              @keyup.enter="fetchAppMap" @clear="fetchAppMap" />
            <el-button type="primary" @click="fetchAppMap">查询</el-button>
          </div>
          <el-table :data="appMap" stripe v-loading="loadingApp" max-height="520" style="width:100%">
            <template #empty>
              <el-empty description="暂无映射数据，请先触发扫描" :image-size="60" />
            </template>
            <el-table-column prop="domain_name" label="域名" min-width="160" show-overflow-tooltip />
            <el-table-column prop="vs_ip" label="VS IP" width="130" />
            <el-table-column prop="vs_port" label="VS 端口" width="80" />
            <el-table-column prop="vs_name" label="VS 名称" min-width="150" show-overflow-tooltip />
            <el-table-column prop="pool_name" label="Pool" min-width="140" show-overflow-tooltip />
            <el-table-column label="来源" width="90">
              <template #default="{ row }">
                <el-tag v-if="row.source === 'irule'" type="success" size="small">iRule</el-tag>
                <el-tag v-else-if="row.source === 'pool'" type="primary" size="small">Pool</el-tag>
                <el-tag v-else-if="row.source === 'vs_name'" type="info" size="small">VS名称</el-tag>
                <el-tag v-else size="small">{{ row.source }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="rule_name" label="iRule" min-width="140" show-overflow-tooltip />
            <el-table-column prop="member_ip" label="成员 IP" width="130" />
            <el-table-column prop="member_port" label="成员端口" width="80" />
            <el-table-column label="成员状态" width="90">
              <template #default="{ row }">
                <el-tag v-if="row.member_state === 'up'" type="success" size="small">UP</el-tag>
                <el-tag v-else-if="row.member_state === 'down'" type="danger" size="small">DOWN</el-tag>
                <el-tag v-else-if="row.member_state === 'disabled'" type="info" size="small">禁用</el-tag>
                <span v-else-if="row.member_state">{{ row.member_state }}</span>
                <span v-else style="color:#c0c4cc;">-</span>
              </template>
            </el-table-column>
          </el-table>
          <div class="pagination-wrap" v-if="totalApp > 0">
            <el-pagination
              v-model:current-page="pageApp" :page-size="sizeApp" :total="totalApp"
              layout="total, prev, pager, next" @current-change="fetchAppMap" small />
          </div>
        </el-tab-pane>

        <!-- ═══════════ 虚拟服务器 Tab ═══════════ -->
        <el-tab-pane label="虚拟服务器" name="vs">
          <div class="filter-bar">
            <el-input v-model="searchVS" placeholder="搜索 VS 名称、IP、目标、Pool..." clearable style="width:320px"
              @keyup.enter="fetchVS" @clear="fetchVS" />
            <el-button type="primary" @click="fetchVS">查询</el-button>
          </div>
          <el-table :data="vsData" stripe v-loading="loadingVS" max-height="520" style="width:100%">
            <template #empty>
              <el-empty description="暂无虚拟服务器数据" :image-size="60" />
            </template>
            <el-table-column prop="name" label="VS 名称" min-width="200" show-overflow-tooltip />
            <el-table-column prop="vs_ip" label="IP" width="140" />
            <el-table-column prop="vs_port" label="端口" width="70" />
            <el-table-column prop="destination" label="原始目标" min-width="200" show-overflow-tooltip />
            <el-table-column prop="pool_name" label="Pool" min-width="160" show-overflow-tooltip />
            <el-table-column label="iRules" min-width="200" show-overflow-tooltip>
              <template #default="{ row }">
                {{ formatRules(row.rules) }}
              </template>
            </el-table-column>
          </el-table>
          <div class="pagination-wrap" v-if="totalVS > 0">
            <el-pagination
              v-model:current-page="pageVS" :page-size="sizeVS" :total="totalVS"
              layout="total, prev, pager, next" @current-change="fetchVS" small />
          </div>
        </el-tab-pane>

        <!-- ═══════════ Pool 成员 Tab ═══════════ -->
        <el-tab-pane label="Pool 成员" name="pool">
          <div class="filter-bar">
            <el-input v-model="searchPool" placeholder="搜索 Pool 名称、成员名称、成员 IP..." clearable style="width:320px"
              @keyup.enter="fetchPool" @clear="fetchPool" />
            <el-button type="primary" @click="fetchPool">查询</el-button>
          </div>
          <el-table :data="poolData" stripe v-loading="loadingPool" max-height="520" style="width:100%">
            <template #empty>
              <el-empty description="暂无 Pool 成员数据" :image-size="60" />
            </template>
            <el-table-column prop="pool_name" label="Pool 名称" min-width="160" show-overflow-tooltip />
            <el-table-column prop="member_name" label="成员名称" min-width="200" show-overflow-tooltip />
            <el-table-column prop="member_ip" label="IP" width="140" />
            <el-table-column prop="member_port" label="端口" width="70" />
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-tag v-if="row.member_state === 'up'" type="success" size="small">UP</el-tag>
                <el-tag v-else-if="row.member_state === 'down'" type="danger" size="small">DOWN</el-tag>
                <el-tag v-else-if="row.member_state === 'disabled'" type="info" size="small">禁用</el-tag>
                <span v-else>{{ row.member_state }}</span>
              </template>
            </el-table-column>
          </el-table>
          <div class="pagination-wrap" v-if="totalPool > 0">
            <el-pagination
              v-model:current-page="pagePool" :page-size="sizePool" :total="totalPool"
              layout="total, prev, pager, next" @current-change="fetchPool" small />
          </div>
        </el-tab-pane>

        <!-- ═══════════ iRules Tab ═══════════ -->
        <el-tab-pane label="iRules" name="rules">
          <div class="filter-bar">
            <el-input v-model="searchRule" placeholder="搜索 iRule 名称或内容..." clearable style="width:320px"
              @keyup.enter="fetchRules" @clear="fetchRules" />
            <el-button type="primary" @click="fetchRules">查询</el-button>
          </div>
          <el-table :data="ruleData" stripe v-loading="loadingRule" max-height="520" style="width:100%">
            <template #empty>
              <el-empty description="暂无 iRule 数据" :image-size="60" />
            </template>
            <el-table-column type="expand">
              <template #default="{ row }">
                <pre class="rule-content">{{ row.rule_content || '(无内容)' }}</pre>
              </template>
            </el-table-column>
            <el-table-column prop="rule_name" label="iRule 名称" min-width="300" show-overflow-tooltip />
          </el-table>
          <div class="pagination-wrap" v-if="totalRule > 0">
            <el-pagination
              v-model:current-page="pageRule" :page-size="sizeRule" :total="totalRule"
              layout="total, prev, pager, next" @current-change="fetchRules" small />
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
import {
  getF5Device, triggerF5Scan, getF5ApplicationMap,
  getF5VirtualServers, getF5PoolMembers, getF5Rules,
} from '@/api/f5'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
const authStore = useAuthStore()
const device = ref(null)
const activeTab = ref('appmap')
const scanning = ref(false)

// 应用映射
const appMap = ref([])
const loadingApp = ref(false)
const pageApp = ref(1); const sizeApp = ref(50); const totalApp = ref(0)
const searchApp = ref('')

// 虚拟服务器
const vsData = ref([])
const loadingVS = ref(false)
const pageVS = ref(1); const sizeVS = ref(20); const totalVS = ref(0)
const searchVS = ref('')

// Pool 成员
const poolData = ref([])
const loadingPool = ref(false)
const pagePool = ref(1); const sizePool = ref(20); const totalPool = ref(0)
const searchPool = ref('')

// iRules
const ruleData = ref([])
const loadingRule = ref(false)
const pageRule = ref(1); const sizeRule = ref(20); const totalRule = ref(0)
const searchRule = ref('')

async function fetchDevice() {
  device.value = await getF5Device(route.params.id)
}

async function fetchAppMap() {
  loadingApp.value = true
  try {
    const res = await getF5ApplicationMap(route.params.id, { page: pageApp.value, size: sizeApp.value, search: searchApp.value })
    appMap.value = res.items
    totalApp.value = res.total
  } finally { loadingApp.value = false }
}

async function fetchVS() {
  loadingVS.value = true
  try {
    const res = await getF5VirtualServers(route.params.id, {
      page: pageVS.value, size: sizeVS.value, search: searchVS.value,
    })
    vsData.value = res.items
    totalVS.value = res.total
  } finally { loadingVS.value = false }
}

async function fetchPool() {
  loadingPool.value = true
  try {
    const res = await getF5PoolMembers(route.params.id, {
      page: pagePool.value, size: sizePool.value, search: searchPool.value,
    })
    poolData.value = res.items
    totalPool.value = res.total
  } finally { loadingPool.value = false }
}

async function fetchRules() {
  loadingRule.value = true
  try {
    const res = await getF5Rules(route.params.id, {
      page: pageRule.value, size: sizeRule.value, search: searchRule.value,
    })
    ruleData.value = res.items
    totalRule.value = res.total
  } finally { loadingRule.value = false }
}

function onTabClick(tab) {
  const name = tab.props?.name || tab.paneName?.value
  if (name === 'appmap') { if (appMap.value.length === 0) fetchAppMap() }
  else if (name === 'vs') fetchVS()
  else if (name === 'pool') fetchPool()
  else if (name === 'rules') fetchRules()
}

function formatRules(rulesStr) {
  try {
    const arr = JSON.parse(rulesStr)
    return arr.join(', ')
  } catch { return rulesStr || '-' }
}

async function handleScan() {
  try {
    await ElMessageBox.confirm('确认扫描此 F5 设备？', '确认扫描')
    scanning.value = true
    await triggerF5Scan(route.params.id)
    ElMessage.success('扫描已触发，请稍后刷新查看结果')
    setTimeout(() => { fetchDevice(); fetchAppMap() }, 3000)
  } catch { /* cancelled */ }
  finally { scanning.value = false }
}

onMounted(() => { fetchDevice(); fetchAppMap() })
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
.rule-content {
  max-height: 400px;
  overflow: auto;
  background: var(--color-bg);
  padding: 12px 16px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--color-text);
}
</style>
