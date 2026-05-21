<template>
  <div class="search-result">
    <div class="page-header">
      <h2>搜索结果：{{ query }}</h2>
    </div>
    <el-table :data="results" v-loading="loading" stripe>
      <template #empty>
        <el-empty description="未找到匹配记录" :image-size="80" />
      </template>
      <el-table-column prop="switch_name" label="交换机" width="160" show-overflow-tooltip />
      <el-table-column prop="switch_ip" label="交换机IP" width="140" />
      <el-table-column prop="ip_address" label="IP 地址" width="140" />
      <el-table-column prop="mac_address" label="MAC 地址" width="150" />
      <el-table-column prop="vlan_bd" label="VLAN/BD" width="90">
        <template #default="{ row }">{{ row.vlan_bd ?? '-' }}</template>
      </el-table-column>
      <el-table-column prop="vlan_type" label="VLAN类型" width="100">
        <template #default="{ row }">{{ row.vlan_type ?? '-' }}</template>
      </el-table-column>
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
    <div class="result-count">
      共 {{ results.length }} 条记录
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import api from '@/api'

const route = useRoute()
const query = ref(route.query.q || '')
const results = ref([])
const loading = ref(false)

function formatTime(t) {
  if (!t) return ''
  const d = new Date(t)
  if (isNaN(d.getTime())) return t
  return d.toLocaleString('zh-CN', { hour12: false })
}

async function doSearch(q) {
  if (!q || q.length < 2) return
  loading.value = true
  try {
    const { data } = await api.get('/search', { params: { q, limit: 100 } })
    results.value = data
  } catch { /* handled by interceptor */ }
  finally { loading.value = false }
}

onMounted(() => {
  if (query.value) doSearch(query.value)
})

watch(() => route.query.q, (val) => {
  if (val) {
    query.value = val
    doSearch(val)
  }
})
</script>

<style scoped>
.page-header {
  margin-bottom: 20px;
}
.page-header h2 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
}
.result-count {
  margin-top: 12px;
  color: var(--color-text-muted);
  font-size: 13px;
}
</style>
