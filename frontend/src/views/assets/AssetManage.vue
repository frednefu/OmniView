<template>
  <div class="asset-page">
    <div class="page-header">
      <h2>信息资产管理</h2>
      <div class="header-right">
        <el-switch v-model="hideEmpty" active-text="隐藏空部门" @change="loadTree" />
        <template v-if="authStore.isAdmin">
          <el-button type="info" plain @click="handleSync" :loading="syncLoading">同步资产</el-button>
          <el-button @click="showMatchPreview" :loading="previewLoading">分组预览</el-button>
          <el-button type="primary" @click="handleAutoMatch" :loading="autoMatchLoading">自动分组</el-button>
          <el-button type="success" plain @click="handleMatchOwner" :loading="ownerMatchLoading">匹配负责人</el-button>
          <el-button v-if="selectedVMs.length > 0" type="warning" @click="showAssignDialog(selectedVMs)">指派选中 ({{ selectedVMs.length }})</el-button>
        </template>
      </div>
    </div>

    <div class="asset-content">
      <!-- 左侧部门树 -->
      <div class="tree-panel" :style="{ width: treeWidth + 'px' }">
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

      <!-- 拖拽分隔条 -->
      <div class="tree-resizer" @mousedown="startResize"></div>

      <!-- 右侧资产面板 -->
      <div class="detail-panel">
        <template v-if="selectedNode">
          <div class="detail-header">
            <h3>{{ selectedNode.full_name || selectedNode.label }}</h3>
          </div>
          <el-tabs v-model="activeTab">
            <template #extra>
              <el-switch v-if="activeTab==='vms'" v-model="hideEmptyFolder" size="small" active-text="隐藏空" @change="rebuildFolderTree" style="margin-right:8px" />
            </template>
            <el-tab-pane label="虚拟机清单" name="vms">
              <div class="vm-split">
                <!-- VM 清单内左侧：文件夹树 -->
                <div class="vm-folder-tree">
                  <el-input v-model="folderTreeFilter" placeholder="搜索文件夹..." clearable size="small" style="margin-bottom:6px" @input="(v)=>folderTreeRef?.filter(v)" />
                  <el-tree
                    ref="folderTreeRef"
                    :data="folderTree"
                    :props="{ children: 'children', label: 'label' }"
                    node-key="id"
                    default-expand-all
                    highlight-current
                    :filter-node-method="(v,d)=>d.label.toLowerCase().includes(v.toLowerCase())"
                    @node-click="handleFolderClick"
                    size="small"
                  >
                    <template #default="{ data }">
                      <span class="folder-node">
                        <el-icon v-if="data.id==='root'"><FolderOpened /></el-icon>
                        <el-icon v-else><Folder /></el-icon>
                        <span>{{ data.label }}</span>
                      </span>
                    </template>
                  </el-tree>
                </div>
                <!-- VM 清单内右侧：表格 -->
                <div class="vm-table-wrap">
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
                <el-select v-model="vmQaxFilter" placeholder="安全" clearable size="small" style="width:80px" @change="vmPage=1;loadVMs()">
                  <el-option label="是" value="yes"/><el-option label="否" value="no"/>
                </el-select>
                <el-select v-model="vmBackupFilter" placeholder="备份" clearable size="small" style="width:80px" @change="vmPage=1;loadVMs()">
                  <el-option label="是" value="yes"/><el-option label="否" value="no"/>
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
                <el-button type="primary" size="small" @click="vmPage=1;loadVMs()">查询</el-button>
                <el-button type="success" size="small" :disabled="selectedVMs.length===0" @click="handleClaim">认领资产</el-button>
                <el-button type="warning" size="small" :disabled="selectedVMs.length===0" @click="handleRevoke">撤销认领</el-button>
              </div>
              <div class="total-info">共 {{ vmTotal }} 条，已选 {{ selectedVMs.length }} 条</div>
              <el-table :data="vmList" v-loading="vmLoading" stripe size="small" max-height="calc(100vh - 400px)" @selection-change="onVMSelect" @sort-change="onVMSort" :default-sort="{prop:'resource_pool',order:'ascending'}">
                <el-table-column type="selection" width="35" />
                <el-table-column prop="vm_name" label="名称" width="150" show-overflow-tooltip sortable="custom" />
                <el-table-column prop="power_state" label="电源" width="65" sortable="custom">
                  <template #default="{ row }">
                    <el-tag :type="row.power_state === 'poweredOn' ? 'success' : 'info'" size="small">{{ row.power_state === 'poweredOn' ? '开' : '关' }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="provisioned_gb" label="置备空间" width="80" sortable="custom">
                  <template #default="{ row }">{{ row.provisioned_gb ? row.provisioned_gb + 'G' : '-' }}</template>
                </el-table-column>
                <el-table-column prop="used_gb" label="已用空间" width="80" sortable="custom">
                  <template #default="{ row }">{{ row.used_gb ? row.used_gb + 'G' : '-' }}</template>
                </el-table-column>
                <el-table-column prop="cpu_count" label="CPU" width="50" sortable="custom" />
                <el-table-column prop="memory_gb" label="内存" width="55" sortable="custom">
                  <template #default="{ row }">{{ row.memory_gb ? row.memory_gb + 'G' : '-' }}</template>
                </el-table-column>
                <el-table-column prop="os_name" label="操作系统" min-width="130" show-overflow-tooltip />
                <el-table-column prop="ip_address" label="IP" width="130" show-overflow-tooltip />
                <el-table-column prop="mac_address" label="MAC" width="130" show-overflow-tooltip />
                <el-table-column prop="vcenter_name" label="vCenter" width="100" show-overflow-tooltip />
                <el-table-column prop="resource_pool" label="资源池" width="100" show-overflow-tooltip sortable="custom" />
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
                <el-table-column label="安全" width="60">
                  <template #default="{ row }">
                    <el-tag :type="row.has_qax ? 'success' : 'info'" size="small">{{ row.has_qax ? '是' : '否' }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="备份" width="120">
                  <template #default="{ row }">
                    <template v-if="row.has_backup">
                      <el-tag :type="isBackupStale(row.last_backup_time) ? 'warning' : 'success'" size="small">
                        是
                      </el-tag>
                      <span v-if="row.last_backup_time" style="font-size:10px;color:#909399;margin-left:2px">{{ formatDate(row.last_backup_time) }}</span>
                    </template>
                    <el-tag v-else type="info" size="small">否</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="owner_name" label="管理员" width="80" />
              </el-table>
              <el-pagination
                v-if="vmTotal>0"
                v-model:current-page="vmPage"
                v-model:page-size="vmSize"
                :page-sizes="[10,20,50,100]"
                :total="vmTotal"
                layout="total,sizes,prev,pager,next"
                @current-change="loadVMs"
                @size-change="loadVMs"
                style="justify-content:center;margin-top:16px"
              />
                </div><!-- .vm-table-wrap -->
              </div><!-- .vm-split -->
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
                <el-table-column label="数据关联" min-width="160" show-overflow-tooltip>
                  <template #default="{row}">
                    <span>{{ row.vm_name || row.domain_name || '-' }}</span>
                    <el-tag size="small" :type="row.source_type==='is'?'warning':''" style="margin-left:4px">{{ row.source_type === 'is' ? '信息系统' : row.source_type === 'vm' ? 'VM' : '' }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="dept_name" label="单位信息" width="120" show-overflow-tooltip />
                <el-table-column prop="owner_name" label="管理员" width="80" />
                <el-table-column label="认领" width="65">
                  <template #default="{ row }">
                    <el-tag :type="row.owner_name ? '' : 'info'" size="small">{{ row.owner_name ? '已认领' : '未认领' }}</el-tag>
                  </template>
                </el-table-column>
              </el-table>
              <el-pagination
                v-if="domainTotal>0"
                v-model:current-page="domainPage"
                v-model:page-size="domainSize"
                :page-sizes="[10,20,50,100]"
                :total="domainTotal"
                layout="total,sizes,prev,pager,next"
                @current-change="loadDomains"
                @size-change="loadDomains"
                style="justify-content:center;margin-top:16px"
              />
            </el-tab-pane>

            <el-tab-pane label="信息系统" name="systems">
              <div class="filter-bar">
                <el-input v-model="sysSearch" placeholder="搜索名称/IP/域名" clearable size="small" style="width:260px" @keyup.enter="sysPage=1;loadSystems()" @clear="sysPage=1;loadSystems()" />
                <el-button type="primary" size="small" @click="sysPage=1;loadSystems()">查询</el-button>
              </div>
              <div class="total-info">共 {{ sysTotal }} 条</div>
              <el-table :data="sysList" v-loading="sysLoading" stripe size="small" max-height="calc(100vh - 400px)">
                <el-table-column prop="system_name" label="系统名称" min-width="160" show-overflow-tooltip />
                <el-table-column prop="system_type" label="资产类型" width="120" />
                <el-table-column prop="sub_type" label="信息系统类型" width="140" show-overflow-tooltip />
                <el-table-column prop="dept_name" label="所属部门" width="120" show-overflow-tooltip />
                <el-table-column prop="ip_address" label="IP地址" width="130" show-overflow-tooltip />
                <el-table-column prop="domain" label="域名" min-width="150" show-overflow-tooltip />
                <el-table-column prop="manager_name" label="管理员" width="80" />
                <el-table-column prop="owner_name" label="负责人" width="80" />
                <el-table-column prop="fill_type" label="填报状态" width="90">
                  <template #default="{row}"><el-tag :type="row.fill_type==='自动'?'success':row.fill_type==='注销'?'danger':''" size="small">{{ row.fill_type||'手动' }}</el-tag></template>
                </el-table-column>
                <el-table-column prop="djdj_status" label="等保状态" width="90" />
              </el-table>
              <el-pagination
                v-if="sysTotal>0"
                v-model:current-page="sysPage" v-model:page-size="sysSize"
                :page-sizes="[10,20,50,100]" :total="sysTotal"
                layout="total,sizes,prev,pager,next"
                @current-change="loadSystems" @size-change="loadSystems"
                style="justify-content:center;margin-top:16px"
              />
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
        <el-tree-select v-model="assignDeptId" :data="deptTreeAll" :props="{label:'dwmc',value:'id',children:'children'}" placeholder="选择目标部门" clearable filterable check-strictly style="flex:1" @change="onAssignDeptChange" />
        <el-select v-model="assignUserId" placeholder="搜索人员姓名" clearable filterable remote :remote-method="searchUsers" :loading="userSearching" style="width:200px" @change="onAssignUserChange">
          <el-option v-for="u in userOptions" :key="u.id" :label="`${u.name||u.username} - ${u.gh||''} (${u.department_name||''})`" :value="u.id" />
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
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, WarningFilled, OfficeBuilding, Folder, FolderOpened } from '@element-plus/icons-vue'
import { useAuthStore } from '@/store/auth'
import { getDepartmentTree } from '@/api/departments'
import { getAssetTree, getDeptVMs, getDeptDomains, getVMFilters, searchAssets, previewAutoMatch, executeAutoMatch, startMatchOwner, statusMatchOwner, syncAssets, claimAssets, assignAssets, revokeAssets, resetAllAssets } from '@/api/assets'
import api from '@/api/index'
import { getUsers } from '@/api/users'

const authStore = useAuthStore()
// 左侧树宽度 — 用户级持久化
const treeWidth = ref(parseInt(localStorage.getItem('assetTreeWidth_' + (authStore.user?.id || 0))) || 300)
function saveTreeWidth() { localStorage.setItem('assetTreeWidth_' + (authStore.user?.id || 0), treeWidth.value) }
let resizing = false
function startResize(e) { resizing = true; document.addEventListener('mousemove', onResize); document.addEventListener('mouseup', stopResize); e.preventDefault() }
function onResize(e) { if (!resizing) return; const w = Math.max(200, Math.min(500, e.clientX - 60)); treeWidth.value = w }
function stopResize() { resizing = false; saveTreeWidth(); document.removeEventListener('mousemove', onResize); document.removeEventListener('mouseup', stopResize) }

const treeRef = ref(null)
const treeFilter = ref('')
const folderTreeFilter = ref('')
const folderTreeRef = ref(null)
const treeData = ref([])
const deptTreeAll = ref([])
const selectedNode = ref(null)
const activeTab = ref('vms')
const hideEmpty = ref(true)
const hideEmptyFolder = ref(true)

// 文件夹树
const folderTree = ref([])
const allFolders = ref([])  // 所有唯一文件夹路径

function buildFolderTree(folders) {
  // 解析文件夹路径: "303/数建处/8000/8900/iNEFU/零代码"
  const SEP = '/'
  const root = { id: 'root', label: '全部虚拟机', children: [] }
  const nodeMap = {}  // path → node

  // 统计每个路径节点下的 VM 数量
  const vmCount = {}  // path → count
  for (const f of folders) {
    if (!f) continue
    const parts = f.split(SEP)
    if (parts.length < 1) continue
    let acc = ''
    for (let i = 0; i < parts.length; i++) {
      const seg = parts[i].trim()
      if (!seg) continue
      acc = acc ? acc + SEP + seg : seg
      vmCount[acc] = (vmCount[acc] || 0) + 1
    }
  }

  // 构建树
  for (const f of folders) {
    if (!f) continue
    const parts = f.split(SEP)
    if (parts.length < 1) continue
    let parentPath = 'root'
    let currentPath = ''

    for (let i = 0; i < parts.length; i++) {
      const seg = parts[i].trim()
      if (!seg) continue
      currentPath = currentPath ? currentPath + SEP + seg : seg

      if (!nodeMap[currentPath]) {
        const node = { id: currentPath, label: seg, children: [], vmCount: vmCount[currentPath] || 0 }
        nodeMap[currentPath] = node
        if (parentPath === 'root') {
          root.children.push(node)
        } else if (nodeMap[parentPath]) {
          nodeMap[parentPath].children.push(node)
        }
      }
      parentPath = currentPath
    }
  }
  return [root]
}

// 按部门（含子部门）从后端加载全量文件夹树
async function reloadFolderTreeForDept(deptId) {
  try {
    const params = {}
    // deptId=-1 → department_id=0（未关联资产）
    // deptId>0 → 正常传部门ID（含子部门）
    if (deptId && deptId !== -1) {
      params.department_id = deptId
    } else if (deptId === -1) {
      params.department_id = 0
    }
    const opts = await getVMFilters(params)
    const folders = opts.folders || []
    const tree = buildFolderTree(folders)
    sortTree(tree)
    if (hideEmptyFolder.value) {
      function filterEmpty(list) {
        return list.filter(n => {
          if (n.children) n.children = filterEmpty(n.children)
          return n.vmCount > 0 || (n.children && n.children.length > 0)
        })
      }
      folderTree.value = filterEmpty(tree)
    } else {
      folderTree.value = tree
    }
  } catch { /* */ }
}

// 过滤空节点并重建文件夹树（从全部文件夹列表）
function rebuildFolderTree() {
  const tree = buildFolderTree(allFolders.value)
  sortTree(tree)
  if (hideEmptyFolder.value) {
    function filterEmpty(list) {
      return list.filter(n => {
        if (n.children) n.children = filterEmpty(n.children)
        return n.vmCount > 0 || (n.children && n.children.length > 0)
      })
    }
    folderTree.value = filterEmpty(tree)
  } else {
    folderTree.value = tree
  }
}

// 递归排序子节点（按 label 字母序）
function sortTree(nodes) {
  nodes.sort((a, b) => a.label.localeCompare(b.label, 'zh'))
  nodes.forEach(n => { if (n.children?.length) sortTree(n.children) })
}


const vmList = ref([])
const vmLoading = ref(false)
const filterOptions = ref({ power_states: [], os_names: [], networks: [], folders: [] })
const vmSearch = ref('')
const vmClaimFilter = ref('')
const vmQaxFilter = ref('')
const vmBackupFilter = ref('')
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

const sysList = ref([]), sysLoading = ref(false), sysPage = ref(1), sysSize = ref(20), sysTotal = ref(0), sysSearch = ref('')

const claimVisible = ref(false)
const claimKeyword = ref('')
const claimSearching = ref(false)
const claimSearchResult = ref([])
const claimSelected = ref([])
const claimSubmitting = ref(false)

const selectedVMs = ref([])
function onVMSelect(val) { selectedVMs.value = val }
function onVMSort({prop, order}) {
  if (!order) { loadVMs(); return }
  vmList.value.sort((a,b) => {
    const va = a[prop] ?? ''; const vb = b[prop] ?? ''
    if (typeof va === 'number') return order === 'ascending' ? va - vb : vb - va
    return order === 'ascending' ? String(va).localeCompare(String(vb)) : String(vb).localeCompare(String(va))
  })
}

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
  if (!query || query.length < 1) {
    // 没输入时，如果选了部门就列出该部门的人
    if (assignDeptId.value) {
      userSearching.value = true
      try {
        const res = await getUsers({ department_id: assignDeptId.value, size: 50 })
        userOptions.value = res.items
      } catch { userOptions.value = [] } finally { userSearching.value = false }
    } else {
      userOptions.value = []
    }
    return
  }
  userSearching.value = true
  try {
    const params = { search: query, size: 20 }
    if (assignDeptId.value) params.department_id = assignDeptId.value
    const res = await getUsers(params)
    userOptions.value = res.items
  } catch { userOptions.value = [] } finally { userSearching.value = false }
}

// 选择目标部门时，同步加载该部门的人员列表
function onAssignDeptChange(deptId) {
  if (deptId) {
    userOptions.value = []
    assignUserId.value = null
    searchUsers('')  // 加载该部门下的人员
  }
}

// 选择人员时，自动回填目标部门
function onAssignUserChange(userId) {
  if (userId) {
    const u = userOptions.value.find(x => x.id === userId)
    if (u && u.department_id && !assignDeptId.value) {
      assignDeptId.value = u.department_id
    }
  }
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
function formatDate(t) { return t ? new Date(t).toLocaleDateString('zh-CN') : '' }
function isBackupStale(t) {
  if (!t) return false
  return (Date.now() - new Date(t).getTime()) > 7 * 24 * 3600 * 1000
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
  try {
    const opts = await getVMFilters()
    filterOptions.value = opts
    allFolders.value = opts.folders || []
    rebuildFolderTree()
  } catch { /* */ }
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
  sysSearch.value = ''
  sysPage.value = 1
  await loadVMs()
  await loadDomains()
  if (activeTab.value === 'systems') await loadSystems()
  await reloadFolderTreeForDept(data.id)
}

// 文件夹树节点点击 → 筛选该文件夹下的 VM
async function handleFolderClick(data) {
  vmPage.value = 1
  if (data.id === 'root') {
    vmFolderFilter.value = ''
  } else {
    vmFolderFilter.value = data.id
  }
  await loadVMs()
}

async function loadVMs() {
  if (!selectedNode.value) return
  vmLoading.value = true
  try {
    const deptId = selectedNode.value.id === -1 ? 0 : selectedNode.value.id
    const res = await getDeptVMs(deptId, {
      page: vmPage.value, size: vmSize.value, search: vmSearch.value,
      claim_status: vmClaimFilter.value, claimed: vmClaimedFilter.value,
      has_qax: vmQaxFilter.value, has_backup: vmBackupFilter.value,
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

async function loadSystems() {
  if (!selectedNode.value) return
  sysLoading.value = true
  try {
    const deptId = selectedNode.value.id === -1 ? 0 : selectedNode.value.id
    const res = await api.get(`/assets/departments/${deptId}/systems`, {
      params: { page: sysPage.value, size: sysSize.value, search: sysSearch.value },
    })
    sysList.value = res.data.items
    sysTotal.value = res.data.total
  } catch { sysList.value = []; sysTotal.value = 0 } finally { sysLoading.value = false }
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

// 页面加载时检查是否有后台任务正在运行，自动恢复轮询
async function checkRunningTasks() {
  try {
    const st = await statusMatchOwner()
    if (st.running) {
      ownerMatchLoading.value = true
      ElMessage.info(st.message || '后台任务运行中...')
      startPollOwner()
    }
  } catch { /* */ }
}

function startPollOwner() {
  stopPollOwner()
  pollTimer = setInterval(async () => {
    const st = await statusMatchOwner()
    if (!st.running) {
      stopPollOwner()
      ownerMatchLoading.value = false
      ElMessage.success(st.message)
      await loadTree()
      if (selectedNode.value) { await loadVMs() }
    }
  }, 2000)
}

function stopPollOwner() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

onBeforeUnmount(() => { stopPollOwner() })

async function handleMatchOwner() {
  ownerMatchLoading.value = true
  try {
    const start = await startMatchOwner()
    if (!start.running) { ownerMatchLoading.value = false; ElMessage.warning(start.message); return }
    ElMessage.info(start.message)
    startPollOwner()
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

watch(activeTab, (tab) => {
  if (tab === 'systems' && selectedNode.value) loadSystems()
})

onMounted(async () => {
  await loadTree()
  await fetchFilterOptions()
  checkRunningTasks()
})
</script>

<style scoped>
.asset-page { padding: 20px; height: calc(100vh - 100px); display: flex; flex-direction: column; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; flex-wrap: wrap; gap: 8px; }
.page-header h2 { margin: 0; font-size: 20px; }
.header-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.asset-content { display: flex; gap: 16px; flex: 1; overflow: hidden; }
.tree-panel { flex-shrink: 0; border: 1px solid #e4e7ed; border-radius: 6px; padding: 10px; overflow-y: auto; background: #fff; }
.tree-resizer { width: 6px; cursor: col-resize; flex-shrink: 0; background: transparent; transition: background .2s; }
.tree-resizer:hover { background: #409eff; }
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
.vm-split { display: flex; gap: 12px; flex: 1; overflow: hidden; min-height: 0; }
.vm-folder-tree { width: 220px; flex-shrink: 0; border: 1px solid #e4e7ed; border-radius: 6px; padding: 8px; overflow-y: auto; background: #fafafa; font-size: 13px; }
.vm-folder-tree :deep(.el-tree-node__content) { height: 28px; }
.folder-node { display: flex; align-items: center; gap: 4px; font-size: 13px; }
.vm-table-wrap { flex: 1; overflow: hidden; display: flex; flex-direction: column; min-width: 0; }
</style>
