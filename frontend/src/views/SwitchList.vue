<template>
  <div class="switch-list">
    <div class="page-header">
      <h2>交换机管理</h2>
      <div class="header-actions" v-if="authStore.isAdmin">
        <el-button @click="downloadTemplate">
          <el-icon><Download /></el-icon>下载模板
        </el-button>
        <el-upload
          :show-file-list="false"
          :before-upload="handleImport"
          accept=".xlsx,.xls,.csv"
        >
          <el-button>
            <el-icon><Upload /></el-icon>批量导入
          </el-button>
        </el-upload>
        <el-dropdown trigger="click">
          <el-button type="warning" plain>
            批量操作<el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleScanAll">
                <el-icon><Refresh /></el-icon>全部扫描
              </el-dropdown-item>
              <el-dropdown-item @click="handleDeleteAll" divided>
                <span style="color: #f56c6c;"><el-icon><Delete /></el-icon>全部删除</span>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button type="primary" @click="openCreate">
          <el-icon><Plus /></el-icon>添加交换机
        </el-button>
      </div>
    </div>

    <el-card>
      <el-table :data="switches" stripe v-loading="loading" style="width: 100%">
        <template #empty>
          <el-empty description="暂无交换机，请点击「添加交换机」开始" :image-size="80" />
        </template>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="name" label="名称" min-width="120" />
        <el-table-column prop="ip_address" label="IP 地址" width="140" />
        <el-table-column prop="mib_type" label="MIB 类型" width="100">
          <template #default="{ row }">
            <el-tag :type="row.mib_type === 'huawei' ? 'warning' : ''" size="small">
              {{ row.mib_type === 'huawei' ? '华为' : '标准' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="scan_interval" label="扫描间隔" width="100">
          <template #default="{ row }">
            {{ row.scan_interval > 0 ? row.scan_interval + 's' : '手动' }}
          </template>
        </el-table-column>
        <el-table-column label="最后扫描" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.last_scan_status === 'success'" type="success" size="small">成功</el-tag>
            <el-tag v-else-if="row.last_scan_status === 'failed'" type="danger" size="small">失败</el-tag>
            <span v-else style="color:#c0c4cc;">未扫描</span>
          </template>
        </el-table-column>
        <el-table-column label="扫描结果" width="160">
          <template #default="{ row }">
            <template v-if="row.last_hosts_found > 0 || row.last_routes_found > 0">
              <span title="主机数">{{ row.last_hosts_found }} 主机</span>
              <span style="margin:0 4px;color:#dcdfe6;">|</span>
              <span title="路由数">{{ row.last_routes_found }} 路由</span>
            </template>
            <span v-else style="color:#c0c4cc;">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
              {{ row.is_active ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="$router.push(`/switches/${row.id}`)">详情</el-button>
            <el-dropdown v-if="authStore.isAdmin" trigger="click" @command="(cmd) => handleCommand(cmd, row)">
              <el-button size="small">
                更多<el-icon class="el-icon--right"><ArrowDown /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="scan">
                    <el-icon><Refresh /></el-icon>扫描
                  </el-dropdown-item>
                  <el-dropdown-item command="edit">
                    <el-icon><Edit /></el-icon>编辑
                  </el-dropdown-item>
                  <el-dropdown-item command="delete" divided>
                    <span style="color: #f56c6c;"><el-icon><Delete /></el-icon>删除</span>
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap" v-if="total > 0">
        <el-pagination
          v-model:current-page="page" :page-size="size" :total="total"
          layout="total, prev, pager, next" @current-change="fetchList" />
      </div>
    </el-card>

    <SwitchFormDialog v-model:visible="dialogVisible" :edit-data="editData" @saved="fetchList" />

    <el-dialog v-model="importDialogVisible" title="导入结果" width="420px">
      <div v-if="importResult">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="新建">{{ importResult.created }}</el-descriptions-item>
          <el-descriptions-item label="跳过(重复)">{{ importResult.skipped }}</el-descriptions-item>
        </el-descriptions>
        <div v-if="importResult.errors.length > 0" style="margin-top:12px;">
          <p style="color:#f56c6c;">错误 ({{ importResult.errors.length }}):</p>
          <ul style="max-height:200px;overflow:auto;font-size:13px;">
            <li v-for="(e, i) in importResult.errors" :key="i">{{ e }}</li>
          </ul>
        </div>
      </div>
      <template #footer>
        <el-button type="primary" @click="importDialogVisible=false;fetchList()">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useAuthStore } from '@/store/auth'
import { getSwitches, triggerScan, deleteSwitch, downloadTemplate, importSwitches, scanAllSwitches, deleteAllSwitches } from '@/api/switches'
import { ElMessage, ElMessageBox } from 'element-plus'
import SwitchFormDialog from '@/components/SwitchFormDialog.vue'

const authStore = useAuthStore()
const switches = ref([])
const loading = ref(false)
const page = ref(1)
const size = ref(20)
const total = ref(0)
const dialogVisible = ref(false)
const editData = ref(null)
const importDialogVisible = ref(false)
const importResult = ref(null)

function formatTime(t) {
  if (!t) return ''
  const d = new Date(t)
  if (isNaN(d.getTime())) return t
  return d.toLocaleString('zh-CN', { hour12: false })
}

async function fetchList() {
  loading.value = true
  try {
    const res = await getSwitches({ page: page.value, size: size.value })
    switches.value = res.items
    total.value = res.total
  } finally {
    loading.value = false
  }
}

async function handleImport(file) {
  try {
    const result = await importSwitches(file)
    importResult.value = result
    importDialogVisible.value = true
  } catch { /* handled by interceptor */ }
  return false // prevent auto-upload
}

function openCreate() {
  editData.value = null
  dialogVisible.value = true
}

function openEdit(row) {
  editData.value = { ...row }
  dialogVisible.value = true
}

async function handleScan(row) {
  try {
    await ElMessageBox.confirm(`确认扫描交换机 ${row.name} (${row.ip_address})？`, '确认扫描')
    await triggerScan(row.id)
    ElMessage.success('扫描已触发')
    fetchList()
  } catch { /* cancelled */ }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确认删除交换机 ${row.name}？此操作不可恢复。`, '确认删除', {
      type: 'warning',
    })
    await deleteSwitch(row.id)
    ElMessage.success('已删除')
    fetchList()
  } catch { /* cancelled */ }
}

function handleCommand(cmd, row) {
  if (cmd === 'scan') handleScan(row)
  else if (cmd === 'edit') openEdit(row)
  else if (cmd === 'delete') handleDelete(row)
}

async function handleScanAll() {
  try {
    await ElMessageBox.confirm('确认扫描所有启用的交换机？', '全部扫描', { type: 'info' })
    const result = await scanAllSwitches()
    ElMessage.success(result.message)
    fetchList()
  } catch { /* cancelled */ }
}

async function handleDeleteAll() {
  try {
    await ElMessageBox.confirm(
      '此操作将删除所有交换机及其关联的扫描数据、历史记录，不可恢复！请确认。',
      '全部删除',
      { type: 'error', confirmButtonClass: 'el-button--danger' }
    )
    const result = await deleteAllSwitches()
    ElMessage.success(result.message)
    fetchList()
  } catch { /* cancelled */ }
}

onMounted(fetchList)
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.page-header h2 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
}
.header-actions {
  display: flex;
  gap: 10px;
  align-items: center;
}
.pagination-wrap {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}
</style>
