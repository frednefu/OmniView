<template>
  <div class="routes-page">
    <h2>路由表</h2>

    <el-form :inline="true" class="filter-bar">
      <el-form-item label="目标网络">
        <el-input v-model="filters.cidr" placeholder="输入 CIDR" clearable style="width:180px" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="fetchData">查询</el-button>
        <el-button @click="filters.cidr='';fetchData()">重置</el-button>
      </el-form-item>
    </el-form>

    <el-table :data="items" v-loading="loading" stripe style="width:100%">
      <template #empty>
        <el-empty description="暂无路由数据，请先对三层交换机执行扫描" :image-size="80" />
      </template>
      <el-table-column type="index" width="50" />
      <el-table-column prop="switch_name" label="交换机" width="160" show-overflow-tooltip />
      <el-table-column prop="switch_ip" label="交换机IP" width="140" />
      <el-table-column prop="target_network" label="目标网络" min-width="140" />
      <el-table-column prop="subnet_mask" label="子网掩码" min-width="140" />
      <el-table-column prop="cidr" label="CIDR" min-width="160" />
      <el-table-column prop="gateway" label="网关" min-width="130" />
      <el-table-column prop="interface_name" label="接口" min-width="150" show-overflow-tooltip />
      <el-table-column prop="route_type" label="类型" width="80" />
      <el-table-column prop="protocol" label="协议" width="80" />
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
import { ref, reactive, onMounted } from 'vue'
import api from '@/api'

const items = ref([])
const loading = ref(false)
const page = ref(1)
const size = ref(50)
const total = ref(0)
const filters = reactive({ cidr: '' })

function formatTime(t) {
  if (!t) return ''
  const d = new Date(t)
  if (isNaN(d.getTime())) return t
  return d.toLocaleString('zh-CN', { hour12: false })
}

async function fetchData() {
  loading.value = true
  try {
    const { data } = await api.get('/results/routes', {
      params: { page: page.value, size: size.value, cidr: filters.cidr }
    })
    items.value = data.items
    total.value = data.total
  } catch { /* handled */ }
  finally { loading.value = false }
}

onMounted(fetchData)
</script>

<style scoped>
.routes-page h2 {
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
