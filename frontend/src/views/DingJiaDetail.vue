<template>
  <div class="page">
    <div class="page-header">
      <h2>备份记录</h2>
      <el-button @click="$router.push('/dingjia')">返回列表</el-button>
    </div>
    <div class="filter-bar">
      <el-input v-model="search" placeholder="搜索VM名称/主机/IP" clearable style="width:260px" @keyup.enter="fetchList" @clear="fetchList">
        <template #append><el-button :icon="Search" @click="fetchList"/></template>
      </el-input>
      <span style="color:#909399;font-size:13px;line-height:32px;white-space:nowrap">共 {{ total }} 条</span>
    </div>
    <el-table :data="items" v-loading="loading" stripe size="small" @sort-change="onSort" row-key="id" :default-sort="{prop:'last_run_time',order:'descending'}">
      <el-table-column type="expand">
        <template #default="{ row }">
          <div v-if="parseVersions(row.backup_versions_detail).length > 0" class="version-panel">
            <div class="version-title">备份历史（共 {{ parseVersions(row.backup_versions_detail).length }} 个版本）</div>
            <el-table :data="parseVersions(row.backup_versions_detail)" size="small" border>
              <el-table-column prop="time" label="开始时间" width="160" />
              <el-table-column prop="end_time" label="结束时间" width="160" />
              <el-table-column label="持续时间" width="100">
                <template #default="{ row: vr }">{{ formatDuration(vr.duration_seconds) }}</template>
              </el-table-column>
              <el-table-column prop="type" label="类型" width="80">
                <template #default="{ row: vr }">
                  <el-tag size="small" :type="vr.type==='full'?'success':''">{{ vr.type === 'full' ? '全备' : vr.type === 'incremental' ? '增量' : vr.type || '-' }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="大小" width="90">
                <template #default="{ row: vr }">{{ vr.size_gb ? vr.size_gb + 'G' : '-' }}</template>
              </el-table-column>
            </el-table>
          </div>
          <div v-else style="color:#909399;padding:8px 0">暂无历史版本详情</div>
        </template>
      </el-table-column>
      <el-table-column prop="vm_name" label="虚拟机名称" min-width="160" show-overflow-tooltip sortable="custom" />
      <el-table-column prop="vm_size_gb" label="大小(GB)" width="90" sortable="custom">
        <template #default="{row}">{{ row.vm_size_gb ? row.vm_size_gb + 'G' : '-' }}</template>
      </el-table-column>
      <el-table-column prop="backup_versions" label="版本数" width="80" sortable="custom" />
      <el-table-column prop="backup_type" label="类型" width="80" sortable="custom">
        <template #default="{row}">
          <el-tag size="small" :type="row.backup_type==='full'?'success':''">{{ row.backup_type === 'full' ? '全备' : row.backup_type === 'incremental' ? '增量' : row.backup_type || '-' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="last_run_result" label="结果" width="80" sortable="custom">
        <template #default="{row}">
          <el-tag :type="row.last_run_result==='completed'?'success':'danger'" size="small">{{ row.last_run_result === 'completed' ? '成功' : row.last_run_result || '-' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="last_run_time" label="开始时间" width="160" sortable="custom">
        <template #default="{row}">{{ formatTime(row.last_run_time) }}</template>
      </el-table-column>
      <el-table-column prop="last_completed_time" label="结束时间" width="160" sortable="custom">
        <template #default="{row}">{{ formatTime(row.last_completed_time) }}</template>
      </el-table-column>
      <el-table-column prop="duration_seconds" label="持续时间" width="100" sortable="custom">
        <template #default="{row}">{{ formatDuration(row.duration_seconds) }}</template>
      </el-table-column>
      <el-table-column prop="host_ip" label="主机IP" width="140" sortable="custom" />
      <el-table-column prop="job_name" label="作业名称" min-width="160" show-overflow-tooltip sortable="custom" />
    </el-table>
    <el-pagination v-if="total>0" v-model:current-page="page" v-model:page-size="size" :page-sizes="[10,20,50,100]" :total="total" layout="total,sizes,prev,pager,next" @current-change="fetchList" @size-change="fetchList" style="justify-content:center;margin-top:16px"/>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { Search } from '@element-plus/icons-vue'
import api from '@/api/index'

const route = useRoute()
const items = ref([]), loading = ref(false), page = ref(1), size = ref(20), total = ref(0), search = ref('')
const sortField = ref(''), sortOrder = ref('')

function parseVersions(detail) {
  if (!detail) return []
  try {
    const arr = typeof detail === 'string' ? JSON.parse(detail) : detail
    if (!Array.isArray(arr)) return []
    // 按开始时间倒序（最新在前）
    return arr.sort((a, b) => (b.time || '').localeCompare(a.time || ''))
  } catch { return [] }
}

function formatTime(t) { return t ? new Date(t).toLocaleString('zh-CN', { hour12: false }) : '-' }
function formatDuration(s) {
  if (s == null) return '-'
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60
  if (h > 0) return h + ':' + String(m).padStart(2,'0') + ':' + String(sec).padStart(2,'0')
  if (m > 0) return m + ':' + String(sec).padStart(2,'0')
  return '0:' + String(sec).padStart(2,'0')
}

function onSort({ prop, order }) {
  sortField.value = prop || ''
  sortOrder.value = order || ''
  page.value = 1
  fetchList()
}

async function fetchList() {
  loading.value = true
  try {
    const params = { page: page.value, size: size.value, search: search.value }
    if (sortField.value) {
      params.sort_field = sortField.value
      params.sort_order = sortOrder.value === 'ascending' ? 'asc' : 'desc'
    }
    const r = await api.get(`/dingjia/${route.params.id}/records`, { params })
    items.value = r.data.items
    total.value = r.data.total
  } catch { } finally { loading.value = false }
}

onMounted(fetchList)
</script>
<style scoped>
.page { padding: 20px }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px }
.page-header h2 { margin: 0; font-size: 20px }
.filter-bar { margin-bottom: 14px; display: flex; gap: 8px; align-items: center }
.version-panel { padding: 8px 0 }
.version-title { font-size: 13px; color: #606266; margin-bottom: 8px; font-weight: 500 }
</style>
