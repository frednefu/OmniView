<template>
  <div class="asset-page">
    <div class="page-header">
      <h2>信息资产管理</h2>
      <div class="header-right">
        <el-switch v-model="hideEmpty" active-text="隐藏空部门" @change="loadTree" />
        <el-button type="info" plain @click="handleSync" :loading="syncLoading">同步资产</el-button>
        <el-button @click="showMatchPreview" :loading="previewLoading">分组预览</el-button>
        <el-button type="primary" @click="handleAutoMatch" :loading="autoMatchLoading">自动分组</el-button>
        <el-button type="success" plain @click="handleMatchOwner" :loading="ownerMatchLoading">匹配负责人</el-button>
        <el-button type="danger" plain @click="handleResetAll">重置关联</el-button>
        <el-button type="success" @click="showClaimDialog">资产认领</el-button>
        <el-button v-if="authStore.isAdmin && selectedVMs.length > 0" type="warning" @click="showAssignDialog(selectedVMs)">指派选中 ({{ selectedVMs.length }})</el-button>
        <el-button v-if="authStore.isAdmin" type="warning" plain @click="showAssignDialog([])">搜索指派</el-button>
      </div>
    </div>

    <div class="asset-content">
      <!-- 左侧组织树 -->
      <div class="tree-panel">
        <el-input v-model="treeFilter" placeholder="搜索部门..." clearable size="small" style="margin-bottom:10px" @input="filterTree" />
        <el-tree
          ref="treeRef"
          :data="treeData"
          :props="{ children: 'children', label: 'label' }"
          node-key="id"
          default-expand-all
          highlight-current
          :filter-node-method="filterNode"
          @node-click="handleNodeClick"
        >
          <template #default="{ data }">
            <span class="tree-node">
              <el-icon v-if="data.id === -1"><WarningFilled /></el-icon>
              <el-icon v-else><OfficeBuilding /></el-icon>
              <span class="node-label">{{ data.label }}</span>
              <span class="node-stats">
                <span class="stat-v">V:{{ data.vm_count || 0 }}</span>
                <span class="stat-d">D:{{ data.domain_count || 0 }}</span>
                <span class="stat-s">S:{{ data.system_count || 0 }}</span>
              </span>
            </span>
          </template>
        </el-tree>
      </div>

      <!-- 右侧资产面板 -->
      <div class="detail-panel">
        <template v-if="selectedNode">
          <div class="detail-header">
            <h3>{{ selectedNode.full_name || selectedNode.label }}</h3>
          </div>
          <el-tabs v-model="activeTab">
            <el-tab-pane label="虚拟机清单" name="vms">
              <div class="filter-bar">
                <el-input v-model="vmSearch" placeholder="搜索名称、IP、MAC、OS..." clearable size="small" style="width:260px" @keyup.enter="vmPage=1;loadVMs()" @clear="vmPage=1;loadVMs()" />
                <el-select v-model="vmClaimFilter" placeholder="分组状态" clearable size="small" style="width:110px" @change="vmPage=1;loadVMs()">
                  <el-option label="未分组" value="unlinked" />
                  <el-option label="自动" value="auto" />
                  <el-option label="手动" value="manual" />
                </el-select>
                <el-select v-model="vmClaimedFilter" placeholder="认领状态" clearable size="small" style="width:110px" @change="vmPage=1;loadVMs()">
                  <el-option label="已认领" value="yes" />
                  <el-option label="未认领" value="no" />
                </el-select>
                <el-select v-model="vmPowerFilter" placeholder="电源状态" clearable size="small" style="width:100px" @change="vmPage=1;loadVMs()">
                  <el-option v-for="s in filterOptions.power_states" :key="s" :label="s==='poweredOn'?'开机':'关机'" :value="s" />
                </el-select>
                <el-select v-model="vmOsFilter" placeholder="操作系统" clearable filterable size="small" style="width:160px" @change="vmPage=1;loadVMs()">
                  <el-option v-for="s in filterOptions.os_names" :key="s" :label="s" :value="s" />
                </el-select>
                <el-select v-model="vmNetFilter" placeholder="网络" clearable filterable size="small" style="width:140px" @change="vmPage=1;loadVMs()">
                  <el-option v-for="s in filterOptions.networks" :key="s" :label="s" :value="s" />
                </el-select>
                <el-select v-model="vmFolderFilter" placeholder="文件夹" clearable filterable size="small" style="width:140px" @change="vmPage=1;loadVMs()">
                  <el-option v-for="s in filterOptions.folders" :key="s" :label="s" :value="s" />
                </el-select>
                <el-button type="primary" size="small" @click="vmPage=1;loadVMs()">查询</el-button>
                <el-button type="success" size="small" :disabled="selectedVMs.length===0" @click="handleClaim">认领资产</el-button>
                <el-button type="warning" size="small" :disabled="selectedVMs.length===0" @click="handleRevoke">撤销认领</el-button>
              </div>
              <div class="total-info">共 {{ vmTotal }} 条，已选 {{ selectedVMs.length }} 条</div>
              <el-table :data="vmList" v-loading="vmLoading" stripe size="small" max-height="calc(100vh - 400px)" @selection-change="onVMSelect">
                <el-table-column type="selection" width="35" />
                <el-table-column prop="vm_name" label="名称" width="150" show-overflow-tooltip />
                <el-table-column prop="power_state" label="电源" width="65">
                  <template #default="{ row }">
                    <el-tag :type="row.power_state === 'poweredOn' ? 'success' : 'info'" size="small">{{ row.power_state === 'poweredOn' ? '开' : '关' }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="provisioned_gb" label="置备空间" width="80">
                  <template #default="{ row }">{{ row.provisioned_gb ? row.provisioned_gb + 'G' : '-' }}</template>
                </el-table-column>
                <el-table-column prop="used_gb" label="已用空间" width="80">
                  <template #default="{ row }">{{ row.used_gb ? row.used_gb + 'G' : '-' }}</template>
                </el-table-column>
                <el-table-column prop="cpu_count" label="CPU" width="50" />
                <el-table-column prop="memory_gb" label="内存" width="55">
                  <template #default="{ row }">{{ row.memory_gb ? row.memory_gb + 'G' : '-' }}</template>
                </el-table-column>
                <el-table-column prop="os_name" label="操作系统" min-width="130" show-overflow-tooltip />
                <el-table-column prop="ip_address" label="IP" width="130" show-overflow-tooltip />
                <el-table-column prop="mac_address" label="MAC" width="130" show-overflow-tooltip />
                <el-table-column prop="vcenter_name" label="vCenter" width="100" show-overflow-tooltip />
                <el-table-column prop="resource_pool" label="资源池" width="100" show-overflow-tooltip />
                <el-table-column prop="vm_folder" label="文件夹" width="120" show-overflow-tooltip />
                <el-table-column prop="remark" label="备注" min-width="120" show-overflow-tooltip />
                <el-table-column prop="f5_public_ips" label="公网IP" width="130" show-overflow-tooltip />
                <el-table-column prop="f5_domains" label="关联域名" min-width="140" show-overflow-tooltip />
                <el-table-column prop="claim_status" label="分组" width="70">
                  <template #default="{ row }">
                    <el-tag :type="row.claim_status === 'auto' ? 'success' : row.claim_status === 'manual' ? '' : 'info'" size="small">
                      {{ row.claim_status === 'auto' ? '自动' : row.claim_status === 'manual' ? '手动' : '未分组' }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="认领" width="70">
                  <template #default="{ row }">
                    <el-tag :type="row.owner_name ? '' : 'info'" size="small">{{ row.owner_name ? '已认领' : '未认领' }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="owner_name" label="负责人" width="80" />
              </el-table>
              <el-pagination
                v-if="vmTotal > vmSize"
                v-model:current-page="vmPage"
                :page-size="vmSize"
                :total="vmTotal"
                layout="prev, pager, next"
                small
                @current-change="loadVMs"
                style="margin-top:10px;justify-content:center"
              />
            </el-tab-pane>

            <el-tab-pane label="域名清单" name="domains">
              <div class="filter-bar">
                <el-input v-model="domainSearch" placeholder="搜索域名或 IP" clearable size="small" style="width:220px" @keyup.enter="domainPage=1;loadDomains()" @clear="domainPage=1;loadDomains()" />
                <el-select v-model="domainTypeFilter" placeholder="记录类型" clearable size="small" style="width:100px" @change="domainPage=1;loadDomains()">
                  <el-option label="A" value="A" />
                  <el-option label="AAAA" value="AAAA" />
                  <el-option label="CNAME" value="CNAME" />
                </el-select>
                <el-button type="primary" size="small" @click="domainPage=1;loadDomains()">查询</el-button>
                <el-button type="success" size="small" :disabled="selectedDomains.length===0" @click="assignDomains">认领域名</el-button>
                <el-button type="warning" size="small" :disabled="selectedDomains.length===0" @click="revokeDomains">撤销认领</el-button>
              </div>
              <div class="total-info">共 {{ domainTotal }} 条，已选 {{ selectedDomains.length }} 条</div>
              <el-table :data="domainList" v-loading="domainLoading" stripe size="small" max-height="calc(100vh - 400px)" @selection-change="onDomainSelect">
                <el-table-column type="selection" width="35" />
                <el-table-column prop="domain_name" label="域名" min-width="200" show-overflow-tooltip />
                <el-table-column prop="record_type" label="类型" width="70" />
                <el-table-column prop="ip_address" label="IP" width="140" />
                <el-table-column prop="source" label="来源" width="60">
                  <template #default="{ row }">
                    <el-tag :type="row.source === 'ZDNS' ? '' : 'success'" size="small">{{ row.source }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="vm_name" label="关联 VM" min-width="120" show-overflow-tooltip />
                <el-table-column prop="owner_name" label="负责人" width="80" />
                <el-table-column label="认领" width="65">
                  <template #default="{ row }">
                    <el-tag :type="row.owner_name ? '' : 'info'" size="small">{{ row.owner_name ? '已认领' : '未认领' }}</el-tag>
                  </template>
                </el-table-column>
              </el-table>
              <el-pagination
                v-if="domainTotal > domainSize"
                v-model:current-page="domainPage"
                :page-size="domainSize"
                :total="domainTotal"
                layout="prev, pager, next"
                small
                @current-change="loadDomains"
                style="margin-top:10px;justify-content:center"
              />
            </el-tab-pane>

            <el-tab-pane label="信息系统" name="systems">
              <el-empty description="暂无数据，功能开发中" />
            </el-tab-pane>
          </el-tabs>
        </template>
        <el-empty v-else description="请选择左侧部门查看资产" />
      </div>
    </div>

    <!-- 资产认领对话框 -->
    <el-dialog v-model="claimVisible" title="资产认领" width="700px" @closed="claimSearchResult=[]">
      <el-input v-model="claimKeyword" placeholder="搜索 IP / MAC / VM 名称 / 域名" clearable @keyup.enter="handleClaimSearch">
        <template #append><el-button :icon="Search" @click="handleClaimSearch" :loading="claimSearching" /></template>
      </el-input>
      <el-table :data="claimSearchResult" stripe size="small" style="margin-top:12px" max-height="400" @selection-change="onClaimSelect">
        <el-table-column type="selection" width="40" />
        <el-table-column prop="asset_type" label="类型" width="60">
          <template #default="{ row }"><el-tag size="small">{{ row.asset_type === 'vm' ? 'VM' : '域名' }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="name" label="名称" min-width="160" show-overflow-tooltip />
        <el-table-column prop="ip_address" label="IP" width="140" />
        <el-table-column prop="department_name" label="当前部门" width="120" />
      </el-table>
      <template #footer>
        <el-button @click="claimVisible = false">取消</el-button>
        <el-button type="primary" :loading="claimSubmitting" :disabled="claimSelected.length === 0" @click="handleClaimSubmit">
          认领选中的 {{ claimSelected.length }} 项
        </el-button>
      </template>
    </el-dialog>

    <!-- 管理员指派对话框 -->
    <el-dialog v-model="assignVisible" title="管理员指派" width="700px" @closed="assignSearchResult=[]">
      <el-input v-model="assignKeyword" placeholder="搜索未关联资产..." clearable @keyup.enter="handleAssignSearch">
        <template #append><el-button :icon="Search" @click="handleAssignSearch" :loading="assignSearching" /></template>
      </el-input>
      <div style="margin-top:12px;display:flex;gap:10px">
        <el-tree-select v-model="assignDeptId" :data="deptTreeAll" :props="{label:'dwmc',value:'id',children:'children'}" placeholder="选择目标部门" clearable filterable check-strictly style="flex:1" />
        <el-select v-model="assignUserId" placeholder="搜索人员姓名" clearable filterable remote :remote-method="searchUsers" :loading="userSearching" style="width:200px">
          <el-option v-for="u in userOptions" :key="u.id" :label="`${u.name||''} - ${u.gh||''} (${u.department_name||''})`" :value="u.id" />
        </el-select>
      </div>
      <el-table :data="assignSearchResult" stripe size="small" style="margin-top:12px" max-height="300" @selection-change="onAssignSelect">
        <el-table-column type="selection" width="40" />
        <el-table-column prop="name" label="名称" min-width="160" show-overflow-tooltip />
        <el-table-column prop="ip_address" label="IP" width="140" />
        <el-table-column prop="vm_folder" label="文件夹" min-width="160" />
      </el-table>
      <template #footer>
        <el-button @click="assignVisible = false">取消</el-button>
        <el-button type="primary" :loading="assignSubmitting" :disabled="assignSelected.length === 0 || (!assignDeptId && !assignUserId)" @click="handleAssignSubmit">
          指派 {{ assignSelected.length }} 项
        </el-button>
      </template>
    </el-dialog>

    <!-- 自动关联预览 -->
    <el-dialog v-model="matchPreviewVisible" title="自动关联预览" width="800px">
      <div class="match-summary">
        共 {{ matchPreviewData.total_vms }} 个未关联 VM，
        <span style="color:#67c23a;font-weight:600">{{ matchPreviewData.matched_count }} 个可匹配</span>
      </div>
      <el-table :data="matchPreviewData.items" stripe size="small" max-height="400" style="margin-top:10px">
        <el-table-column prop="vm_name" label="VM 名称" width="160" />
        <el-table-column prop="vm_folder" label="文件夹路径" min-width="200" show-overflow-tooltip />
        <el-table-column prop="matched_segment" label="匹配片段" width="140" />
        <el-table-column prop="matched_dept_name" label="匹配部门" min-width="160" />
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, WarningFilled, OfficeBuilding } from '@element-plus/icons-vue'
import { useAuthStore } from '@/store/auth'
import { getDepartmentTree } from '@/api/departments'
import { getAssetTree, getDeptVMs, getDeptDomains, getVMFilters, searchAssets, previewAutoMatch, executeAutoMatch, startMatchOwner, statusMatchOwner, syncAssets, claimAssets, assignAssets, revokeAssets, resetAllAssets } from '@/api/assets'
import { getUsers } from '@/api/users'

const authStore = useAuthStore()
const treeRef = ref(null)
const treeFilter = ref('')
const treeData = ref([])
const deptTreeAll = ref([])
const selectedNode = ref(null)
const activeTab = ref('vms')
const hideEmpty = ref(true)

const vmList = ref([])
const vmLoading = ref(false)
const filterOptions = ref({ power_states: [], os_names: [], networks: [], folders: [] })
const vmSearch = ref('')
const vmClaimFilter = ref('')
const vmClaimedFilter = ref('')
const vmPowerFilter = ref('')
const vmOsFilter = ref('')
const vmNetFilter = ref('')
const vmFolderFilter = ref('')
const vmPage = ref(1)
const vmSize = ref(20)
const vmTotal = ref(0)

const domainList = ref([])
const domainLoading = ref(false)
const domainSearch = ref('')
const domainTypeFilter = ref('')
const domainPage = ref(1)
const domainSize = ref(50)
const domainTotal = ref(0)
const selectedDomains = ref([])
function onDomainSelect(val) { selectedDomains.value = val }

const claimVisible = ref(false)
const claimKeyword = ref('')
const claimSearching = ref(false)
const claimSearchResult = ref([])
const claimSelected = ref([])
const claimSubmitting = ref(false)

const selectedVMs = ref([])
function onVMSelect(val) { selectedVMs.value = val }

async function handleClaim() {
  const ids = selectedVMs.value.map(v => v.id).filter(Boolean)
  if (ids.length === 0) return ElMessage.warning('请选择 VM')
  try {
    const res = await claimAssets({ vm_ids: ids })
    ElMessage.success(res.message)
    await loadVMs(); await loadTree()
  } catch (e) { ElMessage.error(e.response?.data?.detail || '认领失败') }
}

async function handleRevoke() {
  const ids = selectedVMs.value.map(v => v.id).filter(Boolean)
  if (ids.length === 0) return ElMessage.warning('请选择 VM')
  try {
    await ElMessageBox.confirm('确定撤销选中资产的认领吗？', '撤销确认', { type: 'warning' })
    const res = await revokeAssets({ vm_ids: ids })
    ElMessage.success(res.message)
    await loadVMs(); await loadTree()
  } catch { /* 取消 */ }
}

const assignVisible = ref(false)
const assignKeyword = ref('')
const assignSearching = ref(false)
const assignSearchResult = ref([])
const assignSelected = ref([])
const assignSubmitting = ref(false)
const assignDeptId = ref(null)
const assignUserId = ref(null)
const userOptions = ref([])
const userSearching = ref(false)
async function searchUsers(query) {
  if (!query || query.length < 1) { userOptions.value = []; return }
  userSearching.value = true
  try {
    const res = await getUsers({ search: query, size: 20 })
    userOptions.value = res.items
  } catch { userOptions.value = [] } finally { userSearching.value = false }
}

const syncLoading = ref(false)
const autoMatchLoading = ref(false)
const ownerMatchLoading = ref(false)
const previewLoading = ref(false)
const matchPreviewVisible = ref(false)
const matchPreviewData = ref({ items: [], total_vms: 0, matched_count: 0 })

function statusLabel(s) {
  return s === 'auto' ? '自动' : s === 'manual' ? '手动' : '未关联'
}

function filterNode(value, data) {
  if (!value) return true
  return data.label.toLowerCase().includes(value.toLowerCase())
}

function filterTree() {
  treeRef.value?.filter(treeFilter.value)
}

async function loadTree() {
  try {
    const res = await getAssetTree()
    const nodes = (res.nodes || []).map(n => ({
      ...n,
      count: n.count,  // total for filtering
    }))
    if (hideEmpty.value) {
      function filterEmpty(list) {
        return list.filter(n => {
          if (n.children) n.children = filterEmpty(n.children)
          return n.count > 0 || (n.children && n.children.length > 0)
        })
      }
      treeData.value = filterEmpty(nodes)
    } else {
      treeData.value = nodes
    }
  } catch { /* 静默 */ }
}

async function fetchFilterOptions() {
  try { filterOptions.value = await getVMFilters() } catch { /* */ }
}

async function handleNodeClick(data) {
  selectedNode.value = data
  vmPage.value = 1
  vmSearch.value = ''
  vmPowerFilter.value = ''
  vmOsFilter.value = ''
  vmNetFilter.value = ''
  vmFolderFilter.value = ''
  domainSearch.value = ''
  domainTypeFilter.value = ''
  domainPage.value = 1
  await loadVMs()
  await loadDomains()
}

async function loadVMs() {
  if (!selectedNode.value) return
  vmLoading.value = true
  try {
    const deptId = selectedNode.value.id === -1 ? 0 : selectedNode.value.id
    const res = await getDeptVMs(deptId, {
      page: vmPage.value, size: vmSize.value, search: vmSearch.value,
      claim_status: vmClaimFilter.value, claimed: vmClaimedFilter.value,
      power_state: vmPowerFilter.value,
      os_name: vmOsFilter.value, network_name: vmNetFilter.value,
      vm_folder: vmFolderFilter.value,
    })
    vmList.value = res.items
    vmTotal.value = res.total
  } catch { vmList.value = [] } finally { vmLoading.value = false }
}

async function loadDomains() {
  if (!selectedNode.value) return
  domainLoading.value = true
  try {
    const deptId = selectedNode.value.id === -1 ? 0 : selectedNode.value.id
    const res = await getDeptDomains(deptId, {
      page: domainPage.value, size: domainSize.value,
      search: domainSearch.value, record_type: domainTypeFilter.value,
    })
    domainList.value = res.items
    domainTotal.value = res.total
  } catch { domainList.value = []; domainTotal.value = 0 } finally { domainLoading.value = false }
}

async function showMatchPreview() {
  previewLoading.value = true
  try {
    matchPreviewData.value = await previewAutoMatch()
    matchPreviewVisible.value = true
  } catch { ElMessage.error('加载预览失败') } finally { previewLoading.value = false }
}

async function handleResetAll() {
  try {
    await ElMessageBox.confirm(
      '确定要重置所有关联数据吗？此操作将清空所有虚拟机的部门归属、负责人和认领状态，且不可恢复！',
      '重置确认',
      { confirmButtonText: '确定重置', cancelButtonText: '取消', type: 'error' }
    )
    const res = await resetAllAssets()
    ElMessage.success(res.message)
    await loadTree()
    if (selectedNode.value) { await loadVMs(); await loadDomains() }
  } catch { /* 取消 */ }
}

let pollTimer = null
onBeforeUnmount(() => { if (pollTimer) clearInterval(pollTimer) })

async function handleMatchOwner() {
  ownerMatchLoading.value = true
  try {
    const start = await startMatchOwner()
    if (!start.running) { ElMessage.warning(start.message); return }
    ElMessage.info(start.message)
    pollTimer = setInterval(async () => {
      const st = await statusMatchOwner()
      if (!st.running) {
        clearInterval(pollTimer)
        pollTimer = null
        ownerMatchLoading.value = false
        ElMessage.success(st.message)
        await loadTree()
        if (selectedNode.value) { await loadVMs() }
      }
    }, 2000)
  } catch (e) {
    ownerMatchLoading.value = false
    ElMessage.error('启动任务失败：' + (e?.response?.data?.detail || e?.message || ''))
  }
}

async function handleSync() {
  syncLoading.value = true
  try {
    const res = await syncAssets()
    ElMessage.success(res.message)
    await loadTree()
  } catch { ElMessage.error('同步失败') } finally { syncLoading.value = false }
}

async function handleAutoMatch() {
  autoMatchLoading.value = true
  try {
    const res = await executeAutoMatch()
    ElMessage.success(`自动关联完成：${res.total_vms} 个 VM，匹配 ${res.matched}，失败 ${res.failed}`)
    await loadTree()
    if (selectedNode.value) { await loadVMs(); await loadDomains() }
  } catch { ElMessage.error('自动关联失败') } finally { autoMatchLoading.value = false }
}

function showClaimDialog() {
  claimKeyword.value = ''
  claimSearchResult.value = []
  claimSelected.value = []
  claimVisible.value = true
}

async function handleClaimSearch() {
  if (!claimKeyword.value.trim()) return
  claimSearching.value = true
  try {
    const res = await searchAssets(claimKeyword.value)
    claimSearchResult.value = res.items.filter(i => i.asset_type === 'vm')
  } catch { claimSearchResult.value = [] } finally { claimSearching.value = false }
}

function onClaimSelect(val) { claimSelected.value = val }

async function handleClaimSubmit() {
  const vmIds = claimSelected.value
    .filter(i => i.asset_type === 'vm' && i.id)
    .map(i => i.id)
  if (vmIds.length === 0) { ElMessage.warning('请选择 VM 资产'); return }
  claimSubmitting.value = true
  try {
    const res = await claimAssets({ vm_ids: vmIds })
    ElMessage.success(res.message)
    claimVisible.value = false
    await loadTree()
    if (selectedNode.value) { await loadVMs(); await loadDomains() }
  } catch (e) { ElMessage.error(e.response?.data?.detail || '认领失败') } finally { claimSubmitting.value = false }
}

async function showAssignDialog(preSelected = []) {
  assignKeyword.value = ''
  assignSearchResult.value = []
  assignSelected.value = []
  assignDeptId.value = null
  assignUserId.value = null
  // 如果从表格选中带入，预填搜索结果
  if (preSelected.length > 0) {
    assignSearchResult.value = preSelected.map(v => ({
      asset_type: 'vm', id: v.id, name: v.vm_name,
      ip_address: v.ip_address, vm_folder: v.vm_folder,
    }))
  }
  // 加载部门和用户选项
  try {
    deptTreeAll.value = await getDepartmentTree(true)
    userOptions.value = []
  } catch { /* 静默 */ }
  assignVisible.value = true
}

async function handleAssignSearch() {
  if (!assignKeyword.value.trim()) return
  assignSearching.value = true
  try {
    const res = await searchAssets(assignKeyword.value)
    assignSearchResult.value = res.items.filter(i => i.asset_type === 'vm')
  } catch { assignSearchResult.value = [] } finally { assignSearching.value = false }
}

function onAssignSelect(val) { assignSelected.value = val }

async function handleAssignSubmit() {
  const vmIds = assignSelected.value
    .filter(i => i.asset_type === 'vm' && i.id)
    .map(i => i.id)
  if (vmIds.length === 0) { ElMessage.warning('请选择 VM 资产'); return }
  assignSubmitting.value = true
  try {
    const res = await assignAssets({ vm_ids: vmIds, department_id: assignDeptId.value || null, user_id: assignUserId.value || null })
    ElMessage.success(res.message)
    assignVisible.value = false
    await loadTree()
    if (selectedNode.value) { await loadVMs(); await loadDomains() }
  } catch (e) { ElMessage.error(e.response?.data?.detail || '指派失败') } finally { assignSubmitting.value = false }
}

function assignDomains() {
  // 用选中的域名打开指派对话框
  const items = selectedDomains.value.map(d => ({
    asset_type: 'domain', id: null, name: d.domain_name,
    ip_address: d.ip_address, vm_folder: '',
  }))
  assignSearchResult.value = items
  assignDeptId.value = null
  assignUserId.value = null
  assignSelected.value = []
  userOptions.value = []
  try { getDepartmentTree(true).then(t => { deptTreeAll.value = t }) } catch { /* */ }
  assignVisible.value = true
}

async function revokeDomains() {
  if (selectedDomains.value.length === 0) return ElMessage.warning('请选择域名')
  try {
    await ElMessageBox.confirm('确定撤销选中域名的认领吗？注意：域名关联到VM，撤销将清空对应VM的负责人。', '撤销确认', { type: 'warning' })
    // 通过域名关联的 VM 来撤销
    const vmIds = [...new Set(selectedDomains.value.map(d => d.vm_id).filter(Boolean))]
    if (vmIds.length === 0) return ElMessage.warning('选中的域名没有关联 VM')
    const res = await revokeAssets({ vm_ids: vmIds })
    ElMessage.success(res.message)
    await loadDomains(); await loadTree()
  } catch { /* 取消 */ }
}

onMounted(async () => {
  await loadTree()
  await fetchFilterOptions()
})
</script>

<style scoped>
.asset-page { padding: 20px; height: calc(100vh - 100px); display: flex; flex-direction: column; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; flex-wrap: wrap; gap: 8px; }
.page-header h2 { margin: 0; font-size: 20px; }
.header-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.asset-content { display: flex; gap: 16px; flex: 1; overflow: hidden; }
.tree-panel { width: 300px; flex-shrink: 0; border: 1px solid #e4e7ed; border-radius: 6px; padding: 10px; overflow-y: auto; background: #fff; }
.detail-panel { flex: 1; border: 1px solid #e4e7ed; border-radius: 6px; padding: 16px; overflow-y: auto; background: #fff; }
.detail-header h3 { margin: 0 0 12px 0; font-size: 17px; }
.tree-node { display: flex; align-items: center; gap: 6px; flex: 1; }
.node-label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.node-stats { margin-left: auto; font-size: 10px; display: flex; gap: 4px; white-space: nowrap; }
.stat-v { color: #409eff; }
.stat-d { color: #67c23a; }
.stat-s { color: #909399; }
.filter-bar { display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; align-items: center; }
.total-info { font-size: 12px; color: #909399; margin-bottom: 6px; }
.match-summary { font-size: 14px; padding: 8px 0; }
</style>
