<template>
  <div class="page">
    <div class="page-header">
      <h2>资产关联</h2>
      <p class="page-desc">将域名 / 虚拟机 / F5 / 备份 / 椒图等资产关联到信息系统，标注组件角色</p>
    </div>

    <el-row :gutter="16" style="flex:1;min-height:0">
      <!-- 左侧：信息系统列表 -->
      <el-col :span="8">
        <el-card shadow="hover" class="sys-panel">
          <template #header><strong>信息系统</strong></template>
          <div class="sys-filter-row">
            <el-input v-model="sysSearch" placeholder="搜索系统名称..." clearable size="small" style="flex:1" @change="fetchSystems" />
            <el-input v-model="sysManager" placeholder="管理员" clearable size="small" style="width:100px" @change="fetchSystems" />
          </div>
          <div class="sys-list">
            <div v-for="s in filteredSystems" :key="s.id" class="sys-item" :class="{ active: selectedSystem?.id === s.id }" @click="selectSystem(s)">
              <span class="sys-name">{{ s.system_name }}</span>
              <span class="sys-manager" :title="s.manager_name">{{ s.manager_name || '-' }}</span>
              <el-tag size="small">{{ s.asset_count }} 资产</el-tag>
            </div>
            <el-empty v-if="filteredSystems.length===0" description="暂无系统" :image-size="50" />
          </div>
        </el-card>
      </el-col>

      <!-- 右侧：已关联资产 -->
      <el-col :span="16">
        <el-card shadow="hover" class="asset-panel" v-if="selectedSystem">
          <template #header>
            <div class="asset-header">
              <strong>{{ selectedSystem.system_name }} — 关联资产</strong>
              <div class="asset-header-btns">
                <el-button type="success" size="small" :loading="autoLinking" @click="autoLink">自动关联</el-button>
                <el-button type="primary" size="small" @click="showAddDialog = true">添加资产</el-button>
                <el-button type="danger" size="small" :disabled="assets.length===0" @click="clearAll">全部清除</el-button>
              </div>
            </div>
          </template>

          <el-table :data="assets" stripe size="small" v-loading="loadingAssets">
            <el-table-column prop="asset_type" label="类型" width="90">
              <template #default="{row}">{{ typeLabel(row.asset_type) }}</template>
            </el-table-column>
            <el-table-column prop="asset_key" label="资产标识" min-width="140" show-overflow-tooltip />
            <el-table-column prop="asset_ip" label="IP" width="140" show-overflow-tooltip />
            <el-table-column prop="asset_label" label="角色" width="90">
              <template #default="{row}">
                <el-tag size="small" :type="labelColor(row.asset_label)">{{ row.asset_label || '未标注' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="130">
              <template #default="{row}">
                <div class="status-cell">
                  <el-tag :type="row.status==='up'?'success':row.status==='down'?'danger':'info'" size="small">{{ row.status_label || '未知' }}</el-tag>
                  <!-- VM 显示备份和椒图状态 -->
                  <span v-if="row.asset_type==='vm'" class="status-extra">
                    <el-tag :type="row.backup_status==='up'?'success':row.backup_status==='warning'?'warning':row.backup_status==='remind'?'warning':row.backup_status==='down'?'danger':'info'" size="small">{{ row.backup_label }}</el-tag>
                    <el-tag :type="row.qax_status==='up'?'success':row.qax_status==='down'?'danger':'info'" size="small" style="margin-top:2px">{{ row.qax_label }}</el-tag>
                  </span>
                  <span v-else-if="row.status_detail" class="status-extra">{{ row.status_detail }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="notes" label="备注" min-width="100" show-overflow-tooltip />
            <el-table-column label="操作" width="100">
              <template #default="{row}">
                <el-tooltip content="编辑"><el-button link type="primary" :icon="Edit" size="small" @click="openEdit(row)" /></el-tooltip>
                <el-tooltip content="移除"><el-button link type="danger" :icon="Delete" size="small" @click="unlink(row)" /></el-tooltip>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
        <el-empty v-else description="请选择左侧信息系统" :image-size="80" />
      </el-col>
    </el-row>

    <!-- 添加资产对话框 -->
    <el-dialog v-model="showAddDialog" title="添加资产关联" width="1100px" top="2vh" @closed="resetAdd">
      <el-form label-width="70px" inline style="margin-bottom:10px">
        <el-form-item label="资产类型">
          <el-select v-model="addAssetType" placeholder="选择类型" @change="onAssetTypeChange" style="width:120px">
            <el-option v-for="t in assetTypes" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="搜索">
          <el-input v-model="addSearch" :placeholder="addAssetType==='vm'?'搜索名称/IP/备注...':'输入关键词搜索...'" style="width:200px" clearable @keyup.enter="assetPage=1;searchAssets()" @clear="assetPage=1;searchAssets()" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="addLabel" placeholder="选择角色" style="width:110px">
            <el-option v-for="l in labels" :key="l" :label="l" :value="l" />
          </el-select>
        </el-form-item>
      </el-form>

      <!-- VM 文件夹树 -->
      <el-row :gutter="12" v-if="addAssetType==='vm'" style="height:420px;overflow:hidden">
        <el-col :span="7" style="height:100%;overflow:hidden">
          <div class="vm-folder-tree">
            <el-input v-model="vmTreeSearch" placeholder="搜索文件夹..." clearable size="small" style="margin-bottom:6px" @input="(v)=>vmTreeRef?.filter(v)" />
            <el-tree
              ref="vmTreeRef"
              :data="vmFolders"
              :props="{ children: 'children', label: 'label' }"
              node-key="path"
              default-expand-all
              highlight-current
              :filter-node-method="(v,d)=>d.label.toLowerCase().includes(v.toLowerCase())"
              @node-click="handleFolderClick"
              size="small"
            >
              <template #default="{ data }">
                <span class="folder-node">
                  <el-icon><Folder /></el-icon>
                  <span>{{ data.label }}</span>
                  <span class="folder-count">{{ data.count }}</span>
                </span>
              </template>
            </el-tree>
          </div>
        </el-col>
        <el-col :span="17">
          <el-table :data="searchResults" stripe size="small" v-loading="searching" max-height="400" @selection-change="onVMSelect">
            <el-table-column type="selection" width="35" />
            <el-table-column prop="name" label="名称" width="160" show-overflow-tooltip />
            <el-table-column prop="ip" label="IP" width="140" />
            <el-table-column prop="extra" label="电源" width="50" align="center">
              <template #default="{row}"><el-tag :type="row.extra==='poweredOn'?'success':'info'" size="small">{{ row.extra==='poweredOn'?'开':'关' }}</el-tag></template>
            </el-table-column>
            <el-table-column label="角色提示" width="80" align="center">
              <template #default="{row}">
                <el-tag v-if="row.role_hint" size="small" type="warning" style="cursor:pointer" @click="addLabel=row.role_hint">{{ row.role_hint }}</el-tag>
                <span v-else class="text-muted">—</span>
              </template>
            </el-table-column>
            <el-table-column prop="remark" label="备注" min-width="100" show-overflow-tooltip />
          </el-table>
          <el-pagination v-if="assetTotal>addSize" v-model:current-page="assetPage" :page-size="addSize" :total="assetTotal" layout="prev,pager,next" small @current-change="searchAssets" style="justify-content:center;margin-top:6px" />
        </el-col>
      </el-row>

      <!-- 其他类型：普通搜索表格 -->
      <template v-else>
        <el-table :data="searchResults" stripe size="small" v-loading="searching" max-height="300" @selection-change="onAssetSelect">
          <el-table-column type="selection" width="40" />
          <el-table-column prop="name" label="名称" min-width="180" show-overflow-tooltip />
          <el-table-column prop="ip" label="IP" width="150" />
          <el-table-column prop="extra" label="补充信息" width="120" />
        </el-table>
        <el-pagination v-if="assetTotal>addSize" v-model:current-page="assetPage" :page-size="addSize" :total="assetTotal" layout="prev,pager,next" small @current-change="searchAssets" style="justify-content:center;margin-top:10px" />
      </template>

      <template #footer>
        <el-button @click="showAddDialog=false">取消</el-button>
        <el-button type="primary" @click="doLink" :disabled="selectedAssets.length===0">关联选中 ({{ selectedAssets.length }})</el-button>
      </template>
    </el-dialog>

    <!-- 编辑资产对话框 -->
    <el-dialog v-model="showEditDialog" title="编辑资产关联" width="500px">
      <el-form label-width="80px" v-if="editRow">
        <el-form-item label="资产"><span>{{ editRow.asset_key }}</span></el-form-item>
        <el-form-item label="类型"><el-tag size="small">{{ typeLabel(editRow.asset_type) }}</el-tag></el-form-item>
        <el-form-item label="角色">
          <el-select v-model="editLabel" placeholder="选择角色">
            <el-option v-for="l in labels" :key="l" :label="l" :value="l" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="editNotes" placeholder="备注信息" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog=false">取消</el-button>
        <el-button type="primary" @click="doEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Edit, Delete } from '@element-plus/icons-vue'
import api from '@/api/index'

const sysList = ref([])
const sysSearch = ref('')
const sysManager = ref('')
const selectedSystem = ref(null)
const assets = ref([])
const loadingAssets = ref(false)

const filteredSystems = computed(() => {
  if (!sysSearch.value) return sysList.value
  const q = sysSearch.value.toLowerCase()
  return sysList.value.filter(s => s.system_name.toLowerCase().includes(q))
})

const assetTypes = [
  { value: 'domain', label: '域名' }, { value: 'vm', label: '虚拟机' },
  { value: 'f5_vs', label: 'F5 VS' }, { value: 'f5_member', label: 'F5 成员' },
  { value: 'backup', label: '备份' }, { value: 'qax', label: '椒图' },
]
const labels = ['前端', '中间件', '数据库', '负载均衡', '存储', '安全', '备份', '监控', '其他']

const showAddDialog = ref(false)
const addAssetType = ref('domain')
const addSearch = ref('')
const addLabel = ref('')
const addNotes = ref('')
const searchResults = ref([])
const searching = ref(false)
const selectedAssets = ref([])
const assetPage = ref(1), addSize = ref(30), assetTotal = ref(0)
const vmFolders = ref([])
const vmFolderFilter = ref('')
const vmTreeRef = ref(null)
const vmTreeSearch = ref('')
const vmTotalCount = ref(0)

function handleFolderClick(data) {
  vmFolderFilter.value = data.path || ''
  assetPage.value = 1
  searchAssets()
}

async function onAssetTypeChange() {
  assetPage.value = 1
  vmFolderFilter.value = ''
  if (addAssetType.value === 'vm') {
    try {
      const { data } = await api.get('/monitor/vm-folders')
      vmFolders.value = data.folders || []
      vmTotalCount.value = vmFolders.value.reduce((s, f) => s + f.count, 0)
    } catch {}
  }
  searchAssets()
}

function typeLabel(t) {
  const m = { domain:'域名', vm:'虚拟机', f5_vs:'F5 VS', f5_member:'F5成员', backup:'备份', qax:'椒图' }
  return m[t] || t
}
function labelColor(l) {
  const m = { '前端':'', '中间件':'success', '数据库':'warning', '负载均衡':'primary', '存储':'info', '安全':'danger', '备份':'' }
  return m[l] || 'info'
}

async function fetchSystems() {
  const { data } = await api.get('/monitor/systems', {
    params: { search: sysSearch.value, manager: sysManager.value }
  })
  sysList.value = data.items || []
}
async function selectSystem(s) {
  selectedSystem.value = s
  loadingAssets.value = true
  try {
    const { data } = await api.get(`/monitor/systems/${s.id}/assets`)
    assets.value = data.items || []
  } catch {} finally { loadingAssets.value = false }
}

const autoLinking = ref(false)
async function autoLink() {
  if (!selectedSystem.value) return
  autoLinking.value = true
  try {
    const { data } = await api.post(`/monitor/systems/${selectedSystem.value.id}/auto-link`)
    ElMessage.success(data.message)
    selectSystem(selectedSystem.value)
  } catch {} finally { autoLinking.value = false }
}
async function searchAssets() {
  searching.value = true
  try {
    const params = { asset_type: addAssetType.value, search: addSearch.value, page: assetPage.value, size: addSize.value }
    if (addAssetType.value === 'vm' && vmFolderFilter.value) {
      params.folder = vmFolderFilter.value
    }
    const { data } = await api.get('/monitor/search-assets', { params })
    searchResults.value = data.items || []
    assetTotal.value = data.total || 0
  } catch {} finally { searching.value = false }
}
function onAssetSelect(v) { selectedAssets.value = v }
function onVMSelect(v) {
  selectedAssets.value = v
  // 自动设置角色：取第一个有role_hint的VM的建议
  if (v.length === 1 && v[0].role_hint) {
    addLabel.value = v[0].role_hint
  }
}
function resetAdd() { addSearch.value=''; addLabel.value=''; addNotes.value=''; searchResults.value=[]; selectedAssets.value=[] }
async function doLink() {
  if (!selectedSystem.value || selectedAssets.value.length===0) return
  const body = { assets: selectedAssets.value.map(a => ({
    asset_type: addAssetType.value,
    asset_key: a.key,
    asset_label: a.role_hint || addLabel.value,
    notes: a.remark || addNotes.value,
  }))}
  try {
    const { data } = await api.post(`/monitor/systems/${selectedSystem.value.id}/assets`, body)
    ElMessage.success(data.message)
    showAddDialog.value = false
    selectSystem(selectedSystem.value)
  } catch {}
}
async function clearAll() {
  await ElMessageBox.confirm(
    `确认删除「${selectedSystem.value.system_name}」下的全部 ${assets.value.length} 个关联资产？此操作不可恢复！`,
    '全部清除',
    { type: 'error', confirmButtonText: '确认删除', cancelButtonText: '取消' }
  )
  try {
    await api.delete(`/monitor/systems/${selectedSystem.value.id}/assets`)
    ElMessage.success('已全部清除')
    selectSystem(selectedSystem.value)
  } catch {}
}

async function unlink(row) {
  await ElMessageBox.confirm(`确认移除 ${row.asset_key}？`, '取消关联', { type: 'warning' })
  try {
    await api.delete(`/monitor/assets/${row.id}`)
    ElMessage.success('已移除')
    selectSystem(selectedSystem.value)
  } catch {}
}

// 编辑
const showEditDialog = ref(false)
const editRow = ref(null)
const editLabel = ref('')
const editNotes = ref('')
function openEdit(row) {
  editRow.value = row
  editLabel.value = row.asset_label || ''
  editNotes.value = row.notes || ''
  showEditDialog.value = true
}
async function doEdit() {
  if (!editRow.value) return
  try {
    await api.put(`/monitor/assets/${editRow.value.id}`, {
      asset_label: editLabel.value,
      notes: editNotes.value,
    })
    ElMessage.success('已更新')
    showEditDialog.value = false
    selectSystem(selectedSystem.value)
  } catch {}
}

onMounted(fetchSystems)
</script>

<style scoped>
.page { padding: 20px; display: flex; flex-direction: column; height: calc(100vh - 60px); }
.page-header h2 { margin: 0; font-size: 20px; }
.page-desc { margin: 4px 0 16px; font-size: 13px; color: var(--color-text-muted); }

.sys-panel { height: 100%; }
.sys-filter-row { display: flex; gap: 8px; margin-bottom: 8px; }
.sys-list { max-height: calc(100vh - 260px); overflow-y: auto; }
.sys-item { display: flex; align-items: center; gap: 8px; padding: 10px 12px; cursor: pointer; border-radius: 6px; margin-bottom: 4px; transition: background .15s; }
.sys-item:hover { background: var(--color-bg); }
.sys-item.active { background: var(--color-primary-light-9, #ecf5ff); }
.sys-name { font-size: 14px; color: var(--color-text); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sys-manager { font-size: 12px; color: var(--color-text-muted); white-space: nowrap; max-width: 80px; overflow: hidden; text-overflow: ellipsis; }

.asset-panel { height: 100%; }
.asset-header { display: flex; justify-content: space-between; align-items: center; }
.asset-header-btns { display: flex; gap: 8px; }

.vm-folder-tree { border: 1px solid var(--color-border); border-radius: 6px; padding: 8px; height: 100%; }
.vm-folder-tree .el-tree { max-height: 340px; overflow-y: auto; }
.folder-node { display: flex; align-items: center; gap: 6px; font-size: 13px; }
.folder-count { font-size: 11px; color: var(--color-text-muted); margin-left: 4px; }
.status-cell { display: flex; flex-direction: column; gap: 2px; }
.status-extra { font-size: 11px; color: var(--color-text-muted); }
</style>
