<template>
  <div class="worker-manage">
    <div class="page-header">
      <h2>Worker 管理</h2>
      <div style="display: flex; gap: 10px; align-items: center;">
        <span style="font-size: 13px; color: #909399;">
          在线 {{ onlineCount }} / 共 {{ total }}
        </span>
        <el-switch v-model="autoRefresh" active-text="自动刷新" size="small" />
        <el-button @click="fetchList" :loading="loading">
          <el-icon><Refresh /></el-icon>刷新
        </el-button>
        <el-button type="primary" @click="openRegister">
          <el-icon><Plus /></el-icon>注册 Worker
        </el-button>
      </div>
    </div>

    <el-card>
      <div class="filter-bar">
        <el-select v-model="statusFilter" placeholder="状态筛选" clearable style="width: 140px" @change="onFilterChange">
          <el-option label="全部" value="" />
          <el-option label="在线" value="online" />
          <el-option label="忙碌" value="busy" />
          <el-option label="待接入" value="pending" />
          <el-option label="离线" value="offline" />
        </el-select>
        <el-input v-model="search" placeholder="搜索 Worker 名称..." clearable style="width: 240px" @keyup.enter="onFilterChange" @clear="onFilterChange" />
        <el-button type="primary" @click="onFilterChange">查询</el-button>
      </div>

      <el-table :data="workers" stripe v-loading="loading" style="width: 100%">
        <template #empty>
          <el-empty description="暂无 Worker 节点" :image-size="80" />
        </template>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="worker_name" label="Worker 名称" min-width="160" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="ip_address" label="IP 地址" width="140">
          <template #default="{ row }">
            {{ row.ip_address || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="能力" min-width="200">
          <template #default="{ row }">
            <el-tag v-for="t in taskTypes(row)" :key="t" size="small" effect="dark" :color="taskColor(t)" style="margin-right: 4px;">
              {{ taskTypeLabel(t) }}
            </el-tag>
            <span v-if="!taskTypes(row).length" style="color: #909399;">-</span>
          </template>
        </el-table-column>
        <el-table-column label="并发" width="80">
          <template #default="{ row }">
            {{ row.current_tasks }} / {{ row.max_tasks }}
          </template>
        </el-table-column>
        <el-table-column prop="version" label="版本" width="80">
          <template #default="{ row }">
            {{ row.version || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="最后心跳" width="140">
          <template #default="{ row }">
            <span :style="{ color: heartbeatStale(row) ? '#F56C6C' : '' }">
              {{ relativeTime(row.last_heartbeat) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="注册时间" width="170">
          <template #default="{ row }">
            {{ formatTime(row.registered_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap" v-if="total > 0">
        <el-pagination
          v-model:current-page="page" :page-size="size" :total="total"
          layout="total, prev, pager, next" @current-change="fetchList" />
      </div>
    </el-card>

    <!-- 注册 Worker 对话框 -->
    <el-dialog v-model="dialogVisible" title="注册 Worker" width="480px" @close="resetForm">
      <el-form :model="form" :rules="formRules" ref="formRef" label-width="80px">
        <el-form-item label="名称" prop="worker_name">
          <el-input v-model="form.worker_name" placeholder="例如: omniview-worker-01" />
        </el-form-item>
        <el-form-item label="版本">
          <el-input v-model="form.version" placeholder="例如: 2.0.0" />
        </el-form-item>
        <el-form-item label="扫描能力">
          <el-checkbox-group v-model="form.task_types">
            <el-checkbox label="switch">交换机</el-checkbox>
            <el-checkbox label="vcenter">vCenter</el-checkbox>
            <el-checkbox label="f5">F5</el-checkbox>
            <el-checkbox label="zdns">ZDNS</el-checkbox>
            <el-checkbox label="zdns_ip">IP扫描</el-checkbox>
            <el-checkbox label="qax">椒图</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleRegister" :loading="submitting">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { reactive, ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { getWorkers, registerWorker, deleteWorker } from '@/api/workers'
import { getVersion } from '@/api/version'
import { ElMessage, ElMessageBox } from 'element-plus'

const workers = ref([])
const loading = ref(false)
const page = ref(1)
const size = ref(20)
const total = ref(0)
const search = ref('')
const statusFilter = ref('')
const autoRefresh = ref(true)

// 注册对话框
const dialogVisible = ref(false)
const submitting = ref(false)
const formRef = ref(null)
const form = reactive({ worker_name: '', version: '1.0.0', task_types: ['switch', 'vcenter', 'f5', 'zdns', 'zdns_ip', 'qax'] })
const formRules = {
  worker_name: [{ required: true, message: '请输入 Worker 名称', trigger: 'blur' }],
}

let refreshTimer = null

const appVersion = ref('1.0.0')

const onlineCount = computed(() => workers.value.filter(w => w.status === 'online').length)

function statusType(s) {
  return s === 'online' ? 'success' : s === 'busy' ? 'warning' : s === 'pending' ? '' : 'info'
}

function statusLabel(s) {
  return s === 'online' ? '在线' : s === 'busy' ? '忙碌' : s === 'pending' ? '待接入' : '离线'
}

const _TASK_LABELS = {
  switch: '交换机', vcenter: 'vCenter', f5: 'F5', zdns: 'ZDNS', zdns_ip: 'IP扫描', qax: '椒图', dingjia: '鼎甲',
}

const _TASK_COLORS = {
  switch: '#06b6d4', vcenter: '#f59e0b', f5: '#10b981', zdns: '#6366f1', zdns_ip: '#8b5cf6', qax: '#ef4444',
}

function taskTypes(row) {
  return row.capabilities?.task_types || []
}

function taskTypeLabel(t) {
  return _TASK_LABELS[t] || t
}

function taskColor(t) {
  return _TASK_COLORS[t] || '#94a3b8'
}

function heartbeatStale(row) {
  if (!row.last_heartbeat) return false
  return Date.now() - new Date(row.last_heartbeat).getTime() > 45000
}

function relativeTime(t) {
  if (!t) return '-'
  const diff = Math.floor((Date.now() - new Date(t).getTime()) / 1000)
  if (diff < 60) return `${diff}秒前`
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`
  return `${Math.floor(diff / 86400)}天前`
}

function formatTime(t) {
  if (!t) return ''
  const d = new Date(t)
  if (isNaN(d.getTime())) return t
  return d.toLocaleString('zh-CN', { hour12: false })
}

async function fetchList() {
  loading.value = true
  try {
    const params = { page: page.value, size: size.value }
    if (search.value) params.search = search.value
    if (statusFilter.value) params.status = statusFilter.value
    const res = await getWorkers(params)
    workers.value = res.items
    total.value = res.total
  } finally {
    loading.value = false
  }
}

function onFilterChange() {
  page.value = 1
  fetchList()
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确认删除 Worker "${row.worker_name}"？`, '确认删除', { type: 'warning' })
    await deleteWorker(row.id)
    ElMessage.success('已删除')
    fetchList()
  } catch { /* cancelled */ }
}

function resetForm() {
  form.worker_name = ''
  form.version = appVersion.value
  form.task_types = ['switch', 'vcenter', 'f5', 'zdns', 'zdns_ip', 'qax']
  formRef.value?.resetFields()
}

function openRegister() {
  resetForm()
  dialogVisible.value = true
}

async function handleRegister() {
  try { await formRef.value.validate() } catch { return }
  submitting.value = true
  try {
    await registerWorker({
      worker_name: form.worker_name,
      version: form.version,
      capabilities: { task_types: form.task_types },
    })
    ElMessage.success('Worker 已注册')
    dialogVisible.value = false
    fetchList()
  } finally {
    submitting.value = false
  }
}

function startPolling() {
  stopPolling()
  refreshTimer = setInterval(fetchList, 5000)
}

function stopPolling() {
  if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null }
}

watch(autoRefresh, (val) => { if (val) { startPolling() } else { stopPolling() } })

async function loadVersion() {
  try {
    const data = await getVersion()
    appVersion.value = data.version
    form.version = data.version
  } catch { /* 使用默认值 */ }
}

onMounted(() => { fetchList(); startPolling(); loadVersion() })
onUnmounted(stopPolling)

if (import.meta.hot) { import.meta.hot.decline() }
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
.filter-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
}
.pagination-wrap {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}
</style>
