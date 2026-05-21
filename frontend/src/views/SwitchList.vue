<template>
  <div class="switch-list">
    <div class="page-header">
      <h2>交换机管理</h2>
      <el-button v-if="authStore.isAdmin" type="primary" @click="openCreate">
        <el-icon><Plus /></el-icon>添加交换机
      </el-button>
    </div>

    <el-card>
      <el-table :data="switches" stripe v-loading="loading" style="width: 100%">
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
        <el-table-column prop="is_active" label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
              {{ row.is_active ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="updated_at" label="更新时间" width="160">
          <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="$router.push(`/switches/${row.id}`)">详情</el-button>
            <el-button v-if="authStore.isAdmin" size="small" @click="handleScan(row)">
              <el-icon><Refresh /></el-icon>扫描
            </el-button>
            <el-button v-if="authStore.isAdmin" size="small" type="warning" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="authStore.isAdmin" size="small" type="danger" @click="handleDelete(row)">删除</el-button>
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
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useAuthStore } from '@/store/auth'
import { getSwitches, triggerScan, deleteSwitch } from '@/api/switches'
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

function formatTime(t) {
  if (!t) return ''
  return new Date(t).toLocaleString('zh-CN')
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

onMounted(fetchList)
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.page-header h2 { margin: 0; }
.pagination-wrap {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}
</style>
