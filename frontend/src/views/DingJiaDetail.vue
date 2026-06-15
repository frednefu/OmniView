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
    <el-table :data="items" v-loading="loading" stripe size="small" @sort-change="onSort">
      <el-table-column prop="vm_name" label="虚拟机名称" min-width="160" show-overflow-tooltip sortable="custom" />
      <el-table-column prop="vm_size_gb" label="大小(GB)" width="90" sortable="custom">
        <template #default="{row}">{{ row.vm_size_gb ? row.vm_size_gb + 'G' : '-' }}</template>
      </el-table-column>
      <el-table-column prop="backup_versions" label="版本数" width="80" sortable="custom" />
      <el-table-column prop="backup_subtype" label="类型" width="80" sortable="custom">
        <template #default="{row}">
          <el-tag size="small">{{ row.backup_subtype === 'full' ? '全备' : row.backup_subtype === 'incremental' ? '增量' : row.backup_subtype || '-' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="last_run_result" label="结果" width="80" sortable="custom">
        <template #default="{row}">
          <el-tag :type="row.last_run_result==='completed'?'success':'danger'" size="small">{{ row.last_run_result === 'completed' ? '成功' : row.last_run_result || '-' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="last_run_time" label="备份时间" width="160" sortable="custom">
        <template #default="{row}">{{ formatTime(row.last_run_time) }}</template>
      </el-table-column>
      <el-table-column prop="last_completed_time" label="完成时间" width="160" sortable="custom">
        <template #default="{row}">{{ formatTime(row.last_completed_time) }}</template>
      </el-table-column>
      <el-table-column prop="next_run_time" label="下次备份" width="160" sortable="custom">
        <template #default="{row}">{{ formatTime(row.next_run_time) }}</template>
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

function formatTime(t) { return t ? new Date(t).toLocaleString('zh-CN', { hour12: false }) : '-' }

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
</style>
