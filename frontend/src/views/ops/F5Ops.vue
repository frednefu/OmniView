<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>F5 系统运维</h2>
        <p class="page-desc">虚拟服务器 · 规则 · 成员池</p>
      </div>
      <div class="header-actions">
        <el-select v-model="selectedDevice" placeholder="选择 F5 设备" style="width:260px" @change="onDeviceChange"
          :loading="loadingDevices">
          <el-option v-for="d in devices" :key="d.id" :label="d.name" :value="d.id" />
        </el-select>
      </div>
    </div>

    <!-- 未选设备 -->
    <div v-if="!selectedDevice" class="empty-device">
      <el-empty description="请选择一台已扫描的 F5 设备" :image-size="100" />
    </div>

    <!-- 标签页 -->
    <template v-else>
      <el-tabs v-model="activeTab" @tab-click="onTabChange" class="ops-tabs">
        <!-- ═══════════ 虚拟服务器 ═══════════ -->
        <el-tab-pane label="虚拟服务器 (Virtual Servers)" name="vs">
          <div class="filter-bar">
            <el-input v-model="vsSearch" placeholder="搜索 IP 或域名..." clearable style="width:260px"
              @keyup.enter="vsPage=1;fetchVS()" @clear="vsPage=1;fetchVS()" />
            <el-select v-model="vsStatusFilter" placeholder="全部状态" clearable style="width:130px" @change="vsPage=1;fetchVS()">
              <el-option label="正常" value="active" />
              <el-option label="部分注销" value="partial" />
              <el-option label="注销" value="deregistered" />
            </el-select>
            <span class="total-hint">共 {{ vsTotal }} 条</span>
          </div>

          <el-table :data="vsItems" stripe size="small" v-loading="loadingVS" class="ops-table">
            <el-table-column prop="vs_names" label="VS名称" min-width="160" show-overflow-tooltip />
            <el-table-column label="iRules" min-width="140">
              <template #default="{ row }">
                <div class="ref-list" v-if="row.irules && row.irules.length > 0">
                  <el-tag v-for="r in row.irules" :key="r" size="small" type="warning" class="ref-tag">{{ r }}</el-tag>
                </div>
                <span v-else class="text-muted">—</span>
              </template>
            </el-table-column>
            <el-table-column label="域名" min-width="200">
              <template #default="{ row }">
                <div class="domain-list" v-if="row.domains && row.domains.length > 0">
                  <div v-for="d in row.domains" :key="d.domain_name" class="domain-row">
                    <span class="domain-name" :class="{ 'domain-gone': !d.zdns_exists }">{{ d.domain_name }}</span>
                    <el-tag v-if="d.zdns_exists" size="small" :type="d.record_type === 'A' ? '' : 'success'"
                      style="margin-left:6px;flex-shrink:0">{{ d.record_type }}</el-tag>
                    <el-tag v-else size="small" type="danger" style="margin-left:6px;flex-shrink:0">注销</el-tag>
                  </div>
                </div>
                <span v-else class="text-muted">—</span>
              </template>
            </el-table-column>
            <el-table-column prop="vs_ip" label="服务IP" width="150" />
            <el-table-column prop="vs_port" label="服务端口" width="90" align="center" />
            <el-table-column label="内网服务器" min-width="340">
              <template #default="{ row }">
                <div class="server-groups" v-if="row.internal_servers && row.internal_servers.length > 0">
                  <div v-for="(sg, idx) in row.internal_servers" :key="idx" class="server-group">
                    <div class="sg-tags">
                      <el-tag type="primary" size="small" v-if="sg.pool_name">Pool: {{ sg.pool_name }}</el-tag>
                      <el-tag type="success" size="small" v-if="sg.rule_name">iRule: {{ sg.rule_name }}</el-tag>
                      <el-tag size="small" :type="sg.source === 'irule' ? 'warning' : 'info'" v-if="sg.source">
                        {{ sg.source === 'irule' ? 'iRule引用' : '默认Pool' }}
                      </el-tag>
                      <span class="sg-domain" v-if="sg.domain">{{ sg.domain }}</span>
                    </div>
                    <div class="sg-members">
                      <span v-for="(m, mi) in sg.members" :key="mi" class="member-item">
                        <span class="member-dot" :class="m.state && m.state.toLowerCase() === 'up' ? 'dot-up' : 'dot-down'"></span>
                        {{ m.ip }}{{ m.port ? ':' + m.port : '' }}
                      </span>
                    </div>
                  </div>
                </div>
                <span v-else class="text-muted">—</span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="100" align="center">
              <template #default="{ row }">
                <el-tag :type="statusTag(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="member_count" label="成员数" width="75" align="center" />
          </el-table>

          <el-pagination v-if="vsTotal > 0" v-model:current-page="vsPage" v-model:page-size="vsSize"
            :page-sizes="[20, 50, 100]" :total="vsTotal" layout="total, sizes, prev, pager, next"
            @current-change="vsPageChange" @size-change="vsPageChange" style="justify-content:center;margin-top:16px" />
        </el-tab-pane>

        <!-- ═══════════ 规则 ═══════════ -->
        <el-tab-pane label="规则 (iRules)" name="rules">
          <div class="filter-bar">
            <el-input v-model="ruleSearch" placeholder="搜索 iRule 名称或域名..." clearable style="width:260px"
              @keyup.enter="rulePage=1;fetchRules()" @clear="rulePage=1;fetchRules()" />
            <el-select v-model="ruleStatusFilter" placeholder="全部状态" clearable style="width:120px" @change="rulePage=1;fetchRules()">
              <el-option label="正常" value="active" />
              <el-option label="部分注销" value="partial" />
              <el-option label="注销" value="deregistered" />
              <el-option label="无域名" value="no_domain" />
            </el-select>
            <span class="total-hint">共 {{ ruleTotal }} 条</span>
          </div>

          <el-table :data="ruleItems" stripe size="small" v-loading="loadingRule" class="ops-table">
            <el-table-column prop="rule_name" label="iRule 名称" width="220" show-overflow-tooltip />
            <el-table-column label="域名 → Pool" min-width="320">
              <template #default="{ row }">
                <div v-if="row.domain_pool_mappings && row.domain_pool_mappings.length > 0" class="mapping-list">
                  <div v-for="(m, idx) in row.domain_pool_mappings" :key="idx" class="mapping-row">
                    <el-tag size="small" :type="m.zdns_exists ? '' : 'danger'">{{ m.domain }}</el-tag>
                    <span class="mapping-arrow">→</span>
                    <el-tag size="small" type="primary">{{ m.pool }}</el-tag>
                  </div>
                </div>
                <span v-else class="text-muted">—</span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="statusTag(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="mapping_count" label="映射数" width="70" align="center" />
          </el-table>

          <el-pagination v-if="ruleTotal > 0" v-model:current-page="rulePage" v-model:page-size="ruleSize"
            :page-sizes="[20, 50, 100]" :total="ruleTotal" layout="total, sizes, prev, pager, next"
            @current-change="rulePageChange" @size-change="rulePageChange" style="justify-content:center;margin-top:16px" />
        </el-tab-pane>

        <!-- ═══════════ 成员池 ═══════════ -->
        <el-tab-pane label="成员池 (Pools)" name="pools">
          <div class="filter-bar">
            <el-input v-model="poolSearch" placeholder="搜索 Pool 名称..." clearable style="width:260px"
              @keyup.enter="poolPage=1;fetchPools()" @clear="poolPage=1;fetchPools()" />
            <el-select v-model="poolStatusFilter" placeholder="运行状态" clearable style="width:130px" @change="poolPage=1;fetchPools()">
              <el-option label="全部 UP" value="up" />
              <el-option label="部分 UP" value="mixed" />
              <el-option label="全部 DOWN" value="down" />
            </el-select>
            <el-select v-model="poolRefFilter" placeholder="引用状态" clearable style="width:130px" @change="poolPage=1;fetchPools()">
              <el-option label="引用" value="full" />
              <el-option label="部分引用" value="partial" />
              <el-option label="无引用" value="none" />
            </el-select>
            <span class="total-hint">共 {{ poolTotal }} 条</span>
          </div>

          <el-table :data="poolItems" stripe size="small" v-loading="loadingPool" class="ops-table">
            <el-table-column label="状态" width="85">
              <template #default="{ row }">
                <el-tag :type="poolStatusTag(row.status)" size="small">{{ poolStatusLabel(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="引用状态" width="90" align="center">
              <template #default="{ row }">
                <el-tag :type="refStatusTag(row.ref_status)" size="small">{{ refStatusLabel(row.ref_status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="pool_name" label="Pool 名称" min-width="160" show-overflow-tooltip />
            <el-table-column label="成员清单" min-width="220">
              <template #default="{ row }">
                <div class="sg-members" v-if="row.members && row.members.length > 0">
                  <span v-for="(m, mi) in row.members" :key="mi" class="member-item">
                    <span class="member-dot" :class="m.state && m.state.toLowerCase() === 'up' ? 'dot-up' : 'dot-down'"></span>
                    {{ m.ip }}{{ m.port ? ':' + m.port : '' }}
                  </span>
                </div>
                <span v-else class="text-muted">—</span>
              </template>
            </el-table-column>
            <el-table-column label="引用 VS" min-width="160">
              <template #default="{ row }">
                <div v-if="row.referenced_vs && row.referenced_vs.length > 0" class="ref-list">
                  <el-tag v-for="v in row.referenced_vs" :key="v" size="small" type="primary" class="ref-tag">{{ v }}</el-tag>
                </div>
                <span v-else class="text-muted">—</span>
              </template>
            </el-table-column>
            <el-table-column label="引用 iRules" min-width="160">
              <template #default="{ row }">
                <div v-if="row.referenced_rules && row.referenced_rules.length > 0" class="ref-list">
                  <el-tag v-for="r in row.referenced_rules" :key="r" size="small" type="success" class="ref-tag">{{ r }}</el-tag>
                </div>
                <span v-else class="text-muted">—</span>
              </template>
            </el-table-column>
            <el-table-column prop="member_count" label="成员数" width="70" align="center" />
          </el-table>

          <el-pagination v-if="poolTotal > 0" v-model:current-page="poolPage" v-model:page-size="poolSize"
            :page-sizes="[20, 50, 100]" :total="poolTotal" layout="total, sizes, prev, pager, next"
            @current-change="poolPageChange" @size-change="poolPageChange" style="justify-content:center;margin-top:16px" />
        </el-tab-pane>
      </el-tabs>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '@/api/index'

// ── 设备选择 ──
const devices = ref([])
const selectedDevice = ref(null)
const loadingDevices = ref(false)
const activeTab = ref('vs')

// ── VS 状态 ──
const vsItems = ref([])
const vsSearch = ref('')
const vsStatusFilter = ref('')
const vsPage = ref(1)
const vsSize = ref(50)
const vsTotal = ref(0)
const loadingVS = ref(false)

// ── Pool 状态 ──
const poolItems = ref([])
const poolSearch = ref('')
const poolStatusFilter = ref('')
const poolRefFilter = ref('')
const poolPage = ref(1)
const poolSize = ref(50)
const poolTotal = ref(0)
const loadingPool = ref(false)

// ── Rule 状态 ──
const ruleItems = ref([])
const ruleSearch = ref('')
const ruleStatusFilter = ref('')
const rulePage = ref(1)
const ruleSize = ref(50)
const ruleTotal = ref(0)
const loadingRule = ref(false)

// ── 加载设备列表 ──
async function loadDevices() {
  loadingDevices.value = true
  try {
    const r = await api.get('/f5', { params: { size: 100 } })
    devices.value = (r.data.items || []).filter(d => d.last_scan_status === 'success' || d.last_scan_status === 'running')
    if (devices.value.length === 1) {
      selectedDevice.value = devices.value[0].id
      fetchAll()
    }
  } catch { /* handled */ }
  finally { loadingDevices.value = false }
}

function onDeviceChange() {
  if (!selectedDevice.value) return
  vsPage.value = 1; poolPage.value = 1; rulePage.value = 1
  fetchAll()
}

function onTabChange() {
  if (!selectedDevice.value) return
  if (activeTab.value === 'vs' && vsItems.value.length === 0) fetchVS()
  else if (activeTab.value === 'pools' && poolItems.value.length === 0) fetchPools()
  else if (activeTab.value === 'rules' && ruleItems.value.length === 0) fetchRules()
}

function fetchAll() {
  fetchVS()
  fetchPools()
  fetchRules()
}

// ── 客户端分页 ──
function paginate(allItems, page, size) {
  const start = (page - 1) * size
  return allItems.slice(start, start + size)
}
function vsPageChange() { vsItems.value = paginate(vsAll, vsPage.value, vsSize.value) }
function poolPageChange() { poolItems.value = paginate(poolAll, poolPage.value, poolSize.value) }
function rulePageChange() { ruleItems.value = paginate(ruleAll, rulePage.value, ruleSize.value) }

// ── 获取虚拟服务器 ──
let vsAll = []
async function fetchVS() {
  if (!selectedDevice.value) return
  loadingVS.value = true
  try {
    const r = await api.get('/ops/f5/virtual-servers', {
      params: { f5_device_id: selectedDevice.value, search: vsSearch.value }
    })
    vsAll = (r.data.items || []).filter(i => !vsStatusFilter.value || i.status === vsStatusFilter.value)
    vsTotal.value = vsAll.length
    vsItems.value = paginate(vsAll, vsPage.value, vsSize.value)
  } catch { /* handled */ }
  finally { loadingVS.value = false }
}

// ── 获取资源池 ──
let poolAll = []
async function fetchPools() {
  if (!selectedDevice.value) return
  loadingPool.value = true
  try {
    const r = await api.get('/ops/f5/pools', {
      params: { f5_device_id: selectedDevice.value, search: poolSearch.value }
    })
    poolAll = (r.data.items || [])
      .filter(i => !poolStatusFilter.value || i.status === poolStatusFilter.value)
      .filter(i => !poolRefFilter.value || i.ref_status === poolRefFilter.value)
    poolTotal.value = poolAll.length
    poolItems.value = paginate(poolAll, poolPage.value, poolSize.value)
  } catch { /* handled */ }
  finally { loadingPool.value = false }
}

// ── 获取规则 ──
let ruleAll = []
async function fetchRules() {
  if (!selectedDevice.value) return
  loadingRule.value = true
  try {
    const r = await api.get('/ops/f5/rules', {
      params: { f5_device_id: selectedDevice.value, search: ruleSearch.value }
    })
    ruleAll = (r.data.items || []).filter(i => !ruleStatusFilter.value || i.status === ruleStatusFilter.value)
    ruleTotal.value = ruleAll.length
    ruleItems.value = paginate(ruleAll, rulePage.value, ruleSize.value)
  } catch { /* handled */ }
  finally { loadingRule.value = false }
}

// ── 状态辅助 ──
function statusTag(s) {
  const map = { active: 'success', partial: 'warning', deregistered: 'danger', no_domain: 'info' }
  return map[s] || 'info'
}
function statusLabel(s) {
  const map = { active: '正常', partial: '部分注销', deregistered: '注销', no_domain: '无域名' }
  return map[s] || s
}
function poolStatusTag(s) {
  const map = { up: 'success', mixed: 'warning', down: 'danger' }
  return map[s] || 'info'
}
function poolStatusLabel(s) {
  const map = { up: '全部UP', mixed: '部分UP', down: '全部DOWN' }
  return map[s] || s
}
function refStatusTag(s) {
  const map = { full: 'success', partial: 'warning', none: 'info' }
  return map[s] || 'info'
}
function refStatusLabel(s) {
  const map = { full: '引用', partial: '部分引用', none: '无引用' }
  return map[s] || s
}

onMounted(() => { loadDevices() })
</script>

<style scoped>
.page { padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
.page-header h2 { margin: 0; font-size: 20px; font-weight: 700; }
.page-desc { margin: 4px 0 0; font-size: 13px; color: var(--color-text-muted); }
.header-actions { display: flex; gap: 10px; align-items: center; }

.empty-device { padding: 60px 0; }

.ops-tabs { margin-top: 4px; }

.filter-bar { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
.total-hint { font-size: 13px; color: var(--color-text-muted); white-space: nowrap; }

.ops-table { width: 100%; }
/* VS 表格：限制域名和内网服务器区域高度，保持行高一致 */
.ops-table .domain-list { max-height: 160px; overflow-y: auto; }
.ops-table .server-groups { max-height: 220px; overflow-y: auto; }

/* ── 域名列表 ── */
.domain-list { display: flex; flex-direction: column; gap: 3px; }
.domain-row { display: flex; align-items: center; font-size: 13px; }
.domain-name { color: var(--color-text); word-break: break-all; }
.domain-name.domain-gone { color: var(--color-text-muted); text-decoration: line-through; }

/* ── 内网服务器 ── */
.server-groups { display: flex; flex-direction: column; gap: 6px; }
.server-group { padding: 4px 8px; background: var(--color-bg); border-radius: 4px; border: 1px solid var(--color-border); }
.sg-tags { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; margin-bottom: 3px; }
.sg-domain { font-size: 11px; color: var(--color-text-muted); max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sg-members { display: flex; flex-wrap: wrap; gap: 4px; }
.member-item { display: inline-flex; align-items: center; gap: 3px; font-size: 12px; color: var(--color-text-secondary); white-space: nowrap; }
.member-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.dot-up { background: #10b981; }
.dot-down { background: #ef4444; }

/* ── 引用列表 ── */
.ref-list { display: flex; flex-wrap: wrap; gap: 4px; }
.ref-tag { margin: 0; }

/* ── 映射列表 ── */
.mapping-list { display: flex; flex-direction: column; gap: 4px; }
.mapping-row { display: flex; align-items: center; gap: 6px; font-size: 13px; }
.mapping-arrow { color: var(--color-text-muted); font-weight: 600; }

.text-muted { color: var(--color-text-muted); font-size: 13px; }
</style>
