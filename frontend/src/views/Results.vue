<template>
  <div class="results-page">
    <h2>扫描结果</h2>

    <el-form :inline="true" class="filter-bar">
      <el-form-item label="IP 地址">
        <el-input v-model="filters.ip" placeholder="输入 IP" clearable style="width:160px" />
      </el-form-item>
      <el-form-item label="MAC 地址">
        <el-input v-model="filters.mac" placeholder="输入 MAC" clearable style="width:160px" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="fetchData">查询</el-button>
        <el-button @click="filters.ip='';filters.mac='';fetchData()">重置</el-button>
        <el-button @click="exportExcel" :loading="exporting">
          <el-icon><Download /></el-icon>导出 Excel
        </el-button>
      </el-form-item>
    </el-form>

    <el-table :data="items" v-loading="loading" stripe style="width:100%">
      <template #empty>
        <el-empty description="暂无扫描结果，请先对交换机执行扫描" :image-size="80" />
      </template>
      <el-table-column type="index" width="50" />
      <el-table-column prop="switch_name" label="交换机" width="160" show-overflow-tooltip />
      <el-table-column prop="switch_ip" label="交换机IP" width="140" />
      <el-table-column prop="ip_address" label="IP 地址" width="140" />
      <el-table-column prop="mac_address" label="MAC 地址" width="150" />
      <el-table-column prop="vlan_bd" label="VLAN/BD" width="90">
        <template #default="{ row }">{{ row.vlan_bd ?? '-' }}</template>
      </el-table-column>
      <el-table-column prop="vlan_type" label="VLAN类型" width="100" />
      <el-table-column prop="physical_port" label="物理端口" min-width="160" show-overflow-tooltip />
      <el-table-column prop="virtual_port" label="虚拟端口" min-width="160" show-overflow-tooltip />
      <el-table-column prop="switch_type" label="类型" width="70">
        <template #default="{ row }">{{ row.switch_type === 'L3' ? '三层' : '二层' }}</template>
      </el-table-column>
      <el-table-column label="更新时间" width="170">
        <template #default="{ row }">
          {{ formatTime(row.created_at) }}
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination-wrap">
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
import { ref, reactive, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import api from '@/api'
import { formatTime } from '@/utils/format'

const route = useRoute()

const items = ref([])
const loading = ref(false)
const exporting = ref(false)
const page = ref(1)
const size = ref(50)
const total = ref(0)
const filters = reactive({ ip: '', mac: '' })


async function fetchData() {
  loading.value = true
  try {
    const { data } = await api.get('/results', {
      params: { page: page.value, size: size.value, ip: filters.ip, mac: filters.mac }
    })
    items.value = data.items
    total.value = data.total
  } catch { /* handled */ }
  finally { loading.value = false }
}

async function exportExcel() {
  exporting.value = true
  try {
    const r = await api.get('/results/export', {
      params: { ip: filters.ip, mac: filters.mac },
      responseType: 'blob',
    })
    const url = URL.createObjectURL(r.data)
    const a = document.createElement('a')
    a.href = url
    a.download = 'scan_results.xlsx'
    a.click()
    URL.revokeObjectURL(url)
  } finally {
    exporting.value = false
  }
}

function loadFromRoute() {
  if (route.query.ip) filters.ip = route.query.ip
  if (route.query.mac) filters.mac = route.query.mac
  fetchData()
}
onMounted(loadFromRoute)
watch(() => route.query, loadFromRoute)
</script>

<style scoped>
.results-page h2 {
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
</style>
