<template>
  <div class="scan-logs-page">
    <div class="page-header">
      <h2>扫描日志</h2>
      <el-button type="danger" plain @click="handleClear" :disabled="!total">
        <el-icon><Delete /></el-icon> 清除全部
      </el-button>
    </div>

    <el-form :inline="true" class="filter-bar">
      <el-form-item label="数据源">
        <el-select v-model="filters.source_type" placeholder="全部" clearable style="width:140px" @change="fetchData">
          <el-option label="交换机" value="switch" />
          <el-option label="vCenter" value="vcenter" />
          <el-option label="F5" value="f5" />
          <el-option label="ZDNS" value="zdns" />
        </el-select>
      </el-form-item>
      <el-form-item label="状态">
        <el-select v-model="filters.status" placeholder="全部" clearable style="width:120px" @change="fetchData">
          <el-option label="扫描中" value="running" />
          <el-option label="成功" value="success" />
          <el-option label="失败" value="failed" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="fetchData">查询</el-button>
        <el-button @click="resetFilters">重置</el-button>
      </el-form-item>
    </el-form>

    <el-table :data="items" v-loading="loading" stripe style="width:100%">
      <template #empty>
        <el-empty description="暂无扫描日志" :image-size="80" />
      </template>
      <el-table-column label="时间" width="170">
        <template #default="{ row }">{{ formatTime(row.started_at) }}</template>
      </el-table-column>
      <el-table-column label="数据源" width="120">
        <template #default="{ row }">
          <el-tag :type="sourceTag(row.source_type)" size="small">{{ sourceLabel(row.source_type) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="source_name" label="设备名称" width="160" show-overflow-tooltip />
      <el-table-column label="触发方式" width="90">
        <template #default="{ row }">
          <el-tag :type="row.triggered_by === 'scheduled' ? '' : 'info'" size="small" effect="plain">
            {{ row.triggered_by === 'scheduled' ? '定时' : '手动' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="statusTag(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="发现数量" width="100">
        <template #default="{ row }">
          <span v-if="row.hosts_found > 0">{{ row.hosts_found }}</span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="耗时" width="80">
        <template #default="{ row }">
          <span v-if="row.duration_seconds != null">{{ row.duration_seconds }}s</span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="错误信息" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.error_message" class="error-text">{{ row.error_message }}</span>
          <span v-else>-</span>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination-wrap" v-if="total > 0">
      <el-pagination
        v-model:current-page="page"
        :page-size="size"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="fetchData"
      />
    </div>

    <!-- 清除确认对话框 -->
    <el-dialog v-model="clearDialogVisible" title="确认清除" width="420px">
      <p>确定要清除<span v-if="filters.source_type">{{ sourceLabel(filters.source_type) }}的</span>全部扫描日志吗？此操作不可恢复。</p>
      <template #footer>
        <el-button @click="clearDialogVisible = false">取消</el-button>
        <el-button type="danger" @click="confirmClear" :loading="clearing">确定清除</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { getScanLogs, clearScanLogs } from '@/api/scanLogs'
import { ElMessage } from 'element-plus'

const items = ref([])
const loading = ref(false)
const clearing = ref(false)
const page = ref(1)
const size = ref(30)
const total = ref(0)
const clearDialogVisible = ref(false)
const filters = reactive({ source_type: '', status: '' })

function formatTime(t) {
  if (!t) return ''
  const d = new Date(t)
  if (isNaN(d.getTime())) return t
  return d.toLocaleString('zh-CN', { hour12: false })
}

function sourceTag(type) {
  const map = { switch: '', vcenter: 'success', f5: 'warning', zdns: '' }
  return map[type] || ''
}

function sourceLabel(type) {
  const map = { switch: '交换机', vcenter: 'vCenter', f5: 'F5', zdns: 'ZDNS' }
  return map[type] || type
}

function statusTag(status) {
  const map = { running: 'warning', success: 'success', failed: 'danger' }
  return map[status] || 'info'
}

function statusLabel(status) {
  const map = { running: '扫描中', success: '成功', failed: '失败' }
  return map[status] || status
}

function resetFilters() {
  filters.source_type = ''
  filters.status = ''
  page.value = 1
  fetchData()
}

async function fetchData() {
  loading.value = true
  try {
    const params = { page: page.value, size: size.value }
    if (filters.source_type) params.source_type = filters.source_type
    if (filters.status) params.status = filters.status
    const data = await getScanLogs(params)
    items.value = data.items
    total.value = data.total
  } catch { /* handled by interceptor */ }
  finally { loading.value = false }
}

function handleClear() {
  clearDialogVisible.value = true
}

async function confirmClear() {
  clearing.value = true
  try {
    const result = await clearScanLogs(filters.source_type || undefined)
    ElMessage.success(result.message)
    clearDialogVisible.value = false
    page.value = 1
    fetchData()
  } catch { /* handled */ }
  finally { clearing.value = false }
}

onMounted(() => {
  fetchData()
})
</script>

<style scoped>
.scan-logs-page h2 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
}
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}
.filter-bar {
  margin-bottom: 16px;
  background: var(--color-bg-card);
  padding: 16px 16px 0;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
}
.pagination-wrap {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
.error-text {
  color: var(--el-color-danger);
}
</style>
