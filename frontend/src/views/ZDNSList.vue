<template>
  <div class="zdns-list">
    <div class="page-header">
      <h2>ZDNS 管理</h2>
      <div class="header-actions" v-if="authStore.isAdmin">
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
          <el-icon><Plus /></el-icon>添加 ZDNS
        </el-button>
      </div>
    </div>

    <el-card>
      <el-table :data="devices" stripe v-loading="loading" style="width: 100%">
        <template #empty>
          <el-empty description="暂无 ZDNS 设备，请点击「添加 ZDNS」开始" :image-size="80" />
        </template>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="name" label="名称" min-width="120" />
        <el-table-column prop="host" label="主机地址" min-width="180" />
        <el-table-column prop="username" label="用户名" width="140" />
        <el-table-column prop="port" label="端口" width="80" />
        <el-table-column label="扫描间隔" width="100">
          <template #default="{ row }">
            {{ row.scan_interval > 0 ? row.scan_interval + 's' : '手动' }}
          </template>
        </el-table-column>
        <el-table-column label="最后扫描" width="130">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:6px;">
              <el-tag v-if="row.last_scan_status === 'success'" type="success" size="small">成功</el-tag>
              <el-tag v-else-if="row.last_scan_status === 'failed'" type="danger" size="small">失败</el-tag>
              <el-tag v-else-if="row.last_scan_status === 'running'" type="warning" size="small">扫描中</el-tag>
              <span v-else style="color:#c0c4cc;">未扫描</span>
              <span v-if="row.last_scan_duration" style="color:#909399;font-size:12px;">{{ row.last_scan_duration }}s</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="记录 / 区" width="110">
          <template #default="{ row }">
            {{ row.last_record_count || 0 }} / {{ row.last_zone_count || 0 }}
          </template>
        </el-table-column>
        <el-table-column label="IP扫描耗时" width="100">
          <template #default="{ row }">
            <span v-if="row.last_ip_scan_duration" style="color:#909399;">{{ row.last_ip_scan_duration }}s</span>
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
            <el-button size="small" @click="$router.push(`/zdns/${row.id}`)">详情</el-button>
            <el-dropdown v-if="authStore.isAdmin" trigger="click" @command="(cmd) => handleCommand(cmd, row)">
              <el-button size="small">
                更多<el-icon class="el-icon--right"><ArrowDown /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="scan">
                    <el-icon><Refresh /></el-icon>扫描
                  </el-dropdown-item>
                  <el-dropdown-item command="ipscan">
                    <el-icon><Connection /></el-icon>IP扫描
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

    <ZDNSFormDialog v-model:visible="dialogVisible" :edit-data="editData" @saved="fetchList" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useAuthStore } from '@/store/auth'
import { getZDNSDevices, deleteZDNSDevice, triggerZDNSScan, triggerZDNSIPScan, scanAllZDNSDevices, deleteAllZDNSDevices } from '@/api/zdns'
import { ElMessage, ElMessageBox } from 'element-plus'
import ZDNSFormDialog from '@/components/ZDNSFormDialog.vue'

const authStore = useAuthStore()
const devices = ref([])
const loading = ref(false)
const page = ref(1)
const size = ref(20)
const total = ref(0)
const dialogVisible = ref(false)
const editData = ref(null)

async function fetchList() {
  loading.value = true
  try {
    const res = await getZDNSDevices({ page: page.value, size: size.value })
    devices.value = res.items
    total.value = res.total
  } finally {
    loading.value = false
  }
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
    await ElMessageBox.confirm(`确认扫描 ZDNS ${row.name} (${row.host})？`, '确认扫描')
    await triggerZDNSScan(row.id)
    ElMessage.success('扫描已触发')
    fetchList()
  } catch { /* cancelled */ }
}

async function handleIPScan(row) {
  try {
    await ElMessageBox.confirm(`确认对 ZDNS ${row.name} 执行 IP 可达性扫描？`, '确认 IP 扫描')
    await triggerZDNSIPScan(row.id)
    ElMessage.success('IP 扫描已触发')
    fetchList()
  } catch { /* cancelled */ }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确认删除 ZDNS ${row.name}？此操作不可恢复。`, '确认删除', { type: 'warning' })
    await deleteZDNSDevice(row.id)
    ElMessage.success('已删除')
    fetchList()
  } catch { /* cancelled */ }
}

function handleCommand(cmd, row) {
  if (cmd === 'scan') handleScan(row)
  else if (cmd === 'ipscan') handleIPScan(row)
  else if (cmd === 'edit') openEdit(row)
  else if (cmd === 'delete') handleDelete(row)
}

async function handleScanAll() {
  try {
    await ElMessageBox.confirm('确认扫描所有启用的 ZDNS 设备？', '全部扫描', { type: 'info' })
    const result = await scanAllZDNSDevices()
    ElMessage.success(result.message)
    fetchList()
  } catch { /* cancelled */ }
}

async function handleDeleteAll() {
  try {
    await ElMessageBox.confirm(
      '此操作将删除所有 ZDNS 设备及其关联数据，不可恢复！',
      '全部删除',
      { type: 'error', confirmButtonClass: 'el-button--danger' }
    )
    const result = await deleteAllZDNSDevices()
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
