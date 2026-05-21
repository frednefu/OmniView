<template>
  <div class="history-page">
    <h2>历史记录</h2>

    <el-form :inline="true" class="filter-bar">
      <el-form-item label="IP 地址">
        <el-input v-model="filters.ip" placeholder="输入 IP" clearable style="width:150px" />
      </el-form-item>
      <el-form-item label="MAC 地址">
        <el-input v-model="filters.mac" placeholder="输入 MAC" clearable style="width:150px" />
      </el-form-item>
      <el-form-item label="变更类型">
        <el-select v-model="filters.change_type" placeholder="全部" clearable style="width:110px">
          <el-option label="新增" value="added" />
          <el-option label="删除" value="deleted" />
          <el-option label="变更" value="modified" />
        </el-select>
      </el-form-item>
      <el-form-item label="交换机">
        <el-select v-model="filters.switch_id" placeholder="全部" clearable style="width:180px">
          <el-option v-for="s in switchOptions" :key="s.id" :label="s.name" :value="s.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="时间范围">
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          range-separator="至"
          start-placeholder="开始"
          end-placeholder="结束"
          value-format="YYYY-MM-DD"
          style="width:240px"
        />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="fetchData">查询</el-button>
        <el-button @click="resetFilters">重置</el-button>
      </el-form-item>
    </el-form>

    <el-table :data="items" v-loading="loading" stripe :row-class-name="rowClassName" style="width:100%">
      <template #empty>
        <el-empty description="暂无历史记录" :image-size="80" />
      </template>
      <el-table-column label="时间" width="170">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column prop="switch_name" label="交换机" width="160" show-overflow-tooltip />
      <el-table-column label="变更类型" width="90">
        <template #default="{ row }">
          <el-tag :type="changeTag(row.change_type)" size="small">{{ changeLabel(row.change_type) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="ip_address" label="IP 地址" width="140" />
      <el-table-column prop="mac_address" label="MAC 地址" width="150" />
      <el-table-column label="VLAN/BD" width="130">
        <template #default="{ row }">
          {{ changeDiff(row, 'vlan_bd') }}
        </template>
      </el-table-column>
      <el-table-column label="物理端口" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">
          {{ changeDiff(row, 'physical_port') }}
        </template>
      </el-table-column>
      <el-table-column label="虚拟端口" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">
          {{ changeDiff(row, 'virtual_port') }}
        </template>
      </el-table-column>
      <el-table-column label="类型" width="80">
        <template #default="{ row }">
          {{ changeDiff(row, 'switch_type') }}
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination-wrap" v-if="isPaginated && total > 0">
      <el-pagination
        v-model:current-page="page"
        :page-size="size"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="fetchData"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { getHistory, getHistoryByIp, getHistoryByMac } from '@/api/history'
import api from '@/api'

const items = ref([])
const loading = ref(false)
const page = ref(1)
const size = ref(50)
const total = ref(0)
const switchOptions = ref([])
const dateRange = ref(null)
const filters = reactive({ ip: '', mac: '', change_type: '', switch_id: null })

const isPaginated = computed(() => !filters.ip && !filters.mac)

function formatTime(t) {
  if (!t) return ''
  const d = new Date(t)
  if (isNaN(d.getTime())) return t
  return d.toLocaleString('zh-CN', { hour12: false })
}

function changeTag(type) {
  return type === 'added' ? 'success' : type === 'deleted' ? 'danger' : 'warning'
}

function changeLabel(type) {
  return type === 'added' ? '新增' : type === 'deleted' ? '删除' : '变更'
}

function rowClassName({ row }) {
  return 'row-' + row.change_type
}

function changeDiff(row, field) {
  const ov = row['old_' + field]
  const nv = row['new_' + field]
  const fmt = (v) => v === null || v === undefined || v === '' ? '-' : v
  if (row.change_type === 'added') return fmt(nv)
  if (row.change_type === 'deleted') return fmt(ov)
  const ofv = fmt(ov)
  const nfv = fmt(nv)
  if (ofv === nfv) return ofv
  return ofv + ' → ' + nfv
}

function resetFilters() {
  filters.ip = ''
  filters.mac = ''
  filters.change_type = ''
  filters.switch_id = null
  dateRange.value = null
  page.value = 1
  fetchData()
}

async function fetchData() {
  loading.value = true
  try {
    if (filters.ip) {
      const data = await getHistoryByIp(filters.ip)
      items.value = data
      total.value = 0
    } else if (filters.mac) {
      const data = await getHistoryByMac(filters.mac)
      items.value = data
      total.value = 0
    } else {
      const params = { page: page.value, size: size.value }
      if (filters.change_type) params.change_type = filters.change_type
      if (filters.switch_id) params.switch_id = filters.switch_id
      if (dateRange.value) {
        params.start_date = dateRange.value[0]
        params.end_date = dateRange.value[1] + ' 23:59:59'
      }
      const data = await getHistory(params)
      items.value = data.items
      total.value = data.total
    }
  } catch { /* handled by interceptor */ }
  finally { loading.value = false }
}

async function fetchSwitches() {
  try {
    const { data } = await api.get('/switches', { params: { size: 100 } })
    switchOptions.value = data.items || []
  } catch { /* handled */ }
}

onMounted(() => {
  fetchSwitches()
  fetchData()
})
</script>

<style scoped>
.history-page h2 {
  margin: 0 0 20px;
  font-size: 22px;
  font-weight: 700;
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

/* 行颜色编码 */
:deep(.row-added) { background-color: var(--color-success-bg) !important; }
:deep(.row-deleted) { background-color: var(--color-danger-bg) !important; }
:deep(.row-modified) { background-color: var(--color-warning-bg) !important; }

/* 行 hover 保持颜色但有过渡 */
:deep(.row-added:hover td) { background-color: #d1fae5 !important; }
:deep(.row-deleted:hover td) { background-color: #fee2e2 !important; }
:deep(.row-modified:hover td) { background-color: #fef3c7 !important; }
</style>
