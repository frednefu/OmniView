<template>
  <div class="scheduler-page">
    <div class="page-header">
      <h2>定时任务监控</h2>
      <div class="header-right">
        <el-tag :type="status.running ? 'success' : 'danger'" size="large" effect="dark">
          {{ status.running ? '守护程序运行中' : '守护程序已停止' }}
        </el-tag>
        <el-button :icon="Refresh" circle @click="fetchStatus" :loading="loading" />
      </div>
    </div>

    <el-table :data="status.jobs" v-loading="loading" stripe size="small">
      <el-table-column prop="name" label="任务名称" min-width="180" />
      <el-table-column label="周期" width="160">
        <template #default="{ row }">
          <div v-if="editingId === row.id" class="edit-interval">
            <el-input-number v-model="editSecs" :min="10" :step="60" size="small" controls-position="right" style="width:100px" />
            <el-button size="small" type="primary" @click="saveInterval(row)">保存</el-button>
            <el-button size="small" @click="editingId = null">取消</el-button>
          </div>
          <span v-else class="interval-cell" @click="startEdit(row)">
            {{ row.interval }}
            <el-icon><Edit /></el-icon>
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="next_run" label="下次运行" width="180">
        <template #default="{ row }">
          <span v-if="row.next_run">{{ formatTime(row.next_run) }}</span>
          <span v-else class="na">-</span>
        </template>
      </el-table-column>
    </el-table>

    <div class="summary">共 <strong>{{ status.total }}</strong> 个定时任务</div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, Edit } from '@element-plus/icons-vue'
import { useAuthStore } from '@/store/auth'

const authStore = useAuthStore()
const loading = ref(false)
const status = reactive({ running: false, jobs: [], total: 0 })
const editingId = ref(null)
const editSecs = ref(0)
let timer = null

function formatTime(t) {
  if (!t) return '-'
  return new Date(t).toLocaleString('zh-CN', { hour12: false })
}

function startEdit(row) {
  editingId.value = row.id
  editSecs.value = row.interval_secs
}

async function saveInterval(row) {
  try {
    const res = await fetch('/api/system/scheduler-interval', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${authStore.token}` },
      body: JSON.stringify({ job_id: row.id, interval_secs: editSecs.value }),
    })
    if (!res.ok) throw new Error()
    ElMessage.success(`周期已修改`)
    editingId.value = null
    await fetchStatus()
  } catch { ElMessage.error('修改失败') }
}

async function fetchStatus() {
  loading.value = true
  try {
    const res = await fetch('/api/system/scheduler-status', {
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    const data = await res.json()
    status.running = data.running
    status.jobs = data.jobs || []
    status.total = data.total || 0
  } catch { /* silent */ } finally { loading.value = false }
}

onMounted(() => { fetchStatus(); timer = setInterval(fetchStatus, 10000) })
onBeforeUnmount(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.scheduler-page { padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 8px; }
.page-header h2 { margin: 0; font-size: 20px; }
.header-right { display: flex; align-items: center; gap: 10px; }
.na { color: #c0c4cc; }
.summary { margin-top: 16px; font-size: 13px; color: #606266; }
.interval-cell { cursor: pointer; display: flex; align-items: center; gap: 4px; }
.interval-cell:hover { color: var(--el-color-primary); }
.edit-interval { display: flex; align-items: center; gap: 6px; }
</style>
